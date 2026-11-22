

"""
邮件工具的无状态辅助层。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

四组内容:
  1. 连接配置：data 覆盖 > 环境变量 > 默认值，并做必填项校验
     （get_email_config / check_email_config）
  2. 纯函数：日期换算与范围判定、MIME 头解码、HTML 剥离、整数解析、错误文本
  3. 报文解析（headers/body/attachments）与附件落盘
  4. IMAP 侧纯辅助：响应行解析、SSL 上下文构造、连接错误翻译
     —— 均不建连，实际建连在 _connection.py

本层不碰 socket、不依赖事件循环，可安全复用与单测。
校验器约定（check_email_config）: 通过 → 200；不通过 → 400（原实现返回 {} 表通过，
调用方靠 `if r.get("code")` 判定，现与其余校验器统一）。
"""


import asyncio
import email as email_lib
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Any, Dict


def _where(func_name: str) -> str:
    return f"{os.path.abspath(__file__)}_{func_name}"


def _ok(data=None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, func_name: str = "", code: int = 400, prefix: bool | None = None) -> Dict[str, Any]:
    """错误信封。默认 400 带「错误：」前缀、500 不带；prefix 可显式覆盖。

    路由类提示（如「暂不支持的 function」）原实现无前缀，用 prefix=False 保持。"""
    if prefix is None:
        prefix = code == 400
    return {"code": code, "data": _where(func_name),
            "message": (f"错误：{message}" if prefix else message)}


