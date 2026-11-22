# -*- coding: utf-8 -*-
"""所有可配置默认值的单一真相源（出厂默认）。

本文件只定义「出厂默认」；运行时实际生效值存在 config.db（SQLite），
由 store.init_db() 首次灌入、之后以库为准（改库不会回流本文件）。

读取优先级（用户 2026-11-22 决策）:
    调用传入 data > config.db（sqlite） > None
    取到 None 时按各函数原有逻辑正常报错，本层不加额外防御。

═══════════════════════════════════════════════════════════════════
进 sqlite 的判据：可调默认值 vs 协议/安全约束
═══════════════════════════════════════════════════════════════════

【进 sqlite｜可调默认值】带业务含义、部署方可按环境调整的缺省值:
    端口、主机名、超时、行数/大小上限、分页缺省、编码、开关（shell/save_attachments…）

【保留常量｜协议与安全约束】绝不进 sqlite，否则违反铁律 #11「能力只能收紧不能放宽」:
    - 安全正则: _IDENT_RE / _READONLY_RE / _FORBIDDEN_RE / _WRITE_START_RE / _FORBIDDEN_WRITE_RE
      （防 SQL 注入与越权写；放进库等于把闸门钥匙交给数据源）
    - 系统目录名单: _TBL_CATALOGS / _SCHEMAISH（拒绝 information_schema/pg_catalog/… 可见）
    - 协议映射: _SQLGLOT_DIALECT / _SQLITE_EXTS（方言与扩展名是协议事实，非可调项）
    - function 白名单: FUNCTIONS / WRITE_FUNCTIONS（路由契约）
    - 进程级可变单例: _HTTP_CLIENT / _CRAWLER / _HOST_CTX / _START_LOCK（运行时状态，非配置）
    - 信封机器默认参: message="success" / func_name="" / code=400（函数签名，非配置）
    - 解析空值防御: data.get("url", "") 里的空串（"取不到即空"，非业务默认值）

这些留在各域源码常量里，改动它们是显式的代码决策，而非"调个配置"。
"""

from typing import Any, Dict, List, NamedTuple, Optional


class Item(NamedTuple):
    """一个配置项。"""
    key: str                      # 点分命名空间，如 "db.port.mysql"
    value: Any                    # 出厂默认值（None 表示"无出厂默认，仅支持库注入"）
    type: str                     # 期望类型: str/int/float/bool/list/dict/any
    category: str                 # 域: db/mail/net/crawl/system/mcp
    note: str                     # 人类可读说明
    secret: bool = False          # True=敏感项（schema 不预置值，仅支持手动注入 config.db）
    hard_max: Optional[float] = None
    # hard_max 非 None = 这是**服务端硬钳制上限**（铁律 #11「能力只能收紧不能放宽」）。
    # 消费点必须走 store.clamp_get(key, hard_max) = min(sqlite值, hard_max)，
    # 即库里的值只能调小（更严），调大无效。出厂 value 恒等于 hard_max。
    # 普通缺省值（超时/主机名/分页缺省）hard_max=None，库值直接生效。


# ── db 域 ────────────────────────────────────────────────────────
DB: List[Item] = [
    Item("db.type", "postgresql", "str", "db", "缺省数据库类型（别名归一后：postgresql/mysql/mongodb/sqlite）"),
    Item("db.port.postgresql", 5432, "int", "db", "PostgreSQL 缺省端口"),
    Item("db.port.mysql", 3306, "int", "db", "MySQL 缺省端口"),
    Item("db.port.mongodb", 27017, "int", "db", "MongoDB 缺省端口"),
    Item("db.max_rows", 500, "int", "db", "单次查询返回行数硬上限（table_data/run_query），用户传更大值被压到此", hard_max=500),
    Item("db.max_affect", 100, "int", "db", "单次写影响行数上限，超限自动回滚（写保护，只可收紧）", hard_max=100),
    Item("db.connect_timeout", 15, "int", "db", "建连超时秒数（asyncpg / sqlite3）"),
    Item("db.mongo.selection_timeout_ms", 10000, "int", "db", "MongoDB 副本集选主超时（毫秒，pymongo serverSelectionTimeoutMS，语义独立于 db.connect_timeout）"),
    Item("db.list_tables.limit", 200, "int", "db", "list_tables 返回条数上限（固定 SQL，防超大列表，只可收紧）", hard_max=200),
    Item("db.table_data.limit", 50, "int", "db", "table_data 未传 limit 时的缺省（仍受 db.max_rows 钳制）"),
    Item("db.run_query.limit", 100, "int", "db", "run_query 未含 LIMIT 时自动补的缺省（仍受 db.max_rows 钳制）"),
    # 连接凭证：无出厂默认，仅支持手动注入 config.db（密钥三不进）
    Item("db.host", None, "str", "db", "缺省主机（不预置；服务端型库必填，缺失仍按原逻辑报「缺少 db_config.host」）", secret=True),
    Item("db.user", None, "str", "db", "缺省账号（不预置）", secret=True),
    Item("db.password", None, "str", "db", "缺省密码（不预置）", secret=True),
    Item("db.database", None, "str", "db", "缺省目标库名（不预置）", secret=True),
    Item("db.sqlite.dir", None, "str", "db", "SQLite 文件夹模式缺省目录（不预置）"),
    Item("db.sqlite.path", None, "str", "db", "SQLite 单文件模式缺省文件（不预置）"),
]

