

"""
function="find_email" — 按条件查找邮件（分页）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

分页元数据（total/offset/count/has_more）随本次改造收进 data，
详见 search.py 的契约变更说明。

⚠️ 既有安全缺陷（未修，见 docs/踩坑记录.md A17）:
    keyword/subject/sender 被直接拼进 IMAP 搜索表达式并用双引号包裹，**未转义**。
    输入 `x" OR (UNSEEN OR DELETED)"` 会构造出
        TEXT "x" OR (UNSEEN OR DELETED)""
    —— 引号被提前闭合，追加的条件生效，搜索范围被绕过（只能扩大、不能缩小，
    且服务端可能直接报语法错误）。修法是转义 `"` 与 `\\`，但会改变现有行为，
    属独立安全决策，本次改造保持原样。
"""


from typing import Any, Dict

from ._helper import _err, build_date_criteria, parse_int
from .search import async_search_mailbox


async def async_find_email(data: dict = None) -> Dict[str, Any]:
    """
    按条件查找邮件（异步，aioimaplib）：关键字/主题/发件人/日期，AND 关系 + 分页。

    入参 (data):
        keyword(str, 条件)          正文/主题/发件人包含的关键字
        subject(str, 条件)          主题包含的字符串
        sender(str, 条件)           发件人地址或显示名包含的字符串
        date_from(str, 条件)        起始日期 "YYYY-MM-DD"
        date_to(str, 条件)          结束日期 "YYYY-MM-DD"
                                    —— 以上五个**至少填一个**，否则 400（防无约束全箱扫描）
        mailbox(str, 可选)          邮箱文件夹，默认 INBOX
        offset(int, 可选)           跳过最近 N 封，默认 0
        count(int, 可选)            本次取几封，默认 10
        save_attachments(bool, 可选) 是否下载附件，默认 True
        attachment_dir(str, 可选)   附件根目录

    返回:
        {"code":200,
         "data":{"emails":[...], "total":N, "offset":N, "count":N, "has_more":bool},
         "message":"命中 N 封，返回 M 封"}
        或 {"code":400/500, "data": 位置, "message": 错误描述}

    服务端条件（TEXT/SUBJECT/FROM/SINCE/BEFORE）之外还有客户端兜底二次过滤，
    因为 QQ 等服务端会忽略部分条件并返回全部 —— 见 search.async_filter_ids_client_side。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "find_email")
    keyword = str(data.get("keyword", "") or "").strip()
    subject = str(data.get("subject", "") or "").strip()
    sender = str(data.get("sender", "") or "").strip()
    offset_r = parse_int({"data": data, "key": "offset", "default": 0,
                          "func_name": "find_email"})
    if offset_r.get("code") != 200:
        return offset_r
    count_r = parse_int({"data": data, "key": "count", "default": 10,
                         "func_name": "find_email"})
    if count_r.get("code") != 200:
        return count_r
    if not keyword and not subject and not sender and not data.get("date_from") and not data.get("date_to"):
        return _err("keyword / subject / sender / date_from / date_to 至少填一个", "find_email")
    criteria = []
    if keyword:
        criteria.append(f'TEXT "{keyword}"')          # ⚠ 未转义，见模块 docstring
    if subject:
        criteria.append(f'SUBJECT "{subject}"')        # ⚠ 未转义
    if sender:
        criteria.append(f'FROM "{sender}"')            # ⚠ 未转义
    bc = build_date_criteria({"data": data, "criteria": criteria})
    if bc.get("code") != 200:
        return bc
    criteria = bc["data"]["criteria"]
    sa = data.get("save_attachments")
    save_attachments = True if sa is None or sa == "" else bool(sa)
    attachment_dir = str(data.get("attachment_dir", "") or "").strip()
    return await async_search_mailbox({
        "data": data, "criteria": criteria,
        "offset": offset_r["data"]["value"], "count": count_r["data"]["value"],
        "func_name": "find_email", "save_attachments": save_attachments,
        "attachment_dir": attachment_dir})