def parse_fetch_lines(data: dict = None) -> Dict[str, Any]:
    """把 aioimaplib fetch 的 response.lines 解析为 {seq_num: chunk_bytes}。

    入参 (data): lines(list, 必填)  aioimaplib 的 response.lines

    返回:
        {"code":200, "data": {seq_num(int): chunk(bytes)}, "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    aioimaplib 已剥掉 untagged 的 "* " 前缀，literal 数据为 bytes/bytearray：
        b'1 FETCH (BODY[HEADER] {541}'
        bytearray(b'<541 字节数据>')
        b')'
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "parse_fetch_lines")
    lines = data.get("lines")
    if lines is None:
        return _err("缺少 lines 字段（aioimaplib 的 response.lines）", "parse_fetch_lines")
    if not isinstance(lines, (list, tuple)):
        return _err(f"lines 必须是列表，收到 {type(lines).__name__}", "parse_fetch_lines")
    fetch_re = re.compile(rb"^(\d+) FETCH \(")
    items = {}
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if not isinstance(ln, (bytes, bytearray, memoryview)):
            i += 1
            continue
        m = fetch_re.match(bytes(ln))
        if m:
            seq = int(m.group(1))
            chunk = b""
            if b"{" in ln and b"}" in ln and i + 1 < n:
                nxt = lines[i + 1]
                if isinstance(nxt, (bytes, bytearray, memoryview)) and not fetch_re.match(bytes(nxt)):
                    chunk = bytes(nxt)
                    i += 1
            items[seq] = chunk
        i += 1
    return _ok(items)


def get_email_config(data: dict = None) -> Dict[str, Any]:
    """从 data 中读取邮箱连接配置。

    入参 (data): 业务字典，读 email_config 段；未填写字段回退 data 顶层同名字段，
                 再回退环境变量 EMAIL_ADDR/EMAIL_PASSWORD/EMAIL_SMTP_HOST/…，最后默认值

    返回:
        {"code":200, "data": {"host_user","password","smtp_host","smtp_port",
                              "imap_host","imap_port","profile_name"}, "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    profile_name：平台装配时注入的"agent 配置里的邮箱名"，用于邮件附件按来源邮箱分目录；
    未注入时为空，scope 回退用邮箱地址(host_user)做目录名，保证不同邮箱附件不混放。

    端口类字段原实现直接 int()，配置里写坏值会抛 ValueError 穿透；现校验后返回 400。
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "get_email_config")
    cfg = data.get("email_config", {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}

    def _port(val, env, default):
        raw = val or data.get(env.lower().replace("email_", "")) or os.environ.get(env, default)
        if raw in (None, ""):
            raw = default
        if isinstance(raw, (dict, list, tuple, set)):
            return None, _err(f"端口配置必须是整数，收到 {type(raw).__name__}", "get_email_config")
        try:
            return int(raw), None
        except (TypeError, ValueError):
            return None, _err(f"端口配置必须是整数，收到 {raw!r}", "get_email_config")

    smtp_port, e = _port(cfg.get("smtp_port"), "EMAIL_SMTP_PORT", 465)
    if e:
        return e
    imap_port, e = _port(cfg.get("imap_port"), "EMAIL_IMAP_PORT", 993)
    if e:
        return e
    return _ok({
        "host_user": str(cfg.get("email") or cfg.get("host_user") or data.get("email") or data.get("host_user")
                        or os.environ.get("EMAIL_ADDR", "")),
        "password": str(cfg.get("password") or data.get("password") or os.environ.get("EMAIL_PASSWORD", "")),
        "smtp_host": str(cfg.get("smtp_host") or data.get("smtp_host")
                         or os.environ.get("EMAIL_SMTP_HOST", "smtp.qq.com")),
        "smtp_port": smtp_port,
        "imap_host": str(cfg.get("imap_host") or data.get("imap_host")
                         or os.environ.get("EMAIL_IMAP_HOST", "imap.qq.com")),
        "imap_port": imap_port,
        "profile_name": str(cfg.get("profile_name") or data.get("profile_name") or ""),
    })


def check_email_config(data: dict = None) -> Dict[str, Any]:
    """校验邮箱配置是否完整。**校验器**：200 通过 / 400 缺地址或缺授权码。

    入参 (data):
        cfg(dict, 必填)         get_email_config 的产物
        func_name(str, 可选)    错误位置标识里的函数名

    返回: {"code":200, "data":{"checked": True}, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "check_email_config")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段（get_email_config 的产物）", "check_email_config")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "check_email_config")
    func_name = str(data.get("func_name") or "check_email_config")
    if not cfg.get("host_user"):
        return _err("缺少邮箱地址 (email_config.email)", func_name)
    if not cfg.get("password"):
        return _err("缺少授权码 (email_config.password)", func_name)
    return _ok({"checked": True})


def error_text(data: dict = None) -> Dict[str, Any]:
    """异常可读文本。

    入参 (data): e(Exception, 必填)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封

    aioimaplib/asyncio 的 TLS 失败与 TimeoutError 的 str() 为空，
    只打 str 会得到 "fail: " 这种查不出原因的日志，故一律带上类型名。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "error_text")
    if "e" not in data:
        return _err("缺少 e 字段（异常对象）", "error_text")
    e = data["e"]
    if not isinstance(e, BaseException):
        return _err(f"e 必须是异常对象，收到 {type(e).__name__}", "error_text")
    text = str(e).strip()
    return _ok(f"{type(e).__name__}: {text}" if text else type(e).__name__)


def imap_ssl_contexts(data: dict = None):
    """IMAP TLS 尝试序列（**生成器，逐个产出信封**，保持惰性：第一步失败才构造第二个 context）。

    入参 (data): 无字段使用，可为 None 或 {}

    yield:
        {"code":200, "data": None, "message":"success"}     第一步：None 由 aioimaplib 自建默认 context
        {"code":200, "data": SSLContext, "message":"success"} 第二步：放宽密码套件的兼容 context

    实测 imap.139.com:993 的握手失败与 TLS 版本无关：Python 3.13/OpenSSL 3.5 的默认
    安全等级为 2，服务端公告的密码套件被整批筛掉，ClientHello 里没有双方都能用的套件，
    于是直接回 handshake_failure alert（把上限降到 TLS1.2 也仍然失败）。第二步只做
    `set_ciphers("DEFAULT@SECLEVEL=1")`——仍保留证书校验、仍协商到 TLS1.2/AES256-GCM，
    只是把被等级 2 拒掉的套件重新放回候选列表。对等级 2 下能正常握手的服务器
    （QQ/163 等）没有影响：第一次就已成功返回。
    """
    yield _ok(None)
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except (ssl.SSLError, ValueError):
        pass
    yield _ok(ctx)


