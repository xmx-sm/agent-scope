

"""
mailbox 检索核心：服务端条件搜索 + 客户端侧二次过滤，按 offset/count 分页。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

receive_email 与 find_email 共用本模块，二者只差入口参数语义。

⚠️ 返回契约变更（本次改造）:
    原实现把 total/offset/count/has_more 挂在**信封顶层**（非标准形状），
    且经 receive_email/find_email 透传后成为对外契约。
    现统一为标准信封，分页元数据收进 data:
        {"code":200,
         "data":{"emails":[...], "total":N, "offset":N, "count":N, "has_more":bool},
         "message":"命中 N 封，返回 M 封"}
    平台侧原先读 r["total"] / r["has_more"] 的代码要改成读 r["data"]["total"] / ["has_more"]。
"""


import asyncio
import email as email_lib
import os
from typing import Any, Dict

from config import get as _cfg_get, pick_str as _pick_str
from ._connection import async_open_imap
from ._helper import (
    _err,
    _ok,
    _save_email_attachments,
    check_email_config,
    decode_header_value,
    error_text,
    get_email_config,
    in_date_range,
    parse_fetch_lines,
    parse_message,
)


async def async_filter_ids_client_side(data: dict = None) -> Dict[str, Any]:
    """客户端过滤（异步）：日期 + subject/sender/keyword（AND 关系）。

    入参 (data):
        conn(aioimaplib 连接, 必填)   已 select 的连接
        ids(list, 必填)               服务端 SEARCH 返回的消息序号
        data(dict, 可选)              业务参数（keyword/subject/sender/date_from/date_to）

    返回: {"code":200, "data": [过滤后的 id...], "message":"success"} 或 400 错误信封

    QQ 等 IMAP 服务端会忽略 SINCE/BEFORE/TEXT/SUBJECT/FROM 等搜索条件并返回全部，
    需按邮件头/正文在客户端兜底过滤，确保条件真正生效。
    按关键字 keyword 搜索时额外拉取正文（批量 RFC822）判断。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_filter_ids_client_side")
    conn = data.get("conn")
    if conn is None:
        return _err("缺少 conn 字段（已 select 的 IMAP 连接）", "async_filter_ids_client_side")
    ids = data.get("ids")
    if ids is None:
        return _err("缺少 ids 字段（服务端 SEARCH 的消息序号）", "async_filter_ids_client_side")
    if not isinstance(ids, (list, tuple)):
        return _err(f"ids 必须是列表，收到 {type(ids).__name__}", "async_filter_ids_client_side")
    biz = data.get("data")
    if biz is None:
        biz = {}
    if not isinstance(biz, dict):
        return _err(f"data 必须是字典，收到 {type(biz).__name__}", "async_filter_ids_client_side")

    keyword = str(biz.get("keyword", "") or "").strip()
    subject = str(biz.get("subject", "") or "").strip()
    sender = str(biz.get("sender", "") or "").strip()
    date_from_str = str(biz.get("date_from", "") or "").strip()
    date_to_str = str(biz.get("date_to", "") or "").strip()
    if not (keyword or subject or sender or date_from_str or date_to_str):
        return _ok(list(ids))
    if not ids:
        return _ok(list(ids))
    # 拉取头部（BODY.PEEK[HEADER]）
    seq = ",".join(str(i) for i in ids)
    resp = await conn.fetch(seq, "(BODY.PEEK[HEADER])")
    msg_map = {}
    if resp.result == "OK":
        pf = parse_fetch_lines({"lines": resp.lines})
        if pf.get("code") != 200:
            return pf
        for num, chunk in pf["data"].items():
            if chunk:
                msg_map[num] = email_lib.message_from_bytes(chunk)
    # 第一轮：按日期/主题/发件人（基于头部）过滤
    candidates = []
    for mid in ids:
        try:
            msg = msg_map.get(int(mid))
        except (ValueError, TypeError):
            msg = None
        if msg is None:
            continue
        dr = in_date_range({"date_str": msg.get("Date", ""),
                            "date_from_str": date_from_str, "date_to_str": date_to_str})
        if dr.get("code") != 200:
            return dr
        if not dr["data"]:
            continue
        dh = decode_header_value({"value": msg.get("Subject", "")})
        if dh.get("code") != 200:
            return dh
        subj = dh["data"]
        from_name, from_addr = email_lib.utils.parseaddr(msg.get("From", "") or "")
        if subject and subject not in subj:
            continue
        if sender and sender not in from_addr and sender not in from_name:
            continue
        candidates.append((mid, subj, from_addr, from_name))
    if not keyword:
        return _ok([m[0] for m in candidates])
    # 第二轮：关键字需全文（含正文），批量拉取正文过滤
    if candidates:
        cseq = ",".join(str(m[0]) for m in candidates)
        resp = await conn.fetch(cseq, "(BODY.PEEK[RFC822])")
        body_map = {}
        if resp.result == "OK":
            pf = parse_fetch_lines({"lines": resp.lines})
            if pf.get("code") != 200:
                return pf
            for num, chunk in pf["data"].items():
                if chunk:
                    body_map[num] = email_lib.message_from_bytes(chunk)
        kw = keyword.lower()
        filtered = []
        for mid, subj, from_addr, from_name in candidates:
            msg = body_map.get(int(mid))
            body = ""
            if msg:
                pm = parse_message({"msg": msg, "with_attachments": False})
                if pm.get("code") != 200:
                    return pm
                body = pm["data"].get("body", "")
            hay = f"{subj} {from_addr} {from_name} {body}".lower()
            if kw in hay:
                filtered.append(mid)
        return _ok(filtered)
    return _ok([m[0] for m in candidates])


async def async_search_mailbox(data: dict = None) -> Dict[str, Any]:
    """统一 IMAP 搜索（异步，aioimaplib）+ 客户端过滤 + 翻页 + 解析。

    入参 (data):
        data(dict, 必填)             业务参数（mailbox/keyword/... 由上层透传）
        criteria(list, 可选)         服务端搜索条件；非空时 AND 组合，为空则 ALL
        offset(int, 可选)            跳过最近 N 封（从新往旧数的偏移）
        count(int, 可选)             本次取几封
        func_name(str, 可选)         错误位置标识里的函数名
        save_attachments(bool, 可选) 默认 True，把附件下载到本地
        attachment_dir(str, 可选)    附件根目录，缺省 "email_attachments"

    返回:
        {"code":200,
         "data":{"emails":[...], "total":N, "offset":N, "count":N, "has_more":bool},
         "message":"命中 N 封，返回 M 封"}
        或 {"code":400/500, "data": 位置, "message": 错误描述}

    分页语义（原样保留）：ids 按时间升序（旧→新），最新的在末尾；
    offset 是"从最新往旧跳过的封数"，故 end = total - offset、start = max(0, end-count)；
    输出 emails 按 reversed(page_ids) 即**最新在前**。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_search_mailbox")
    biz = data.get("data")
    if biz is None:
        return _err("缺少 data 字段（业务参数字典）", "async_search_mailbox")
    if not isinstance(biz, dict):
        return _err(f"data 必须是字典，收到 {type(biz).__name__}", "async_search_mailbox")
    criteria = data.get("criteria")
    if criteria is None:
        criteria = []
    if not isinstance(criteria, (list, tuple)):
        return _err(f"criteria 必须是列表，收到 {type(criteria).__name__}", "async_search_mailbox")
    func_name = str(data.get("func_name") or "async_search_mailbox")

    def _nonneg(key, default):
        raw = data.get(key, default)
        if raw in (None, ""):
            raw = default
        if isinstance(raw, (dict, list, tuple, set)):
            return None, _err(f"{key} 必须是整数，收到 {type(raw).__name__}", func_name)
        try:
            v = int(raw)
        except (TypeError, ValueError):
            return None, _err(f"{key} 必须是整数", func_name)
        return max(v, 0), None

    offset, e = _nonneg("offset", 0)
    if e:
        return e
    count, e = _nonneg("count", 10)
    if e:
        return e
    sa = data.get("save_attachments")
    if sa is None or sa == "":
        sa = _cfg_get("mail.save_attachments", True)
    save_attachments = bool(sa)
    attachment_dir = str(data.get("attachment_dir", "") or "").strip()

    try:
        cg = get_email_config(biz)
        if cg.get("code") != 200:
            return cg
        cfg = cg["data"]
        ck = check_email_config({"cfg": cfg, "func_name": func_name})
        if ck.get("code") != 200:
            return ck
        cr = await async_open_imap({"cfg": cfg, "timeout": 30})
        if cr.get("code") != 200:
            return cr
        conn = cr["data"]
        resp = await conn.login(cfg["host_user"], cfg["password"])
        if resp.result != "OK":
            await conn.logout()
            return {"code": 500, "data": f"{os.path.abspath(__file__)}_{func_name}",
                    "message": f"登录失败：{resp.result}"}
        mailbox = _pick_str(biz.get("mailbox"), "mail.mailbox", "INBOX")
        resp = await conn.select(mailbox)
        if resp.result != "OK":
            await conn.logout()
            return {"code": 500, "data": f"{os.path.abspath(__file__)}_{func_name}",
                    "message": f"无法打开邮箱文件夹: {mailbox}"}
        search_expr = f'({" ".join(criteria)})' if criteria else "ALL"
        resp = await conn.search(search_expr)
        if resp.result != "OK":
            await conn.logout()
            return {"code": 500, "data": f"{os.path.abspath(__file__)}_{func_name}",
                    "message": "搜索失败"}
        # 从 SEARCH 结果行解析消息 id：aioimaplib 已剥掉 "* SEARCH " 前缀，
        # response.lines 形如 [b'1 2 3 ... 611', b'SEARCH completed']
        ids = []
        for ln in resp.lines:
            ids.extend(int(x) for x in ln.split() if x.isdigit())
        # 客户端兜底过滤：QQ 邮箱 IMAP 服务端忽略部分搜索条件，需按头/正文过滤
        fr = await async_filter_ids_client_side({"conn": conn, "ids": ids, "data": biz})
        if fr.get("code") != 200:
            await conn.logout()
            return fr
        ids = fr["data"]
        total = len(ids)
        # ids 按时间升序（旧→新），最新的在末尾
        end = total - offset
        start = max(0, end - count)
        page_ids = ids[start:end]
        emails = []
        if not attachment_dir:
            attachment_dir = _cfg_get("mail.attachment_dir", "email_attachments")
        # 第二层目录用 profile_name（agent 配置里的邮箱名）；未注入则回退邮箱地址，保证不同邮箱分目录
        mail_box_name = cfg.get("profile_name", "") or cfg.get("host_user", "")
        for mid in reversed(page_ids):
            resp = await conn.fetch(str(mid), "(RFC822)")
            pf = parse_fetch_lines({"lines": resp.lines})
            if pf.get("code") != 200:
                await conn.logout()
                return pf
            chunk = pf["data"].get(mid, b"")
            if not chunk:
                continue
            msg = email_lib.message_from_bytes(chunk)
            dh = decode_header_value({"value": msg.get("Message-ID", "")})
            if dh.get("code") != 200:
                await conn.logout()
                return dh
            msg_id_raw = dh["data"].strip().strip("<>").strip()
            # email_id = "{邮箱名}#{Message-ID}"，第三层目录用 Message-ID；区分来源邮箱避免 ID 冲突
            email_id = f"{mail_box_name}#{msg_id_raw}" if msg_id_raw else mail_box_name
            pm = parse_message({"msg": msg, "with_attachments": save_attachments})
            if pm.get("code") != 200:
                await conn.logout()
                return pm
            parsed = pm["data"]
            parsed["email_id"] = email_id
            if save_attachments and parsed.get("attachments"):
                sv = await asyncio.to_thread(
                    _save_email_attachments,
                    {"email_id": email_id, "attachment_dir": attachment_dir,
                     "attachments": parsed["attachments"]})
                if sv.get("code") != 200:
                    # 附件落盘失败不拖垮整封邮件的解析结果（原实现即如此降级）
                    parsed["attachments"] = [{"error": str(sv.get("message", "")).removeprefix("错误：")}]
                else:
                    parsed["attachments"] = sv["data"]
            emails.append(parsed)
        await conn.logout()
        return _ok({"emails": emails, "total": total, "offset": offset,
                    "count": len(emails), "has_more": end < total},
                   f"命中 {total} 封，返回 {len(emails)} 封")
    except Exception as e:
        return {"code": 500, "data": f"{os.path.abspath(__file__)}_{func_name}",
                "message": f"邮件操作失败：{error_text({'e': e})['data']}"}
