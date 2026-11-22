# -*- coding: utf-8 -*-
"""权限规则、审批审计与 pending 确认的 SQLite 存储。

三张表：

- ``permission_rules``：allow / deny / ask 规则
- ``permission_audit``：谁在何时批准 / 拒绝了哪次工具调用
- ``permission_pending``：跨进程共享的待确认事件与结果

数据库路径必须显式传入（绝对路径），不做源码兜底，和 RAG 的
``base_dir`` 约定一致。默认支持 ``create_dir=True`` 自动创建父目录。

所有方法都是 async，内部通过 ``asyncio.to_thread`` 执行 SQLite I/O。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agentscope.permission import PermissionBehavior, PermissionRule

from .context import (
    add_permission_rule,
    build_permission_context,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS permission_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL,
    rule_content TEXT,
    behavior TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_permission_rules_scope
    ON permission_rules (tenant_id, agent_id, tool_name, behavior);

CREATE TABLE IF NOT EXISTS permission_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    reply_id TEXT,
    tool_call_id TEXT,
    tool_name TEXT NOT NULL,
    tool_input TEXT,
    decision TEXT NOT NULL,
    decision_source TEXT,
    rules TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_permission_audit_scope
    ON permission_audit (tenant_id, agent_id, created_at);

CREATE TABLE IF NOT EXISTS permission_pending (
    key TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    reply_id TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_permission_pending_scope
    ON permission_pending (tenant_id, agent_id, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _coerce_rule(rule: Any) -> PermissionRule:
    if isinstance(rule, PermissionRule):
        return rule
    if not isinstance(rule, dict):
        raise ValueError("rule 必须是 PermissionRule 或字典")
    tool_name = str(rule.get("tool_name") or "").strip()
    if not tool_name:
        raise ValueError("rule.tool_name 不能为空")
    behavior_raw = rule.get("behavior")
    if isinstance(behavior_raw, PermissionBehavior):
        behavior = behavior_raw
    else:
        behavior = {
            "allow": PermissionBehavior.ALLOW,
            "deny": PermissionBehavior.DENY,
            "ask": PermissionBehavior.ASK,
        }.get(str(behavior_raw or "").strip().lower())
        if behavior is None:
            raise ValueError("rule.behavior 必须是 allow/deny/ask")
    content = rule.get("rule_content")
    if content is not None and not isinstance(content, str):
        raise ValueError("rule.rule_content 必须是字符串或 None")
    return PermissionRule(
        tool_name=tool_name,
        rule_content=content,
        behavior=behavior,
        source=str(rule.get("source") or "projectSettings"),
    )


class PermissionStore:
    """SQLite 权限存储。

    用法::

        store = PermissionStore("/data/permission.db", create_dir=True)
        await store.initialize()

        await store.add_rule(PermissionRule(...), tenant_id="u1", agent_id="a1")
        ctx = await store.load_context("u1", "a1", base={"mode": "default"})

        await store.record_audit({...})
        await store.save_pending("reply-1", {"tool_calls": [...]})
        result = await store.wait_pending("reply-1", timeout=300)
    """

    def __init__(self, db_path: str, create_dir: bool = False) -> None:
        path = str(db_path or "").strip()
        if not path:
            raise ValueError("缺少 permission.sqlite.path")
        if not os.path.isabs(path):
            raise ValueError(f"permission.sqlite.path 必须是绝对路径: {path}")
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            if not create_dir:
                raise ValueError(f"permission.sqlite 目录不存在: {parent}")
            os.makedirs(parent, exist_ok=True)
        self.db_path = path
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_sync)
            self._initialized = True

    def _init_sync(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    async def _ensure(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def _run(self, fn, *args):
        await self._ensure()
        return await asyncio.to_thread(fn, *args)

    # ── 规则 ────────────────────────────────────────────────────
    async def add_rule(
        self,
        rule: Any,
        *,
        tenant_id: str = "",
        agent_id: str = "",
    ) -> int:
        parsed = _coerce_rule(rule)
        return await self._run(
            self._add_rule_sync, parsed, str(tenant_id or ""), str(agent_id or ""))

    async def add_rules(
        self,
        rules: List[Any],
        *,
        tenant_id: str = "",
        agent_id: str = "",
    ) -> int:
        parsed = [_coerce_rule(rule) for rule in rules or []]
        return await self._run(
            self._add_rules_sync, parsed, str(tenant_id or ""), str(agent_id or ""))

    def _add_rule_sync(
        self,
        rule: PermissionRule,
        tenant_id: str,
        agent_id: str,
    ) -> int:
        conn = self._connect()
        try:
            return self._insert_rule(conn, rule, tenant_id, agent_id)
        finally:
            conn.close()

    def _add_rules_sync(
        self,
        rules: List[PermissionRule],
        tenant_id: str,
        agent_id: str,
    ) -> int:
        conn = self._connect()
        try:
            count = 0
            with conn:
                for rule in rules:
                    self._insert_rule(conn, rule, tenant_id, agent_id)
                    count += 1
            return count
        finally:
            conn.close()

    @staticmethod
    def _insert_rule(
        conn: sqlite3.Connection,
        rule: PermissionRule,
        tenant_id: str,
        agent_id: str,
    ) -> int:
        conn.execute(
            "DELETE FROM permission_rules WHERE tenant_id=? AND agent_id=? "
            "AND tool_name=? AND behavior=? AND IFNULL(rule_content,'')=IFNULL(?,'') "
            "AND source=?",
            (tenant_id, agent_id, rule.tool_name, rule.behavior.value,
             rule.rule_content, rule.source),
        )
        cur = conn.execute(
            "INSERT INTO permission_rules "
            "(tenant_id, agent_id, tool_name, rule_content, behavior, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, agent_id, rule.tool_name, rule.rule_content,
             rule.behavior.value, rule.source, _now()),
        )
        conn.commit()
        return int(cur.lastrowid)

    async def list_rules(
        self,
        *,
        tenant_id: str = "",
        agent_id: str = "",
        behavior: Optional[str] = None,
        include_global: bool = True,
    ) -> List[PermissionRule]:
        return await self._run(
            self._list_rules_sync, str(tenant_id or ""), str(agent_id or ""),
            behavior, include_global)

    def _list_rules_sync(
        self,
        tenant_id: str,
        agent_id: str,
        behavior: Optional[str],
        include_global: bool,
    ) -> List[PermissionRule]:
        conn = self._connect()
        try:
            clauses = []
            args: List[Any] = []
            if include_global:
                clauses.append(
                    "((tenant_id=? OR tenant_id='') AND (agent_id=? OR agent_id=''))")
                args.extend([tenant_id, agent_id])
            else:
                clauses.append("tenant_id=? AND agent_id=?")
                args.extend([tenant_id, agent_id])
            if behavior:
                clauses.append("behavior=?")
                args.append(str(behavior))
            sql = "SELECT * FROM permission_rules"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY id"
            rows = conn.execute(sql, args).fetchall()
            return [
                PermissionRule(
                    tool_name=row["tool_name"],
                    rule_content=row["rule_content"],
                    behavior=PermissionBehavior(row["behavior"]),
                    source=row["source"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    async def delete_rules(
        self,
        *,
        rule_id: Optional[int] = None,
        tenant_id: str = "",
        agent_id: str = "",
        tool_name: Optional[str] = None,
    ) -> int:
        return await self._run(
            self._delete_rules_sync, rule_id, str(tenant_id or ""),
            str(agent_id or ""), tool_name)

    def _delete_rules_sync(
        self,
        rule_id: Optional[int],
        tenant_id: str,
        agent_id: str,
        tool_name: Optional[str],
    ) -> int:
        conn = self._connect()
        try:
            clauses = []
            args: List[Any] = []
            if rule_id is not None:
                clauses.append("id=?")
                args.append(int(rule_id))
            else:
                clauses.append("tenant_id=? AND agent_id=?")
                args.extend([tenant_id, agent_id])
                if tool_name is not None:
                    clauses.append("tool_name=?")
                    args.append(tool_name)
            with conn:
                cur = conn.execute(
                    "DELETE FROM permission_rules WHERE " + " AND ".join(clauses),
                    args)
            return int(cur.rowcount)
        finally:
            conn.close()

    async def load_context(
        self,
        tenant_id: str = "",
        agent_id: str = "",
        base: Any = None,
        *,
        include_global: bool = True,
    ):
        """把 SQLite 规则合并进一个 PermissionContext。"""
        context = build_permission_context(base)
        rules = await self.list_rules(
            tenant_id=tenant_id, agent_id=agent_id,
            include_global=include_global)
        for rule in rules:
            add_permission_rule(context, rule)
        return context

    # ── 审计 ────────────────────────────────────────────────────
    async def record_audit(self, entry: Dict[str, Any]) -> int:
        if not isinstance(entry, dict):
            raise ValueError("audit entry 必须是字典")
        tool_name = str(entry.get("tool_name") or "").strip()
        if not tool_name:
            raise ValueError("audit.tool_name 不能为空")
        decision = str(entry.get("decision") or "").strip().lower()
        if decision not in ("allow", "deny", "ask", "error"):
            raise ValueError("audit.decision 必须是 allow/deny/ask/error")
        return await self._run(self._record_audit_sync, dict(entry), tool_name, decision)

    def _record_audit_sync(
        self,
        entry: Dict[str, Any],
        tool_name: str,
        decision: str,
    ) -> int:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO permission_audit "
                    "(tenant_id, agent_id, reply_id, tool_call_id, tool_name, "
                    " tool_input, decision, decision_source, rules, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(entry.get("tenant_id") or ""),
                        str(entry.get("agent_id") or ""),
                        entry.get("reply_id"),
                        entry.get("tool_call_id"),
                        tool_name,
                        _json(entry.get("tool_input")),
                        decision,
                        entry.get("decision_source"),
                        _json(entry.get("rules")),
                        str(entry.get("created_at") or _now()),
                    ),
                )
            return int(cur.lastrowid)
        finally:
            conn.close()

    async def list_audit(
        self,
        *,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        return await self._run(
            self._list_audit_sync, tenant_id, agent_id,
            max(0, int(limit)), max(0, int(offset)))

    def _list_audit_sync(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        limit: int,
        offset: int,
    ) -> List[dict]:
        conn = self._connect()
        try:
            clauses, args = [], []
            if tenant_id is not None:
                clauses.append("tenant_id=?")
                args.append(tenant_id)
            if agent_id is not None:
                clauses.append("agent_id=?")
                args.append(agent_id)
            sql = "SELECT * FROM permission_audit"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            args.extend([limit, offset])
            rows = conn.execute(sql, args).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["tool_input"] = _loads(item.get("tool_input"))
                item["rules"] = _loads(item.get("rules"))
                result.append(item)
            return result
        finally:
            conn.close()

    # ── 分布式 pending ──────────────────────────────────────────
    async def save_pending(
        self,
        key: str,
        payload: Any,
        *,
        tenant_id: str = "",
        agent_id: str = "",
        reply_id: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> None:
        text = str(key or "").strip()
        if not text:
            raise ValueError("pending key 不能为空")
        await self._run(
            self._save_pending_sync, text, payload, str(tenant_id or ""),
            str(agent_id or ""), reply_id, int(ttl_seconds))

    def _save_pending_sync(
        self,
        key: str,
        payload: Any,
        tenant_id: str,
        agent_id: str,
        reply_id: Optional[str],
        ttl_seconds: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=max(1, ttl_seconds))).isoformat()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO permission_pending "
                    "(key, tenant_id, agent_id, reply_id, payload, status, "
                    " result, version, created_at, expires_at, resolved_at) "
                    "VALUES (?, ?, ?, ?, ?, 'pending', NULL, 1, ?, ?, NULL) "
                    "ON CONFLICT(key) DO UPDATE SET "
                    "tenant_id=excluded.tenant_id, agent_id=excluded.agent_id, "
                    "reply_id=excluded.reply_id, "
                    "payload=excluded.payload, status='pending', result=NULL, "
                    "version=permission_pending.version+1, "
                    "expires_at=excluded.expires_at, resolved_at=NULL",
                    (key, tenant_id, agent_id, reply_id, _json(payload),
                     now.isoformat(), expires),
                )
        finally:
            conn.close()

    async def get_pending(self, key: str) -> Optional[dict]:
        return await self._run(self._get_pending_sync, str(key))

    def _get_pending_sync(self, key: str) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM permission_pending WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["payload"] = _loads(item.get("payload"))
            item["result"] = _loads(item.get("result"))
            return item
        finally:
            conn.close()

    async def resolve_pending(
        self,
        key: str,
        result: Any,
        *,
        expected_version: Optional[int] = None,
    ) -> bool:
        return await self._run(
            self._resolve_pending_sync, str(key), result, expected_version)

    def _resolve_pending_sync(
        self,
        key: str,
        result: Any,
        expected_version: Optional[int],
    ) -> bool:
        conn = self._connect()
        try:
            sql = (
                "UPDATE permission_pending SET status='resolved', result=?, "
                "version=version+1, resolved_at=? "
                "WHERE key=? AND status='pending'"
            )
            args: List[Any] = [_json(result), _now(), key]
            if expected_version is not None:
                sql += " AND version=?"
                args.append(int(expected_version))
            with conn:
                cur = conn.execute(sql, args)
            return cur.rowcount > 0
        finally:
            conn.close()

    async def list_pending(
        self,
        *,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        status: Optional[str] = "pending",
        limit: int = 100,
    ) -> List[dict]:
        return await self._run(
            self._list_pending_sync, tenant_id, agent_id, status,
            max(0, int(limit)))

    def _list_pending_sync(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        status: Optional[str],
        limit: int,
    ) -> List[dict]:
        conn = self._connect()
        try:
            clauses, args = [], []
            if tenant_id is not None:
                clauses.append("tenant_id=?")
                args.append(tenant_id)
            if agent_id is not None:
                clauses.append("agent_id=?")
                args.append(agent_id)
            if status is not None:
                clauses.append("status=?")
                args.append(status)
            sql = "SELECT * FROM permission_pending"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY created_at DESC LIMIT ?"
            args.append(limit)
            rows = conn.execute(sql, args).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["payload"] = _loads(item.get("payload"))
                item["result"] = _loads(item.get("result"))
                result.append(item)
            return result
        finally:
            conn.close()

    async def wait_pending(
        self,
        key: str,
        *,
        timeout: float = 300,
        interval: float = 0.5,
    ) -> Optional[Any]:
        """轮询等待另一个进程 resolve_pending。超时返回 None。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, float(timeout))
        while loop.time() < deadline:
            item = await self.get_pending(key)
            if item is None:
                return None
            if item.get("status") == "resolved":
                return item.get("result")
            await asyncio.sleep(max(0.05, float(interval)))
        return None

    async def cleanup_expired(self) -> int:
        return await self._run(self._cleanup_expired_sync)

    def _cleanup_expired_sync(self) -> int:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE permission_pending SET status='expired', "
                    "resolved_at=? WHERE status='pending' AND expires_at IS NOT NULL "
                    "AND expires_at < ?",
                    (_now(), _now()),
                )
            return int(cur.rowcount)
        finally:
            conn.close()


def make_pending_key(
    reply_id: str,
    *,
    tenant_id: str = "",
    agent_id: str = "",
) -> str:
    """生成 pending key；同一 reply 内所有需要确认的工具共用一个 key。"""
    rid = str(reply_id or "").strip()
    if not rid:
        raise ValueError("reply_id 不能为空")
    return f"{tenant_id or '-'}:{agent_id or '-'}:{rid}"


__all__ = ["PermissionStore", "make_pending_key"]