def imap_connect_error(data: dict = None) -> Dict[str, Any]:
    """超时类异常的真实原因回填。

    入参 (data): e(Exception, 必填), conn(aioimaplib 连接, 可选)
    返回: {"code":200, "data": 异常对象, "message":"success"} 或 400 错误信封

    握手失败已经由 _wait_imap_hello 直接抛出，这里只兜 "连接建立但服务端不发
    greeting" 的纯超时：aioimaplib 的 TimeoutError str() 为空，前端因此只看到
    "fail: "，故再从 _client_task 取一次异常。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "imap_connect_error")
    e = data.get("e")
    if e is None:
        return _err("缺少 e 字段（异常对象）", "imap_connect_error")
    if not isinstance(e, BaseException):
        return _err(f"e 必须是异常对象，收到 {type(e).__name__}", "imap_connect_error")
    conn = data.get("conn")
    if not isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        return _ok(e)
    try:
        task = conn._client_task
        if task.done() and not task.cancelled() and task.exception() is not None:
            return _ok(task.exception())
    except BaseException:
        pass
    return _ok(e)


def parse_int(data: dict = None) -> Dict[str, Any]:
    """动态读取整数参数。**校验器**：200 带 value / 400 非法。

    入参 (data):
        data(dict, 必填)       业务参数字典
        key(str, 必填)         要读的字段名
        default(int, 可选)     缺省值，默认 0
        func_name(str, 可选)   错误位置标识里的函数名
        min_zero(bool, 可选)   True（默认）时负数钳到 0

    返回: {"code":200, "data":{"value": int}, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "parse_int")
    biz = data.get("data")
    if biz is None:
        return _err("缺少 data 字段（业务参数字典）", "parse_int")
    if not isinstance(biz, dict):
        return _err(f"data 必须是字典，收到 {type(biz).__name__}", "parse_int")
    key = data.get("key")
    if not key:
        return _err("缺少 key 字段（要读的字段名）", "parse_int")
    raw_default = data.get("default", 0)
    if isinstance(raw_default, (dict, list, tuple, set)):
        return _err(f"default 必须是整数，收到 {type(raw_default).__name__}", "parse_int")
    try:
        default = int(raw_default)
    except (TypeError, ValueError):
        return _err("default 必须是整数", "parse_int")
    func_name = str(data.get("func_name") or "parse_int")
    clamp = data.get("min_zero", True)

    if key not in biz or biz[key] is None or biz[key] == "":
        return _ok({"value": default})
    raw = biz[key]
    if isinstance(raw, (dict, list, tuple, set)):
        return _err(f"{key} 必须是整数，收到 {type(raw).__name__}", func_name)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _err(f"{key} 必须是整数", func_name)
    return _ok({"value": val if val >= 0 or not clamp else 0})