# ── mail 域 ──────────────────────────────────────────────────────
MAIL: List[Item] = [
    Item("mail.smtp.host", "smtp.qq.com", "str", "mail", "SMTP 服务器缺省主机"),
    Item("mail.smtp.port", 465, "int", "mail", "SMTP 缺省端口（465 隐式 TLS；非 465 必须 STARTTLS 升级成功）"),
    Item("mail.imap.host", "imap.qq.com", "str", "mail", "IMAP 服务器缺省主机"),
    Item("mail.imap.port", 993, "int", "mail", "IMAP 缺省端口（143 为明文，本平台拒绝）"),
    Item("mail.connect_timeout", 30, "int", "mail", "IMAP/SMTP 建连超时秒数"),
    Item("mail.mailbox", "INBOX", "str", "mail", "缺省邮箱文件夹"),
    Item("mail.receive.offset", 0, "int", "mail", "receive_email 缺省跳过最近 N 封"),
    Item("mail.receive.count", 10, "int", "mail", "receive_email 缺省取几封"),
    Item("mail.find.offset", 0, "int", "mail", "find_email 缺省跳过最近 N 封"),
    Item("mail.find.count", 10, "int", "mail", "find_email 缺省取几封"),
    Item("mail.save_attachments", True, "bool", "mail", "是否默认下载附件"),
    Item("mail.attachment_dir", "email_attachments", "str", "mail", "附件落盘根目录缺省"),
    Item("mail.body_limit", 2000, "int", "mail", "正文截断字符数"),
    Item("mail.html_limit", 50000, "int", "mail", "HTML 截断字符数"),
    Item("mail.from_name", "MX", "str", "mail", "发件人显示名（原实现硬编码，现可配）"),
    # 账号凭证：无出厂默认，仅支持手动注入
    Item("mail.account.user", None, "str", "mail", "缺省发/收邮箱地址（不预置）", secret=True),
    Item("mail.account.password", None, "str", "mail", "缺省授权码（不预置）", secret=True),
    Item("mail.profile_name", None, "str", "mail", "附件分目录用的邮箱名（不预置，缺失回退邮箱地址）"),
]

# ── net 域（基础网络）────────────────────────────────────────────
NET: List[Item] = [
    Item("net.http_client.timeout", 30, "int", "net", "共享 httpx 客户端建连超时秒数"),
    Item("net.http_client.max_connections", 1000, "int", "net", "连接池最大连接数"),
    Item("net.http_client.max_keepalive", 200, "int", "net", "连接池最大保活连接数"),
    Item("net.timeout.default", 5, "int", "net", "get_timeout 未传时的缺省超时秒数"),
    Item("net.http_request.timeout", 10, "int", "net", "http_request 未传 timeout 的缺省"),
    Item("net.http_request.max_length", 10000, "int", "net", "http_request 响应体截断字符数"),
    Item("net.http_request.method", "GET", "str", "net", "http_request 缺省方法"),
    Item("net.http_request.response_type", "auto", "str", "net", "http_request 缺省响应解析方式"),
    Item("net.download.timeout", 30, "int", "net", "download 未传 timeout 的缺省"),
    Item("net.download.max_size", 0, "int", "net", "download 大小上限字节数，0=不限"),
    Item("net.download.report_every", 1048576, "int", "net", "download 每多少字节上报一次进度"),
    Item("net.verify", True, "bool", "net", "是否校验 TLS 证书（False 会禁用校验，慎用）"),
    Item("net.weather_wttr.format", "j1", "str", "net", "wttr.in 缺省格式"),
]

