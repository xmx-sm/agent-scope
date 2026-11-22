"""用户定时任务：间隔与日历式调度。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import AgentConversation, UserScheduledJob
from app.services.agent.chat import async_run_turn

logger = logging.getLogger("scheduled")
CN = timezone(timedelta(hours=8))
MAX_JOBS = 20
_running: set[str] = set()
_sem = asyncio.Semaphore(2)
_tasks: set[asyncio.Task] = set()


def _parse_rule(raw) -> dict:
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw or "{}")
        except (ValueError, TypeError):
            data = {}
    return data if isinstance(data, dict) else {}


def _normalize_rule(raw) -> dict:
    rule = _parse_rule(raw)
    mode = str(rule.get("date_mode") or "weekday")
    if mode not in ("weekday", "month_range", "date_span"):
        raise ApiError("日历日期模式只支持 weekday/month_range/date_span")
    times = []
    for item in rule.get("times") or ["09:00"]:
        text = str(item)
        try:
            hour, minute = text.split(":")
            hour, minute = int(hour), int(minute)
        except (ValueError, AttributeError):
            raise ApiError(f"时刻格式不合法：{text}")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ApiError(f"时刻格式不合法：{text}")
        times.append(f"{hour:02d}:{minute:02d}")
    times = sorted(set(times))
    if not times or len(times) > 12:
        raise ApiError("每天时刻需 1~12 个")
    out = {"date_mode": mode, "times": times}
    if mode == "weekday":
        days = []
        for item in rule.get("weekdays") or [1, 2, 3, 4, 5]:
            try:
                day = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= day <= 7:
                days.append(day)
        if not days:
            raise ApiError("请至少选择一个星期")
        out["weekdays"] = sorted(set(days))
    elif mode == "month_range":
        try:
            start = int(rule.get("month_from") or 1)
            end = int(rule.get("month_to") or 31)
        except (TypeError, ValueError):
            raise ApiError("每月日号必须为整数")
        if not (1 <= start <= 31 and 1 <= end <= 31):
            raise ApiError("每月日号必须在 1~31")
        out["month_from"] = start
        out["month_to"] = end
    else:
        start = str(rule.get("start_date") or "")
        end = str(rule.get("end_date") or "")
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            raise ApiError("日期范围格式必须为 YYYY-MM-DD")
        if end_dt < start_dt:
            raise ApiError("结束日期不能早于开始日期")
        out["start_date"] = start
        out["end_date"] = end
    return out


def _day_matches(day, rule: dict) -> bool:
    mode = rule.get("date_mode")
    if mode == "weekday":
        return day.isoweekday() in rule["weekdays"]
    if mode == "month_range":
        start, end = rule["month_from"], rule["month_to"]
        if start <= end:
            return start <= day.day <= end
        return day.day >= start or day.day <= end
    start = datetime.strptime(rule["start_date"], "%Y-%m-%d").date()
    end = datetime.strptime(rule["end_date"], "%Y-%m-%d").date()
    return start <= day <= end


def _next_calendar(rule: dict, now_utc: datetime) -> datetime | None:
    now_cn = now_utc.astimezone(CN)
    times = rule.get("times") or []
    for offset in range(0, 401):
        day = (now_cn + timedelta(days=offset)).date()
        if not _day_matches(day, rule):
            continue
        for text in times:
            hour, minute = (int(part) for part in text.split(":"))
            candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=CN)
            if candidate > now_cn:
                return candidate.astimezone(timezone.utc)
    return None


def _summary(rule: dict) -> str:
    times = "、".join(rule.get("times") or [])
    mode = rule.get("date_mode")
    if mode == "weekday":
        names = "一二三四五六日"
        days = "、".join(f"周{names[day - 1]}" for day in rule.get("weekdays") or [])
        return f"{days} {times}"
    if mode == "month_range":
        return f"每月 {rule['month_from']}~{rule['month_to']} 日 {times}"
    return f"{rule['start_date']} 至 {rule['end_date']} 每天 {times}"


def _public(row: UserScheduledJob) -> dict:
    now = datetime.now(timezone.utc)
    rule = _parse_rule(row.calendar_rule)
    remaining = int((row.next_run_at - now).total_seconds()) if row.next_run_at else None
    return {
        "id": row.id,
        "name": row.name,
        "instruction": row.instruction,
        "interval_seconds": row.interval_seconds,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "next_run_in": remaining,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_status": row.last_status,
        "last_error": row.last_error,
        "last_conversation_id": row.last_conversation_id,
        "run_count": row.run_count,
        "enabled": row.enabled,
        "conv_mode": row.conv_mode,
        "conversation_id": row.conversation_id,
        "timeout_seconds": row.timeout_seconds,
        "schedule_mode": row.schedule_mode,
        "calendar_rule": rule or None,
        "calendar_summary": _summary(rule) if row.schedule_mode == "calendar" and rule else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def async_list(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    rows = (
        await session.execute(
            select(UserScheduledJob)
            .where(UserScheduledJob.user_id == params["user_id"])
            .order_by(UserScheduledJob.created_at)
        )
    ).scalars().all()
    return [_public(row) for row in rows]


async def _get_own(session: AsyncSession, user_id: str, job_id: str) -> UserScheduledJob:
    row = await session.get(UserScheduledJob, job_id)
    if row is None or row.user_id != user_id:
        raise ApiError("定时任务不存在", code=404)
    return row


async def _validate_target(
    session: AsyncSession, user_id: str, conv_mode: str, conversation_id: str | None
) -> None:
    if conv_mode not in ("new", "fixed"):
        raise ApiError("会话模式只支持 new/fixed")
    if conv_mode == "fixed":
        if not conversation_id:
            raise ApiError("固定会话模式必须选择目标会话")
        conv = await session.get(AgentConversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise ApiError("目标会话不存在或不属于你")


async def async_save(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    data: dict = params["data"]
    job_id = data.get("id")
    row = await _get_own(session, user_id, job_id) if job_id else None
    if row is None:
        count = int(
            (
                await session.execute(
                    select(func.count()).select_from(UserScheduledJob).where(
                        UserScheduledJob.user_id == user_id
                    )
                )
            ).scalar_one()
        )
        if count >= MAX_JOBS:
            raise ApiError(f"每人最多 {MAX_JOBS} 个定时任务")
        row = UserScheduledJob(user_id=user_id)
        session.add(row)
    name = str(data.get("name") or "").strip()
    instruction = str(data.get("instruction") or "").strip()
    if not name or not instruction:
        raise ApiError("任务名称与指令不能为空")
    mode = str(data.get("schedule_mode") or "interval")
    if mode not in ("interval", "calendar"):
        raise ApiError("调度方式只支持 interval/calendar")
    conv_mode = str(data.get("conv_mode") or "new")
    await _validate_target(session, user_id, conv_mode, data.get("conversation_id"))
    timeout = max(10, min(int(data.get("timeout_seconds") or 300), 1800))
    row.name = name[:100]
    row.instruction = instruction
    row.conv_mode = conv_mode
    row.conversation_id = data.get("conversation_id") if conv_mode == "fixed" else None
    row.timeout_seconds = timeout
    row.schedule_mode = mode
    now = datetime.now(timezone.utc)
    if mode == "interval":
        interval = max(60, min(int(data.get("interval_seconds") or 3600), 366 * 86400))
        row.interval_seconds = interval
        row.calendar_rule = ""
        row.next_run_at = now + timedelta(seconds=interval)
    else:
        rule = _normalize_rule(data.get("calendar_rule"))
        nxt = _next_calendar(rule, now)
        if nxt is None:
            raise ApiError("日历规则在未来 400 天内没有触发点")
        row.calendar_rule = json.dumps(rule, ensure_ascii=False)
        row.next_run_at = nxt
        row.interval_seconds = 3600
    row.enabled = bool(data.get("enabled", True))
    if job_id:
        row.next_run_at = row.next_run_at
    await session.commit()
    await session.refresh(row)
    return _public(row)


async def async_toggle(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await _get_own(session, params["user_id"], params["job_id"])
    row.enabled = bool(params["enabled"])
    if row.enabled:
        now = datetime.now(timezone.utc)
        if row.schedule_mode == "calendar":
            rule = _parse_rule(row.calendar_rule)
            nxt = _next_calendar(rule, now)
            if nxt is None:
                raise ApiError("日历规则已无触发点")
            row.next_run_at = nxt
        else:
            row.next_run_at = now + timedelta(seconds=row.interval_seconds)
    await session.commit()
    return _public(row)


async def async_delete(params: dict) -> None:
    session: AsyncSession = params["session"]
    row = await _get_own(session, params["user_id"], params["job_id"])
    await session.delete(row)
    await session.commit()


async def _create_conversation(session: AsyncSession, job: UserScheduledJob) -> str:
    if job.conv_mode == "fixed" and job.conversation_id:
        conv = await session.get(AgentConversation, job.conversation_id)
        if conv is not None and conv.user_id == job.user_id:
            return conv.id
    now_cn = datetime.now(CN)
    conv = AgentConversation(
        user_id=job.user_id,
        title=f"[定时] {job.name} {now_cn:%m-%d %H:%M}"[:200],
        origin="cron",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv.id


async def _execute(job_id: str) -> None:
    from app.core.database import AsyncSessionLocal

    async with _sem:
        _running.add(job_id)
        try:
            async with AsyncSessionLocal() as session:
                job = await session.get(UserScheduledJob, job_id)
                if job is None or not job.enabled:
                    return
                user_id = job.user_id
                instruction = job.instruction
                timeout = job.timeout_seconds
                cid = await _create_conversation(session, job)
                job.last_status = "running"
                job.last_conversation_id = cid
                await session.commit()
            try:
                result = await asyncio.wait_for(
                    async_run_turn(user_id, cid, instruction, source="cron"),
                    timeout=timeout,
                )
                status = "success"
                error = ""
                content = result.get("content") or ""
            except asyncio.TimeoutError:
                status, error, content = "timeout", f"执行超时（{timeout}s）", ""
            except Exception as exc:  # noqa: BLE001
                status, error, content = "error", str(exc)[:1000], ""
            async with AsyncSessionLocal() as session:
                job = await session.get(UserScheduledJob, job_id)
                if job is None:
                    return
                job.last_run_at = datetime.now(timezone.utc)
                job.last_status = status
                job.last_error = error
                job.last_conversation_id = cid
                job.run_count += 1
                if status == "success" and content:
                    job.last_error = ""
                await session.commit()
        finally:
            _running.discard(job_id)


async def async_run_now(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await _get_own(session, params["user_id"], params["job_id"])
    if row.id in _running:
        raise ApiError("任务正在执行中")
    task = asyncio.create_task(_execute(row.id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"job_id": row.id, "submitted": True}


async def async_tick(params: dict) -> int:
    """认领到期任务并后台执行。返回认领数量。"""
    from app.core.database import AsyncSessionLocal

    processed = 0
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        rows = (
            await session.execute(
                select(UserScheduledJob).where(
                    UserScheduledJob.enabled.is_(True),
                    UserScheduledJob.next_run_at <= now,
                )
            )
        ).scalars().all()
    for row in rows:
        if row.id in _running:
            continue
        now = datetime.now(timezone.utc)
        if row.schedule_mode == "calendar":
            rule = _parse_rule(row.calendar_rule)
            nxt = _next_calendar(rule, now)
            enabled = nxt is not None
            new_next = nxt or row.next_run_at
        else:
            new_next = now + timedelta(seconds=max(60, row.interval_seconds))
            enabled = True
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(UserScheduledJob)
                .where(
                    UserScheduledJob.id == row.id,
                    UserScheduledJob.next_run_at == row.next_run_at,
                    UserScheduledJob.enabled.is_(True),
                )
                .values(next_run_at=new_next, enabled=enabled, last_status="running")
            )
            await session.commit()
        if result.rowcount != 1:
            continue
        processed += 1
        task = asyncio.create_task(_execute(row.id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return processed


async def async_scheduler_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            count = await async_tick({})
            if count:
                logger.info("定时任务触发：%s 个", count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("定时任务扫描失败：%s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