def imap_date(data: dict = None) -> Dict[str, Any]:
    """把 "YYYY-MM-DD" 转为 IMAP 日期格式 "DD-Mon-YYYY"。

    入参 (data):
        date_str(str, 必填)     日期字符串
        inclusive_end(bool, 可选) True 时加 1 天（BEFORE 是排他的）

    返回:
        {"code":200, "data": str, "message":"success"}      转换成功
        {"code":400, "data": 位置, "message": "错误：date_from/date_to 格式应为 YYYY-MM-DD"}
        （原实现解析失败返回 None，调用方静默跳过该条件——现改 400 显式报错）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "imap_date")
    raw = data.get("date_str")
    if raw is None:
        return _err("缺少 date_str 字段", "imap_date")
    if isinstance(raw, (dict, list, tuple, set)):
        return _err(f"date_str 必须是字符串，收到 {type(raw).__name__}", "imap_date")
    inclusive_end = bool(data.get("inclusive_end", False))
    try:
        d = datetime.strptime(str(raw).strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return _err(f"日期格式应为 YYYY-MM-DD，收到 {str(raw)!r}", "imap_date")
    if inclusive_end:
        d = d + timedelta(days=1)
    return _ok(d.strftime("%d-%b-%Y"))


def in_date_range(data: dict = None) -> Dict[str, Any]:
    """客户端判断邮件日期是否在 [date_from, date_to] 内（统一转 UTC，含首尾）。

    入参 (data):
        date_str(str, 必填)        邮件的 Date 头
        date_from_str(str, 可选)   起始日 YYYY-MM-DD
        date_to_str(str, 可选)     截止日 YYYY-MM-DD

    返回: {"code":200, "data": bool, "message":"success"} 或 400 错误信封

    邮件 Date 头解析失败视为"在范围内"（原语义：不因头部畸形误杀邮件）；
    但 date_from/date_to 本身畸形原实现是 pass 忽略，现仍忽略以保持行为一致
    （它们已在 imap_date 处被校验过）。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "in_date_range")
    date_str = data.get("date_str")
    if date_str is None:
        return _err("缺少 date_str 字段（邮件的 Date 头）", "in_date_range")
    if isinstance(date_str, (dict, list, tuple, set)):
        return _err(f"date_str 必须是字符串，收到 {type(date_str).__name__}", "in_date_range")
    date_from_str = str(data.get("date_from_str") or "").strip()
    date_to_str = str(data.get("date_to_str") or "").strip()
    try:
        dt = email_lib.utils.parsedate_to_datetime(str(date_str))
    except Exception:
        return _ok(True)
    if dt is None:
        return _ok(True)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if date_from_str:
        try:
            d0 = datetime.strptime(date_from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt < d0:
                return _ok(False)
        except ValueError:
            pass
    if date_to_str:
        try:
            d1 = datetime.strptime(date_to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            if dt >= d1:
                return _ok(False)
        except ValueError:
            pass
    return _ok(True)


def decode_header_value(data: dict = None) -> Dict[str, Any]:
    """解码邮件头（Subject/From）的中文编码。

    入参 (data): value(str|None, 可选) 原始头值
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "decode_header_value")
    value = data.get("value")
    if value is None or value == "":
        return _ok("")
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    if not isinstance(value, str):
        return _err(f"value 必须是字符串，收到 {type(value).__name__}", "decode_header_value")
    try:
        parts = decode_header(value)
    except Exception as e:
        return _ok(value)          # 头部畸形时原样返回，不让解码拖垮整封邮件的解析
    result = []
    for content, charset in parts:
        if isinstance(content, bytes):
            charset = charset or "utf-8"
            try:
                result.append(content.decode(charset))
            except Exception:
                result.append(content.decode("utf-8", errors="ignore"))
        else:
            result.append(content)
    return _ok("".join(result))


def strip_html(data: dict = None) -> Dict[str, Any]:
    """把 HTML 转为纯文本（去标签、去空白），用作 HTML 邮件的纯文本降级内容。

    入参 (data): html(str, 可选)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "strip_html")
    html = data.get("html")
    if not html:
        return _ok("")
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")
    if not isinstance(html, str):
        return _err(f"html 必须是字符串，收到 {type(html).__name__}", "strip_html")
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)  # 去 script/style
    text = re.sub(r"(?s)<[^>]+>", "", text)                   # 去标签
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    return _ok(re.sub(r"[ \t]+", " ", text).strip())


