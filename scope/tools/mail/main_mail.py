

"""
mail 工具统一入口与 function 路由。

原 async_email_tools.py 拆分而来：本文件只保留调度，辅助与功能各归其模块。
新增功能：写一个 <function>.py，并在本文件路由里加一个 if function == "..." 分支。

注意: function="to_mail" 是 send_email 的兼容别名（原代码即如此），勿删。

模块布局:
    main_mail.py     本文件，async_email_tools 入口与路由
    _helper.py       无状态辅助：配置解析、日期/头/整数解析、HTML 剥离、
                     报文解析与附件落盘、IMAP 响应行解析、SSL 上下文、错误翻译
    _connection.py   IMAP/SMTP 连接生命周期（建连、握手、放弃）
    search.py        mailbox 检索与客户端侧二次过滤（receive/find 共用）
    send_email.py    function="send_email"（含别名 to_mail）
    receive_email.py function="receive_email"
    find_email.py    function="find_email"
"""


import asyncio

from typing import Dict, Any

from ._helper import _err
from .find_email import async_find_email
from .receive_email import async_receive_email
from .send_email import async_send_email



async def async_email_tools(data: dict) -> Dict[str, Any]:
    """
    邮件工具统一入口（异步：SMTP 用 aiosmtplib、IMAP 用 aioimaplib，原生异步 I/O 不占线程池）。
    data["function"] 决定执行哪个功能，其余字段为该功能的业务参数（全部动态参数形式）。

    参数 (data 字典):
        data: {"function": 要执行的功能名称, # 必填
               "email_config": 邮箱连接配置(dict, 可选, 可放公共配置段),
               ...功能业务参数见下方各功能说明}

    公共配置段 email_config（所有功能共用，也可把字段直接放 data 顶层）:
        email(str)        邮箱完整地址，如 "184586774@qq.com"
        password(str)     授权码（QQ邮箱在设置-账户中生成）
        smtp_host(str)    发送服务器（必填；调用或 config.db 都没有则报错）
        smtp_port(int)    发送端口（必填；同上）
        imap_host(str)    接收服务器（必填；同上）
        imap_port(int)    接收端口（必填；同上）

    支持的功能与业务参数:
        ① function="send_email" — 通过 SMTP 发送电子邮件（支持附件与 HTML）
            业务参数:
                email(str, 必填)      收件人邮箱地址
                subject(str, 可选)    邮件主题
                content(str, 可选)    邮件正文（纯文本；与 html 同时提供时作为 HTML 客户端的降级内容）
                html(str, 可选)       邮件正文（HTML 格式，如 "<h1>标题</h1><p>内容</p>"）
                attachments(list, 可选) 附件列表，元素为本地文件路径字符串，
                                        如 ["/root/git_app/report.pdf", "a.txt"]
            说明: html 与 content 二选一或同时给（同时给时构建 multipart/alternative，客户端优先展示 HTML）；
                  只给 html 时自动附带纯文本降级版本。
            返回: {"code":200, "data": 发件详情, "message":"邮件发送成功"}

        ② function="receive_email" — 接收收件箱邮件（IMAP，支持翻页与日期过滤，自动下载附件）
            业务参数:
                mailbox(str, 可选)    邮箱文件夹，默认 "INBOX"
                offset(int, 可选)     跳过最近 N 封（从最新一封往后数），默认 0
                count(int, 可选)      本次取几封（每页条数），默认 10
                date_from(str, 可选)  起始日期，格式 "YYYY-MM-DD"，只取该日(含)之后的邮件
                date_to(str, 可选)    结束日期，格式 "YYYY-MM-DD"，只取该日(含)之前的邮件
                save_attachments(bool, 可选) 是否自动下载附件到本地，默认 True
                attachment_dir(str, 可选) 附件保存根目录，默认 "email_attachments"，
                                          每封邮件按 "{邮箱}/{Message-ID}" 分子目录存放
            附件说明: 邮件含附件时，按 {attachment_dir}/{来源邮箱名}/{Message-ID}/ 落盘
                     （来源邮箱名取 agent 配置里的 profile name，未配置则回退邮箱地址；
                      目录不存在自动创建，文件名重名加 (1)(2)…），返回结果每封邮件增加
                     email_id（"{邮箱名}#{Message-ID}"，区分来源邮箱避免 ID 冲突）与
                     attachments 字段 [{filename, local_path, size, content_type}]。
                     save_attachments=False 时不下载，attachments 为空列表。
            返回: {"code":200, "data": 邮件列表, "total": 命中总数, "offset":..., "count":..., "has_more": 是否还有下一页}

        ③ function="find_email" — 按条件查找邮件（支持翻页与日期过滤，自动下载附件）
            业务参数（keyword/subject/sender 至少填一个）:
                keyword(str, 可选)    全文搜索关键词
                subject(str, 可选)    按主题搜索
                sender(str, 可选)     按发件人搜索
                offset(int, 可选)     跳过最近 N 条命中，默认 0
                count(int, 可选)      本次取几封，默认 10
                date_from(str, 可选)  起始日期 "YYYY-MM-DD"
                date_to(str, 可选)    结束日期 "YYYY-MM-DD"
                save_attachments(bool, 可选) 是否自动下载附件到本地，默认 True
                attachment_dir(str, 可选) 附件保存根目录，默认 "email_attachments"
            附件说明与返回同 receive_email

    调用示例:
        async_email_tools({"function":"send_email", "email":"xxx@139.com", "subject":"主题", "content":"正文",
                     "email_config":{"email":"184586774@qq.com","password":"授权码"}})
        async_email_tools({"function":"receive_email", "offset":0, "count":10, "date_from":"2026-07-01",
                     "email_config":{"email":"184586774@qq.com","password":"授权码"}})
        async_email_tools({"function":"find_email", "keyword":"合同", "sender":"abc@qq.com", "offset":0, "count":5,
                     "email_config":{"email":"184586774@qq.com","password":"授权码"}})

    翻页说明: offset=0,count=10 → 最新10封；offset=10,count=10 → 再往前10封。has_more=false 表示已到最后一页。

    返回:
        {"code": 200, "data": ..., "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_email_tools")
    raw_fn = data.get("function", "")
    if isinstance(raw_fn, (dict, list, tuple, set)):
        return _err(f"function 必须是字符串，收到 {type(raw_fn).__name__}", "async_email_tools")
    function = str(raw_fn or "").strip()
    if not function:
        return _err("data 中缺少 function 字段", "async_email_tools")
    if function == "send_email":
        return await async_send_email(data)
    if function == "receive_email":
        return await async_receive_email(data)
    if function == "find_email":
        return await async_find_email(data)
    if function == "to_mail":                      # send_email 的兼容别名，勿删
        return await async_send_email(data)
    return _err(f"暂不支持的 function: {function}，支持: send_email / receive_email / find_email",
                "async_email_tools", prefix=False)



if __name__ == "__main__":
    # 邮件工具测试：参数校验/分发（不发真实邮件、不硬编码授权码）
    import asyncio

    async def main():
        print("== 参数校验 ==")
        print(await async_email_tools({"function": "send_email"}))
        print(await async_email_tools({"function": "receive_email", "count": "abc"}))
        print(await async_email_tools({"function": "find_email"}))
        print(await async_email_tools({"function": "bad"}))
        print("== 配置校验（缺 email/password） ==")
        print(await async_email_tools({"function": "receive_email", "email_config": {"email": "x@qq.com"}}))
        # 真实收发需在 data.email_config 传邮箱与授权码，如:
        # await async_email_tools({"function": "receive_email", "count": 3,
        #              "email_config": {"email": "xxx@qq.com", "password": "授权码"}})

    asyncio.run(main())
