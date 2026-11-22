"""AI 工具目录（用户 AI 工具权限的单一真相源）。"""

TOOL_GROUPS: list[dict] = [
    {
        "name": "basic",
        "label": "基础工具",
        "description": "读取、搜索、编辑文件与基础交互",
        "tools": [
            {"name": "Read", "label": "读取文件", "description": "读取本地文件内容"},
            {"name": "Write", "label": "写入文件", "description": "创建或覆盖文件"},
            {"name": "Edit", "label": "编辑文件", "description": "按片段修改文件"},
            {"name": "Glob", "label": "文件匹配", "description": "按通配符查找文件"},
            {"name": "Grep", "label": "内容搜索", "description": "按正则搜索文件内容"},
        ],
    },
    {
        "name": "db",
        "label": "数据库工具",
        "description": "查询与写入 PostgreSQL / MySQL / MongoDB / SQLite",
        "tools": [
            {"name": "async_db_tools", "label": "数据库查询", "description": "列库、表结构、只读查询"},
            {"name": "async_db_write_tools", "label": "数据库写入", "description": "插入、更新、删除"},
        ],
    },
    {
        "name": "net",
        "label": "网络工具",
        "description": "HTTP 请求、下载、网页抓取与截图",
        "tools": [
            {"name": "async_req_tools", "label": "HTTP / 下载", "description": "请求、天气、下载"},
            {"name": "async_crawl_tools", "label": "网页抓取", "description": "浏览器渲染、截图、PDF"},
        ],
    },
    {
        "name": "mail",
        "label": "邮件工具",
        "description": "收发邮件、附件与搜索",
        "tools": [
            {"name": "async_mail_tools", "label": "邮件收发", "description": "发信、收信、查找"},
        ],
    },
    {
        "name": "mcp",
        "label": "MCP 工具",
        "description": "外部 MCP 服务",
        "tools": [
            {"name": "async_mcp_tools", "label": "MCP 客户端", "description": "连接外部 MCP 服务"},
        ],
    },
    {
        "name": "system",
        "label": "系统工具",
        "description": "Shell 命令执行",
        "tools": [
            {"name": "async_sys_tools", "label": "Shell 命令", "description": "执行系统命令"},
        ],
    },
    {
        "name": "rag",
        "label": "知识库工具",
        "description": "知识库写入、检索与删除",
        "tools": [
            {"name": "async_rag_tools", "label": "RAG 检索", "description": "写入/检索/删除知识库"},
        ],
    },
]

GROUP_MAP = {group["name"]: group for group in TOOL_GROUPS}


def all_items() -> list[dict]:
    return [
        {"group": group["name"], "tool": tool["name"]}
        for group in TOOL_GROUPS
        for tool in group["tools"]
    ]


def is_valid(group: str, tool: str = "") -> bool:
    if group not in GROUP_MAP:
        return False
    if not tool:
        return True
    return any(item["name"] == tool for item in GROUP_MAP[group]["tools"])