def parse_message(data: dict = None) -> Dict[str, Any]:
    """解析邮件对象为字典：主题/发件人/收件人/日期/正文（含 HTML）。

    入参 (data):
        msg(email.Message, 必填)   邮件对象
        with_attachments(bool, 可选) True 时额外收集附件元数据
                                     （payload 为 bytes，由调用方落盘）；
                                     False 跳过附件以省内存（原默认行为）

    返回: {"code":200, "data": {"subject","from_name","from","to","date","body","html",
                                可选 "attachments"}, "message":"success"}
          或 {"code":400, "data": 位置, "message": 错误描述}

    附件识别：part 含 filename 或 Content-Disposition: attachment；inline 嵌图不算附件。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "parse_message")
    msg = data.get("msg")
    if msg is None:
        return _err("缺少 msg 字段（email.Message 对象）", "parse_message")
    if not hasattr(msg, "get") or not hasattr(msg, "get_payload"):
        return _err(f"msg 必须是 email.Message 类对象，收到 {type(msg).__name__}", "parse_message")
    with_attachments = bool(data.get("with_attachments", False))

    from_name, from_addr = email_lib.utils.parseaddr(msg.get("From", "") or "")
    body = ""
    html = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = part.get_content_disposition()
            dh = decode_header_value({"value": part.get_filename() or ""})
            if dh.get("code") != 200:
                return dh
            filename = dh["data"]
            if filename or disposition == "attachment":
                if with_attachments:
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append({
                            "filename": filename or "unnamed",
                            "content_type": ctype,
                            "size": len(payload),
                            "payload": payload,
                        })
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="ignore")
            if ctype == "text/plain" and not body:
                body = text
            elif ctype == "text/html" and not html:
                html = text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="ignore")
            if msg.get_content_type() == "text/html":
                html = text
            else:
                body = text
    if not body and html:
        sh = strip_html({"html": html})
        if sh.get("code") != 200:
            return sh
        body = sh["data"]
    dh_subj = decode_header_value({"value": msg.get("Subject")})
    if dh_subj.get("code") != 200:
        return dh_subj
    dh_from = decode_header_value({"value": from_name})
    if dh_from.get("code") != 200:
        return dh_from
    result = {
        "subject": dh_subj["data"],
        "from_name": dh_from["data"],
        "from": from_addr,
        "to": msg.get("To", ""),
        "date": msg.get("Date", ""),
        "body": body[:2000],
        "html": html[:50000] if html else "",
    }
    if with_attachments:
        result["attachments"] = attachments
    return _ok(result)


def _save_email_attachments(data: dict = None) -> Dict[str, Any]:
    """同步写盘：把附件存到 {attachment_dir}/{邮箱}/{Message-ID}/ 下（两层目录隔离不同邮箱）。

    入参 (data):
        email_id(str, 必填)        形如 "{邮箱}#{Message-ID}"，按首个 # 拆分
        attachment_dir(str, 必填)  落盘根目录
        attachments(list, 必填)    parse_message(with_attachments=True) 的产物

    返回:
        {"code":200, "data": [{"filename","local_path","size","content_type"}, ...],
         "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    目录不存在则创建（含父目录）；文件名重名自动加 (1)(2)…；local_path 为绝对路径。
    邮箱与 Message-ID 里的路径分隔符与 Windows 非法字符一律替换为 _，防穿越目录。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "save_email_attachments")
    email_id = data.get("email_id")
    if email_id is None:
        return _err("缺少 email_id 字段（形如 \"{邮箱}#{Message-ID}\"）", "save_email_attachments")
    if isinstance(email_id, (dict, list, tuple, set)):
        return _err(f"email_id 必须是字符串，收到 {type(email_id).__name__}", "save_email_attachments")
    attachment_dir = data.get("attachment_dir")
    if not attachment_dir:
        return _err("缺少 attachment_dir 字段（落盘根目录）", "save_email_attachments")
    if isinstance(attachment_dir, (dict, list, tuple, set)):
        return _err(f"attachment_dir 必须是字符串，收到 {type(attachment_dir).__name__}",
                    "save_email_attachments")
    attachments = data.get("attachments")
    if attachments is None:
        return _err("缺少 attachments 字段", "save_email_attachments")
    if not isinstance(attachments, (list, tuple)):
        return _err(f"attachments 必须是列表，收到 {type(attachments).__name__}",
                    "save_email_attachments")
    parts = str(email_id or "unknown#unknown").split("#", 1)
    mail_user = re.sub(r'[\\/:*?"<>|]', '_', (parts[0] or "unknown").strip())[:120] or "unknown"
    msg_id = re.sub(r'[\\/:*?"<>|]', '_',
                    (parts[1] if len(parts) > 1 else "unknown").strip().strip("<>").strip())[:120] or "unknown"
    mail_dir = os.path.join(str(attachment_dir), mail_user, msg_id)
    try:
        os.makedirs(mail_dir, exist_ok=True)
    except OSError as e:
        return _err(f"创建附件目录失败: {mail_dir}（{e}）", "save_email_attachments")
    saved = []
    for att in attachments:
        if not isinstance(att, dict):
            return _err(f"attachments 的元素必须是字典，收到 {type(att).__name__}",
                        "save_email_attachments")
        if "payload" not in att:
            return _err(f"附件缺少 payload 字段（filename={att.get('filename')!r}）",
                        "save_email_attachments")
        payload = att["payload"]
        if not isinstance(payload, (bytes, bytearray)):
            return _err(f"附件 payload 必须是 bytes，收到 {type(payload).__name__}",
                        "save_email_attachments")
        fn = str(att.get("filename") or "unnamed")
        safe_fn = re.sub(r'[\\/:*?"<>|]', '_', fn) or "unnamed"
        path = os.path.join(mail_dir, safe_fn)
        if os.path.exists(path):
            base, ext = os.path.splitext(safe_fn)
            i = 1
            while os.path.exists(os.path.join(mail_dir, f"{base}({i}){ext}")):
                i += 1
            path = os.path.join(mail_dir, f"{base}({i}){ext}")
        try:
            with open(path, "wb") as f:
                f.write(bytes(payload))
        except OSError as e:
            return _err(f"附件写盘失败: {path}（{e}）", "save_email_attachments")
        saved.append({
            "filename": os.path.basename(path),
            "local_path": os.path.abspath(path),
            "size": att.get("size", len(payload)),
            "content_type": att.get("content_type", ""),
        })
    return _ok(saved)


