

"""
function="send_email" — 发送邮件（正文/HTML/附件/抄送）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

发件人显示名原实现硬编码为 "MX"（见下方 TODO 注释），未改动以保持行为一致。
"""


import os
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from email.utils import formataddr
from typing import Any, Dict

from aiosmtplib import errors as smtp_errors

from ._connection import async_open_smtp
from ._helper import _err, _ok, check_email_config, error_text, get_email_config, strip_html
from config import get as _cfg_get


async def async_send_email(data: dict = None) -> Dict[str, Any]:
    """
    通过 SMTP 发送电子邮件（异步，aiosmtplib；支持附件与 HTML）。

    入参 (data):
        email(str, 必填)            收件人邮箱地址
        subject(str, 可选)          邮件主题
        content(str, 可选)          纯文本正文
        html(str, 可选)             HTML 正文（有 html 时自动构造 multipart/alternative，
                                    纯文本降级取 content，缺则从 html 剥离）
        attachments(list[str], 可选) 附件文件路径列表（须已存在，逐个校验）

    返回:
        {"code":200, "data":{"email","subject","content","html","attachments"},
         "message":"邮件发送成功"}
        或 {"code":400, "data": 位置, "message": 参数错误}
        或 {"code":500, "data": 位置, "message": 发送失败原因（认证错误单独给指引）}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "send_email")
    email = str(data.get("email", "") or "").strip()
    subject = data.get("subject")
    content = data.get("content")
    html = data.get("html")
    attachments = data.get("attachments")
    if not email:
        return _err("data 中缺少 email 字段", "send_email")
    try:
        cg = get_email_config(data)
        if cg.get("code") != 200:
            return cg
        cfg = cg["data"]
        ck = check_email_config({"cfg": cfg, "func_name": "send_email"})
        if ck.get("code") != 200:
            return ck
        # 校验附件列表
        attach_files = []
        if attachments is not None:
            if not isinstance(attachments, list):
                return _err("attachments 必须是文件路径列表", "send_email")
            for p in attachments:
                p = str(p or "").strip()
                if not p:
                    continue
                if not os.path.isfile(p):
                    return _err(f"附件文件不存在 - {p}", "send_email")
                attach_files.append(p)

        # msg: 邮件体 — 有 HTML 时用 multipart/alternative（纯文本降级 + HTML）；
        #      有附件时用 multipart/mixed（内部再套 alternative）；否则纯文本
        html = str(html or "").strip()
        has_html = bool(html)
        if has_html or attach_files:
            msg = MIMEMultipart()  # mixed：可含 alternative 与附件
            if has_html:
                alt = MIMEMultipart("alternative")
                # 纯文本降级：content 或从 HTML 抽取的纯文本
                sh = strip_html({"html": html})
                if sh.get("code") != 200:
                    return sh
                text = str(content or "").strip() if content else sh["data"]
                alt.attach(MIMEText(text or "", "plain", "utf-8"))
                alt.attach(MIMEText(html, "html", "utf-8"))
                msg.attach(alt)
            else:
                msg.attach(MIMEText(content or "", "plain", "utf-8"))
            for fp in attach_files:
                try:
                    with open(fp, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                except OSError as e:
                    return _err(f"附件读取失败 - {fp}（{e}）", "send_email")
                encoders.encode_base64(part)
                filename = os.path.basename(fp)
                part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", filename))
                msg.attach(part)
        else:
            msg = MIMEText(content or "", "plain", "utf-8")

        # 发件人显示名：原硬编码 "MX"，现读 config.db（mail.from_name，出厂 "MX"）。
        msg["from"] = formataddr((_cfg_get("mail.from_name", "MX"), cfg["host_user"]))
        msg["to"] = email
        msg["Subject"] = subject

        # smtp: 端口决定 TLS 模式（465 隐式 / 其余必须 STARTTLS 升级成功），不占线程
        sr = await async_open_smtp({"cfg": cfg, "timeout": 30})
        if sr.get("code") != 200:
            return sr
        smtp = sr["data"]
        await smtp.login(cfg["host_user"], cfg["password"])
        await smtp.sendmail(cfg["host_user"], email, msg.as_string())
        await smtp.quit()

        return _ok({"email": email, "subject": subject, "content": content,
                    "html": html, "attachments": attach_files}, "邮件发送成功")

    except smtp_errors.SMTPAuthenticationError:
        return {"code": 500, "data": f"{os.path.abspath(__file__)}_send_email",
                "message": "邮件发送失败：认证错误，请检查邮箱账号和授权码"}
    except smtp_errors.SMTPException as e:
        et = error_text({"e": e})
        return {"code": 500, "data": f"{os.path.abspath(__file__)}_send_email",
                "message": f"邮件发送失败：SMTP错误 - {et['data'] if et.get('code') == 200 else e}"}
    except Exception as e:
        et = error_text({"e": e})
        return {"code": 500, "data": f"{os.path.abspath(__file__)}_send_email",
                "message": f"邮件发送失败：{et['data'] if et.get('code') == 200 else e}"}
