

"""
function="receive_email" — 按条件收取邮件（分页）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

分页元数据（total/offset/count/has_more）随本次改造收进 data，
详见 search.py 的契约变更说明。
"""


from typing import Any, Dict

from ._helper import _err, build_date_criteria, parse_int
from config import get as _cfg_get
from .search import async_search_mailbox


async def async_receive_email(data: dict = None) -> Dict[str, Any]:
    """
    通过 IMAP 接收收件箱邮件（异步，aioimaplib），支持翻页与日期过滤。

    入参 (data):
        mailbox(str, 可选)           邮箱文件夹，默认 INBOX
        offset(int, 可选)            跳过最近 N 封，默认 0
        count(int, 可选)             本次取几封，默认 10
        date_from(str, 可选)         起始日期 "YYYY-MM-DD"
        date_to(str, 可选)           结束日期 "YYYY-MM-DD"
        save_attachments(bool, 可选) 是否自动下载附件，默认 True
        attachment_dir(str, 可选)    附件保存根目录，默认 "email_attachments"
                                     （每封邮件按 邮箱/Message-ID 分子目录）

    返回:
        {"code":200,
         "data":{"emails":[每封含 email_id 与 attachments], "total":N,
                 "offset":N, "count":N, "has_more":bool},
         "message":"命中 N 封，返回 M 封"}
        或 {"code":400/500, "data": 位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "receive_email")
    offset_r = parse_int({"data": data, "key": "offset",
                          "default": _cfg_get("mail.receive.offset", 0),
                          "func_name": "receive_email"})
    if offset_r.get("code") != 200:
        return offset_r
    count_r = parse_int({"data": data, "key": "count",
                         "default": _cfg_get("mail.receive.count", 10),
                         "func_name": "receive_email"})
    if count_r.get("code") != 200:
        return count_r
    sa = data.get("save_attachments")
    if sa is None or sa == "":
        sa = _cfg_get("mail.save_attachments", True)
    save_attachments = bool(sa)
    attachment_dir = str(data.get("attachment_dir", "") or "").strip()  # 空串交 search 兜底读 config
    bc = build_date_criteria({"data": data, "criteria": []})
    if bc.get("code") != 200:
        return bc
    return await async_search_mailbox({
        "data": data, "criteria": bc["data"]["criteria"],
        "offset": offset_r["data"]["value"], "count": count_r["data"]["value"],
        "func_name": "receive_email", "save_attachments": save_attachments,
        "attachment_dir": attachment_dir})