def build_date_criteria(data: dict = None) -> Dict[str, Any]:
    """根据 data 中的 date_from/date_to 追加 IMAP 日期过滤条件。

    入参 (data):
        data(dict, 必填)        业务参数（读 date_from/date_to）
        criteria(list, 可选)    待追加的条件列表（不传则新建）

    返回:
        {"code":200, "data": {"criteria": [条件...]}, "message":"success"}
        或 {"code":400, "data": 位置, "message": "错误：日期格式应为 YYYY-MM-DD…"}

    原实现原地 append 并返回同一列表，且日期畸形时**静默跳过该条件**；
    现返回新信封里的列表（同时保留 append 语义，便于调用方沿用），日期畸形改 400 报错。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "build_date_criteria")
    biz = data.get("data")
    if biz is None:
        return _err("缺少 data 字段（业务参数字典）", "build_date_criteria")
    if not isinstance(biz, dict):
        return _err(f"data 必须是字典，收到 {type(biz).__name__}", "build_date_criteria")
    criteria = data.get("criteria")
    if criteria is None:
        criteria = []
    if not isinstance(criteria, list):
        return _err(f"criteria 必须是列表，收到 {type(criteria).__name__}", "build_date_criteria")
    date_from = str(biz.get("date_from", "") or "").strip()
    date_to = str(biz.get("date_to", "") or "").strip()
    if date_from:
        d = imap_date({"date_str": date_from})
        if d.get("code") != 200:
            return d
        criteria.append(f"SINCE {d['data']}")
    if date_to:
        d = imap_date({"date_str": date_to, "inclusive_end": True})
        if d.get("code") != 200:
            return d
        criteria.append(f"BEFORE {d['data']}")
    return _ok({"criteria": criteria})