# ── crawl 域（高级网络/浏览器渲染，物理在 net/ 下，key 用 crawl.）──
CRAWL: List[Item] = [
    Item("crawl.page_timeout_max", 120000, "int", "crawl", "page_timeout 服务端钳制上限（毫秒），只可收紧", hard_max=120000),
    Item("crawl.semaphore_max", 5, "int", "crawl", "并发信号量钳制上限，只可收紧", hard_max=5),
    Item("crawl.recycle_max", 50, "int", "crawl", "浏览器回收周期钳制上限（页数），只可收紧", hard_max=50),
    Item("crawl.batch_urls_max", 20, "int", "crawl", "crawl_many 单次 URL 数上限，超过直接拒，只可收紧", hard_max=20),
    Item("crawl.deep_pages_max", 30, "int", "crawl", "deep_crawl 总页数钳制上限，只可收紧", hard_max=30),
    Item("crawl.output_max_length_default", 20000, "int", "crawl", "输出正文缺省截断字符数，0=不限"),
    Item("crawl.output_format", "markdown", "str", "crawl", "抓取输出缺省格式（markdown/html/links）"),
    Item("crawl.deep_crawl.max_depth", 2, "int", "crawl", "deep_crawl 缺省爬取深度"),
    Item("crawl.deep_crawl.total_limit", 10, "int", "crawl", "deep_crawl 缺省总页数（受 crawl.deep_pages_max 钳制）"),
    Item("crawl.deep_crawl.concurrent_limit", 4, "int", "crawl", "deep_crawl 缺省并发（受 crawl.semaphore_max 钳制）"),
    Item("crawl.screenshot.wait_ms", 1000, "int", "crawl", "screenshot 截图前等待毫秒数"),
    Item("crawl.links_limit", 200, "int", "crawl", "output_format=links 时每类链接条数上限（防超大，只可收紧）", hard_max=200),
    Item("crawl.extraction.type", "css", "str", "crawl", "结构化抽取缺省策略（css/xpath/regex）"),
    Item("crawl.apply_wait_for.min_ms", 1000, "int", "crawl", "wait_for 轮询最短等待（下限保护）"),
    Item("crawl.apply_wait_for.cap_ms", 15000, "int", "crawl", "wait_for 轮询最长等待上限，只可收紧", hard_max=15000),
    Item("crawl.allow_headed", False, "bool", "crawl", "是否允许有头浏览器（平台装配可注入覆盖）"),
]

# ── system 域 ────────────────────────────────────────────────────
SYSTEM: List[Item] = [
    Item("system.cmd_run.timeout", 30, "int", "system", "cmd_run 执行总超时秒数"),
    Item("system.cmd_run.shell", True, "bool", "system", "是否用 shell 执行"),
    Item("system.cmd_run.capture_output", True, "bool", "system", "是否捕获 stdout/stderr"),
    Item("system.cmd_run.text", True, "bool", "system", "以文本模式返回"),
    Item("system.cmd_run.encoding", "utf-8", "str", "system", "输出编码"),
    Item("system.cmd_run.errors", "ignore", "str", "system", "编码错误处理"),
    Item("system.cmd_run.output_limit", 0, "int", "system", "stdout 最大字符数，0=不限"),
    Item("system.cmd_run.output_part", "tail", "str", "system", "超限时保留哪部分: head/tail/middle"),
]

# ── mcp 域 ───────────────────────────────────────────────────────
# 注意：mcp 只有 1 个域级默认。timeout/execution_timeout/is_stateful 等都是
# **per-server 配置**（从 mcpServers 每个 server 段读，见 build_client），
# 不是域级缺省，放进 schema 会成为改了无效的死配置，故不收。
MCP: List[Item] = [
    # config_path 出厂默认是"本包目录下 mcp_servers.json"，含 __file__，
    # 故 value=None，由 store._expand_default 在灌库时按运行时上下文展开。
    Item("mcp.config_path", None, "str", "mcp",
         "data['mcp']=True 时读的缺省配置文件路径（可指到 /etc/agent/mcp.json 等，免改源码）"),
]

# 全部配置项（顺序即灌库顺序）
ALL: List[Item] = DB + MAIL + NET + CRAWL + SYSTEM + MCP

# key → Item 索引
BY_KEY: Dict[str, Item] = {it.key: it for it in ALL}

# 敏感项（schema 不预置值，仅支持手动注入 config.db）
SECRET_KEYS: List[str] = [it.key for it in ALL if it.secret]


def keys_by_category(category: str) -> List[str]:
    """按域取 key 列表。"""
    return [it.key for it in ALL if it.category == category]


def describe(key: str) -> Optional[str]:
    """取某 key 的人类可读说明；未知 key 返回 None。"""
    it = BY_KEY.get(key)
    return it.note if it else None


# ── 导入即自检：schema 本身的契约错误应尽早崩（配置管理层的编程错误）──
def _selfcheck() -> None:
    seen = set()
    for it in ALL:
        if it.key in seen:
            raise ValueError(f"schema 重复 key: {it.key}")
        seen.add(it.key)
        if not it.key.startswith(it.category + "."):
            raise ValueError(f"schema key 前缀与 category 不符: {it.key} (category={it.category})")
        # 敏感项出厂必须为 None（不得在源码里预置任何真实凭证）
        if it.secret and it.value is not None:
            raise ValueError(f"敏感项出厂值必须为 None: {it.key}")
        # 钳制项出厂必须等于硬上限（否则 min() 语义混乱）
        if it.hard_max is not None and it.value != it.hard_max:
            raise ValueError(f"钳制项出厂值须等于 hard_max: {it.key} "
                             f"(value={it.value}, hard_max={it.hard_max})")
        if it.hard_max is not None and it.type not in ("int", "float"):
            raise ValueError(f"钳制项只支持数值型: {it.key} (type={it.type})")


_selfcheck()
