

"""
function="find_email" — 按条件查找邮件（分页）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

分页元数据（total/offset/count/has_more）随本次改造收进 data，
详见 search.py 的契约变更说明。

⚠️ IMAP 搜索表达式安全（A17 已修）:
    keyword/subject/sender 用 _imap_quote 转义 `\\` 与 `"` 后再拼进 quoted string。
    输入 `x" OR (UNSEEN OR DELETED)"` 现在是单个字面量，不再能闭合引号追加条件。
"""


from typing import Any, Dict

from ._helper import _err, build_date_criteria, parse_int
from config import get as _cfg_get
from .search import async_search_mailbox


def _imap_quote(value: str) -> str:
    """把用户输入转成 IMAP quoted string 的安全内容。

    RFC 3501 quoted string 只认 `\\` 与 `\"` 两种转义。先转义反斜杠再转义双引号，
    避免 `\\"` 被解释成“转义反斜杠 + 结束引号”。修 A17：关键字不再能闭合引号
    追加 `OR (...)` 扩大搜索范围。
    """
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


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
    offset_r = parse_int({"data": data, "key": "offset",
                          "default": _cfg_get("mail.find.offset", 0),
                          "func_name": "find_email"})
    if offset_r.get("code") != 200:
        return offset_r
    count_r = parse_int({"data": data, "key": "count",
                         "default": _cfg_get("mail.find.count", 10),
                         "func_name": "find_email"})
    if count_r.get("code") != 200:
        return count_r
    if not keyword and not subject and not sender and not data.get("date_from") and not data.get("date_to"):
        return _err("keyword / subject / sender / date_from / date_to 至少填一个", "find_email")
    criteria = []
    if keyword:
        criteria.append(f'TEXT "{_imap_quote(keyword)}"')
    if subject:
        criteria.append(f'SUBJECT "{_imap_quote(subject)}"')
    if sender:
        criteria.append(f'FROM "{_imap_quote(sender)}"')
    bc = build_date_criteria({"data": data, "criteria": criteria})
    if bc.get("code") != 200:
        return bc
    criteria = bc["data"]["criteria"]
    sa = data.get("save_attachments")
    if sa is None or sa == "":
        sa = _cfg_get("mail.save_attachments", True)
    save_attachments = bool(sa)
    attachment_dir = str(data.get("attachment_dir", "") or "").strip()
    return await async_search_mailbox({
        "data": data, "criteria": criteria,
        "offset": offset_r["data"]["value"], "count": count_r["data"]["value"],
        "func_name": "find_email", "save_attachments": save_attachments,
        "attachment_dir": attachment_dir})
