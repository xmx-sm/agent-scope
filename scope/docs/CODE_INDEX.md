# scope CODE_INDEX

`tools/` 与 `config/` 下每个文件的作用、行数与依赖关系。找文件、改代码前先在此定位。
工具层五域详列于第二～六节；基础设施层 `config/` 见第七节（详解见《配置说明.md》）。

五个域共 **39 个文件 / 127 个顶层函数 / 6726 行**，由 `agent_study/scope/tools` 的 6 个单体文件（3335 行）改造而来。
（⑤ 收尾后如需逐文件行数，以 `wc -l tools/*/*.py` 为准；下表为各轮改造时的快照。）
（原 `crawl` 独立成域，后经用户决策**合并回 net**，定位为「高级网络请求」：）

| 阶段 | 文件 | 行数 | 说明 |
|---|---|---|---|
| ① AST 拆分 | 37 | 3906 | +571：各模块 docstring 与重新分布的 import |
| ② 入参与错误返回统一 | 37 | 6550 | +2644：`if` 校验分支、信封机器、data 解包、docstring 补入参表 |
| ③ crawl 合并回 net | 39 | 6558 | 目录重组：`crawl/_helper.py` 拆为 `_envelope`/`_fs`/`_render`，旧信封层 3 个符号丢弃（19→16 个信封机器），download 补闸门 |
| ④ config 层 | +4 | +616 | 新增基础设施层 `scope/config/`（schema/store/merge/__init__），五域硬编码默认值收敛到 config.db；工具层文件数不变，但 21 个文件新增 `from config import …` |
| ⑤ 收尾优化 | 39 | 6726 | 修 A17（IMAP 引号转义）/C2（`list_databases` 白名单）；net 读写闸门合并为 `_check_fs`；连接/身份类参数去源码兜底 |

统一约定见《工具拆分规范.md》（含第五、六条规则），接口契约见《参数说明.md》〇′ 节，默认配置见《配置说明.md》。

### 每域的文件角色

除 `main_<域>.py` 与功能文件外，每域都有一层**信封机器**（`_where`/`_ok`/`_err`），
它们是规则 6 的豁免对象——签名保持原生形态，因为造信封的机器不能自己是信封。
下表符号清单里的 `_where`/`_ok`/`_err` 即此。

---

## 一、目录总览

全仓 **63 个 Python 文件 / 10619 行**：工具层 `tools/` 40 文件 + 基础设施层 `config/` 4 文件 + 框架层 `llm/`、`media/`、`rag/`、`common/`。
框架层中 `llm/`（模型工厂）、`media/`（TTS/ASR 落盘服务）、`rag/`（SQLite 本地知识库 + `tools/rag` + 官方 `KnowledgeBase`/`RAGMiddleware`）与 `agent/`（子智能体）已实现；其余 `middleware/`、`permission/`、`skills/`、`storage/` 尚未实现，缺口与规划见《框架层规划.md》。

```
tools/
├── system/      3 文件    6 函数    364 行   系统工具（cmd_run）
├── net/        17 文件   30 函数   1722 行   网络工具（基础 HTTP/天气/下载 + 高级浏览器渲染/截图/PDF）
├── mail/        7 文件   27 函数   1579 行   邮件工具（收发 / 查找）
├── mcp/         3 文件    8 函数    360 行   MCP 客户端
└── db/          9 文件   46 函数   2533 行   数据库读写（PG / MySQL / MongoDB / SQLite）
       合计        39 文件  127 函数   6726 行
```

每个域的形状一致：

| 角色 | 命名 | 职责 | 是否套信封 |
|------|------|------|-----------|
| 入口 | `main_<域>.py` | **只做** `data["function"]` 路由，不含业务逻辑 | ✅ |
| 无状态辅助 | `_helper.py`（或 `_common.py` / `_client.py` / `_config.py`） | 常量、纯函数、配置解析、错误包装 | ✅ |
| **信封机器** | 同上文件内的 `_where` / `_ok` / `_err` | 造信封 / 定位错误位置；**签名保持原生**（规则 6 豁免①） | 它们就是信封本身 |
| 有状态/连接 | `_crawler.py` / `_connection.py` / `executors.py` 等 | 进程级单例、驱动建连、SSL 生命周期 | ✅，`data` 直接放活对象 |
| 功能 | `<function>.py` | 一个 function 一个文件 | ✅ |
| **纯副作用** | 散在 `_helper.py` / `_crawler.py` / `_connection.py` | 只改入参对象状态，无数据可返回（**6 个**，规则 6 豁免②） | ❌ 返回 None，坏入参 fail-fast 抛 `ValueError` |

---

## 二、`tools/system/` — 系统工具

| 文件 | 行数 | 函数数 | 符号 | 依赖 |
|------|------|--------|------|------|
| `main_sys.py` | 87 | 1 | `async_sys_tools` | `_common`, `cmd_run` |
| `_common.py` | 99 | 4 | `_where`, `_ok`, `_err`, `get_common_args` | — |
| `cmd_run.py` | 178 | 1 | `async_cmd_run` | `_common` |

链状，无分支。`_common.py` 收纳 subprocess 参数归一化（`timeout`/`shell`/`capture_output`/`text`/`encoding`/`errors`）与信封机器。

`get_common_args` 第二轮改了签名：原 `(data, func_name)` 两个位置参数 → `{"data": ..., "func_name": ...}`，
且返回从**半信封**（成功时只有 `{"value": ...}`，无 code/message）升级为完整信封。

`main_sys.py` 保留 `if __name__ == "__main__"` 自测块（11 个用例），用 `python -m tools.system.main_sys` 跑。

---

## 三、`tools/net/` — 网络工具

| 文件 | 行数 | 函数数 | 符号 | 依赖 |
|------|------|--------|------|------|
| `main_crawl.py` | 118 | 1 | `async_crawl_tools` | `_envelope`, `_fs`, `crawl`, `crawl_many`, `deep_crawl`, `extract_pdf`, `screenshot` |
| `main_net.py` | 142 | 1 | `async_req_tools` | `_envelope`, `cityid`, `download`, `http_request`, `weather`, `weather_wttr` |
| `_client.py` | 137 | 2 | `get_http_client`, `get_timeout` | `_envelope` |
| `_crawler.py` | 82 | 2 | `_get_crawler`, `_reset_crawler` | `_envelope` |
| `_envelope.py` | 45 | 3 | `_where`, `_ok`, `_err` | — |
| `_fs.py` | 127 | 4 | `configure_fs_policy`, `_to_bool_tuple`, `_check_write`, `_check_read` | `_envelope` |
| `_render.py` | 293 | 7 | `_valid_names`, `_build_config`, `_apply_wait_for`, `_clamp_configs`, `_apply_extraction`, `_pick_output`, `_fail` | `_envelope`, `_fs` |
| `cityid.py` | 44 | 1 | `async_getcityid` | `_client`, `_envelope` |
| `crawl.py` | 98 | 1 | `async_crawl` | `_crawler`, `_envelope`, `_render` |
| `crawl_many.py` | 49 | 1 | `async_crawl_many` | `_envelope`, `_render`, `crawl` |
| `deep_crawl.py` | 110 | 1 | `async_deep_crawl` | `_crawler`, `_envelope`, `_render` |
| `download.py` | 109 | 1 | `async_req_download` | `_client`, `_envelope`, `_fs` |
| `extract_pdf.py` | 83 | 1 | `async_extract_pdf` | `_envelope`, `_fs`, `_render` |
| `http_request.py` | 106 | 1 | `async_http_request` | `_client`, `_envelope` |
| `screenshot.py` | 87 | 1 | `async_screenshot` | `_envelope`, `_fs`, `crawl` |
| `weather.py` | 44 | 1 | `async_get_weather` | `_client`, `_envelope` |
| `weather_wttr.py` | 48 | 1 | `async_get_weather_wttr` | `_client`, `_envelope` |


net 是**唯一有两个入口的域**：`main_net.py`（基础网络）与 `main_crawl.py`（高级网络/浏览器渲染）。
装配时两者挂进**同一个** `ToolGroup("net")`，模型一次 `reset_tools` 即可同时拿到——
这是原 `agent_study/tools/__init__.py` 的做法（`net_tools.append(FunctionTool(async_crawl_tools))`，
描述文案「网络工具…pro 网页抓取」），本次合并只是把目录结构对齐这个既有意图。

**为什么不合并成单个 dispatcher**：平台需要能单独停用 crawl（慢、贵、起浏览器）而保留 http_request；
合并会让黑盒 schema 的参数面翻倍，模型更易填错。

### 辅助层四段（其他域最多三段）

| 文件 | 职责 | 为何独立 |
|------|------|---------|
| `_envelope.py` | `_where`/`_ok`/`_err` 信封机器 | net 有四个辅助文件，若把信封塞进其中一个，其余三个都要横向依赖它（文件闸门依赖 httpx 客户端单例，语义不成立）。**六域里唯一独立成文件的信封层** |
| `_client.py` | httpx 单例 `_HTTP_CLIENT`/`_HTTP_CLIENT_INSECURE` + `get_timeout` | 进程级可变全局，依赖 `global` 语义 |
| `_fs.py` | 文件闸门 `_HOST_CTX`/`configure_fs_policy`/`_check_write`/`_check_read`/`_to_bool_tuple` | **net 域共用层**，download 与 screenshot 同走此闸门 |
| `_render.py` | crawl4ai 配置构建/钳制/输出抽取 + 上限常量 | 无状态，与连接层无关 |

`_crawler.py` 是浏览器单例（有状态），归功能支撑而非辅助层。

⚠️ **合并修掉的不对称**：合并前 `download` 的 `save_path` 直接 `open(...,"wb")` 落盘、
**完全不过闸门**，而同域的 `screenshot` 走 `_check_write`——同一能力两种命运，
平台注入的租户约束对 download 失效（可写到 uploads 根之外）。现两者共用 `_fs.py`，
同一路径判定一致（已验证：cwd 外两侧均拒、cwd 内两侧均放行）。

⚠️ **`_fs.py` 的外部契约未变**：平台注入的回调仍是 `check_write(path) -> (bool, str)` 元组。
`_to_bool_tuple` 在内部转信封，同时兼容回调直接返回信封的写法，**平台侧无需改注入代码**。

⚠️ **`_err` 参数顺序曾是跨域陷阱**：合并前两域签名倒置——
`crawl._err(where, msg)` vs `net._err(message, func_name, code, prefix)`，
跨文件复制粘贴必错且不报错（两个 str 参数）。现全库统一为后者。

### 纯副作用豁免（6 个里的 5 个在 net）

`configure_fs_policy` / `_apply_wait_for` / `_clamp_configs` / `_apply_extraction`（`_render.py`、`_fs.py`）
与 `_reset_crawler`（`_crawler.py`）。它们只改入参对象状态、无数据可返回，
故入参改 data 而**不套信封**，坏入参 fail-fast 抛 `ValueError`。

### 两处内部复用

`crawl_many` 与 `screenshot` 都调 `crawl`（不是各自重写抓取逻辑）；
`_render._clamp_configs` 调 `_fs._check_write`（downloads_path 越界抛 ValueError，由调用方转 400）。

### 依赖图

```
_envelope  ←  _client   ←  {weather, cityid, weather_wttr, http_request, download}
     ↑           ↑                                              ↓
     └── _fs  ←─┴──  文件闸门                        main_net（基础网络入口）
     ↑
     └── _render ← _crawler ← {crawl, deep_crawl} ← {crawl_many, screenshot}
                                                    ← extract_pdf（仅 _render/_fs）
                                          main_crawl（高级网络入口）
```

`extract_pdf` 不经浏览器（0.9.4 实证 file:// 必炸、http(s) PDF 导航失败），
走官方 `PDFContentScrapingStrategy.scrap()` + `asyncio.to_thread`。

### crawl4ai 是延迟导入

`_crawler.py` 与 `_render._apply_extraction` 在函数内 `import crawl4ai`，
`extract_pdf` 同理依赖 `bs4`。未安装时模块照常加载，**合并后返回 400 信封**
（原实现裸抛 `ModuleNotFoundError`），附 pip 安装指引；`screenshot`/`extract_pdf`
的入参校验与闸门判定不依赖 crawl4ai，未装也能跑到。


---

## 四、`tools/mail/` — 邮件工具

| 文件 | 行数 | 函数数 | 符号 | 依赖 |
|------|------|--------|------|------|
| `main_mail.py` | 147 | 1 | `async_email_tools` | `_helper`, `find_email`, `receive_email`, `send_email` |
| `_connection.py` | 222 | 4 | `_abandon_imap`, `_wait_imap_hello`, `async_open_imap`, `async_open_smtp` | `_helper` |
| `_helper.py` | 635 | 17 | `_where`, `_ok`, `_err`, `parse_fetch_lines`, `get_email_config`, `check_email_config`, `error_text`, `imap_ssl_contexts`, `imap_connect_error`, `parse_int`, `imap_date`, `in_date_range`, `decode_header_value`, `strip_html`, `parse_message`, `_save_email_attachments`, `build_date_criteria` | — |
| `find_email.py` | 86 | 1 | `async_find_email` | `_helper`, `search` |
| `receive_email.py` | 60 | 1 | `async_receive_email` | `_helper`, `search` |
| `search.py` | 295 | 2 | `async_filter_ids_client_side`, `async_search_mailbox` | `_connection`, `_helper` |
| `send_email.py` | 134 | 1 | `async_send_email` | `_connection`, `_helper` |

分层要点：`_helper.py` 收**全部无状态**辅助（含 IMAP 的 SSL 上下文构造与错误翻译文案），
`_connection.py` 只管**实际建连与握手生命周期**。二者边界是"碰不碰 socket"，不是"同步还是异步"。

`receive_email` 与 `find_email` 只差入口参数语义，检索逻辑全在 `search.py` 共用。

`main_mail.py` 里 `function="to_mail"` 是 `send_email` 的**兼容别名**（原代码即如此），路由到同一函数，勿删。

⚠️ **第二轮唯一的破坏性契约变更在这里**：`search.py` 的分页元数据
（`total`/`offset`/`count`/`has_more`）原先挂在信封**顶层**（非标准形状），经入口透传成为对外契约，
现统一收进 `data`。平台侧读 `r["total"]` 的代码必须改成 `r["data"]["total"]`，
`r["data"]` 也从"邮件列表"变成 `{"emails": [...]}`。详见《参数说明.md》第四节。

`_connection.py` 的 2 个纯副作用豁免：`_abandon_imap` / `_wait_imap_hello`（全库 6 个里的 2 个）。
其余三个连接函数（`async_open_imap`/`async_open_smtp`）返回活对象，套信封，`data` 直接是连接实例。

⚠️ **安全不变量（勿在重构中松动）**：SMTP 非 465 端口若 STARTTLS 升级失败必须**拒绝**——
否则授权码以明文过网络；IMAP 143 端口失败要给出"本平台不以明文提交授权码"的指引。
两条失败路径都必须先关半开连接，防 fd 泄漏。

**第二轮修掉 A20**：`get_email_config` 的 `int(smtp_port)` 遇 `"abc"` 裸抛 `ValueError`，现返回 400。
`imap_date` 遇畸形日期原先返回 `None` 使条件**静默跳过**，现 400 报错。

✅ **A17 已修（⑤）**：`find_email.py` 的 keyword/subject/sender 统一经 `_imap_quote`
转义 `\\` 与 `"` 后再拼 quoted string，注入串 `x" OR (UNSEEN OR DELETED)"` 现在是单个字面量。

---

## 五、`tools/mcp/` — MCP 客户端

| 文件 | 行数 | 函数数 | 符号 | 依赖 |
|------|------|--------|------|------|
| `main_mcp.py` | 77 | 1 | `async_mcp_tools` | `_config`, `client` |
| `_config.py` | 195 | 6 | `_where`, `_ok`, `_err`, `load_from_file`, `resolve_mcp_servers`, `build_client` | — |
| `client.py` | 88 | 1 | `async_mcp_client` | `_config` |

链状。`DEFAULT_MCP_CONFIG` 指向**本目录**（`_config.py` 所在目录）下的 `mcp_servers.json`——
该文件当前不存在，靠 `data["mcp"]` 或 `config_path` 传入。⚠️ 移动 `_config.py` 会改变默认配置文件的查找位置。

`_config.py` 的 `resolve_mcp_servers` 原先返回**元组** `(servers, source)`，其中 `servers is None` 表示错误、
`servers == {}` 表示"未配置任何 MCP 但不阻断"。第二轮改成信封后这三态用 code 区分，
**易错的特例是"默认配置文件不存在"仍算成功（`code=200` + 空 servers）**，已单独验证保真。

`build_client` 返回活对象 `MCPClient`，套信封放在 `data.client`（一次返回多个值，故用命名字典）。

**第二轮修掉 A12 及三处隐藏缺陷**：
① 全域无 `isinstance` 检查，非 dict 入参裸抛 `AttributeError`（六域里唯一完全无防护）→ 现 400；
② `build_client` 对 stdio 缺 `command` 是 `cfg["command"]` 直接索引 → `KeyError`，现 400；
③ `load_from_file` 的 `open`/`json.load` 无保护 → `FileNotFoundError`/`JSONDecodeError`/`IsADirectoryError`，现 400；
④ 配置段非 dict 原先 `continue` **静默跳过**，用户永远不知道少了哪个 server，现计入 `errors` 并出现在 message 里。

---

## 六、`tools/db/` — 数据库工具

| 文件 | 行数 | 函数数 | 符号 | 依赖 |
|------|------|--------|------|------|
| `main_db.py` | 205 | 2 | `async_db_write_tools`, `async_db_tools` | `_helper`, `dialect`, `gate`, `mongodb`, `mysql`, `postgresql`, `sqlite` |
| `_helper.py` | 488 | 16 | `_err`, `_ok`, `_resolve`, `_sqlite_target_path`, `_sqlite_databases`, `_db_allowed`, `_target_db`, `_check_ident`, `_jsonable`, `_rows_to_dicts`, `_mongo_filters`, `_qcol`, `_qtbl`, `_wph`, `_write_where`, `_check_scalars` | — |
| `dialect.py` | 355 | 3 | `_sql_dialect_table`, `_sql_dialect_query`, `_sql_dialect_write` | `_helper`, `executors` |
| `executors.py` | 446 | 9 | `_pg_exec`, `_pg_write`, `_my_exec`, `_my_write`, `_lt_read_run`, `_lt_exec`, `_lt_write_run`, `_lt_write`, `_mongo_call` | `_helper` |
| `gate.py` | 546 | 10 | `_tbl_list`, `_stem`, `_db_same`, `_tbl_hit`, `_tbl_denied_msg`, `_tbl_gate`, `_sql_table_refs`, `_sql_tbl_check`, `_db_gate`, `_tbl_filter_out` | `_helper` |
| `mongodb.py` | 231 | 3 | `_bad_limit`, `_mongo`, `_mongo_write` | `_helper`, `executors` |
| `mysql.py` | 89 | 1 | `_my` | `_helper`, `dialect`, `executors` |
| `postgresql.py` | 89 | 1 | `_pg` | `_helper`, `dialect`, `executors` |
| `sqlite.py` | 84 | 1 | `_lite` | `_helper`, `dialect`, `executors` |

最大的一域（46 个函数、2533 行），**四层结构**，自底向上：

### 为什么 `executors` 与 `dialect` 必须分开

这是本域拆分的**关键约束**，不是风格偏好：

- `dialect.py` 的 `_sql_dialect_write` 调用 `executors.py` 的 `_pg_write`/`_my_write`/`_lt_write`
- `postgresql.py` 的 `_pg` 调用 `dialect.py` 的 `_sql_dialect_query`/`_sql_dialect_table`

若把「底层驱动执行」和「方言语句编排」合进一个文件，`_pg → dialect → _pg_write` 会与该文件形成双向依赖。拆开即为无环的单向链：

```
_helper  ←  executors  ←  dialect  ←  {postgresql, mysql, sqlite}
   ↑            ↑                        ↑
   └────────  mongodb  ──────────────────┘
   ↑
   └── gate（旁路，只被 main_db 调）
```

### 为什么 `gate.py` 不并入 `_helper.py`

它虽然也是无状态函数，但内容是库级/表级白名单黑名单与 SQL 表引用校验，是这个工具的**业务核心**而非辅助。
混进 helper 会让 546 行安全逻辑失去独立可见性——改动它应当是显式的安全决策。

### 第二轮的三处结构变化

1. **`_err(msg)` → `_err(msg, where)`**：原件位置标识硬编码 `_async_db_tools` 且 `__file__` 取 `_err`
   自己所在文件，导致所有闸门/配置错误都报 `_helper.py_async_db_tools`、无诊断价值（A15）。
   现由各调用方传入 `where`，错误可精确定位到 `gate.py`/`executors.py`。
2. **`_db_gate`/`_tbl_gate`/`_sql_tbl_check` 改为校验器信封**：原件返回"错误字符串或 None"，
   调用方要 `if gerr: return _err(gerr)` 转一道。现直接 `return gr` 转发 400 信封，少一层转换。
   `_db_gate` 还顺带回传 `target_db`（白名单去后缀互认时它可能被改写），调用方不必再单独调 `_target_db`。
3. **去掉 `raise ValueError` 作业务信号**：原件 `_lt_exec`/`_lt_write` 用
   `raise ValueError(原因)` + 入口 `except ValueError: return _err(str(e))` 实现校验失败回传。
   现改为逐层返回 400 信封显式转发；入口**保留** `except ValueError` 兜底，
   因为 MongoDB 线程内回调超限仍需异常传播（线程返回值无法回传错误信封）。

### 安全逻辑未松动（已逐项验证）

第二轮改造触及全部闸门，故单独断言 10 个闸门场景：两侧**均** 400，**且执行后库未被改动**
（查 `orders`/`customers` 行数）。验证见《工具拆分规范.md》第五节 ③。

**第二轮修掉 A16**：`dialect.py` 的 `if _check_ident(col, "列名"): continue` 会**静默丢掉非法列名的条件**
照常查询，模型拿到 `code=200` 但少了条件的残缺结果集。`order_by` 同病。现均 400 报错。

✅ **C2 已修（⑤）**：`main_db.py` 的 `list_databases` 输出白名单过滤改为与黑名单一致的
`_db_same`，SQLite 文件夹模式下 `allowed_databases: ["orders"]` 能正确列出 `orders.db`。

---

## 七、`config/` — 默认配置中心（基础设施层）

与 `tools/` 平级，不在 `tools/` 下。五域的硬编码默认值收敛到这里的 `config.db`（SQLite）。
读取优先级 **data > sqlite > None**；连接/身份类参数（`db.type`、`db.port.*`、`db.database`、mail 的 smtp/imap host+port）**无源码兜底**，data 与 sqlite 都无值时返回 400。完整契约、105 项配置表、三类语义见《配置说明.md》。

| 文件 | 行数 | 职责 | 依赖 |
|------|------|------|------|
| `__init__.py` | 61 | 统一导出（生命周期 API + 三合并辅助 + schema 查询） | `schema`, `store`, `merge` |
| `schema.py` | 195 | **105 项配置的单一真相源**：Item(key/value/type/category/note/secret/hard_max) + 导入即自检 `_selfcheck()` | — |
| `store.py` | 298 | `config.db` 读写 + 进程级缓存（同步读一次、`get()` 走内存）+ 生命周期 `configure/init_db/load/aload/get/clamp_get/set_value/unset` | `schema` |
| `merge.py` | 62 | `pick`/`pick_str`/`pick_int` 三合并辅助，处理 falsy 语义差异（0/False 有效 vs 空串未传） | `store` |

关键设计：

- **进程级缓存 + RLock**：`store._LOCK` 是 `RLock` 而非 `Lock`——`load()` 持锁时调 `init_db()`，
  后者结尾又抢同一把锁清缓存，非重入会死锁（"configure 到新路径后首次 set_value"路径踩过，见踩坑记录 C7）。
- **`clamp_get` 只收紧不放宽**：10 个钳制项（`hard_max` 非 None）消费点走 `min(sqlite值, hard_max)`，
  库内调小生效、调大被源码上限压回（铁律 #11）。源码常量 `_MAX_ROWS`/`_SEMAPHORE_MAX` 等降为 `hard_max` 兜底。
- **敏感项出厂 None**：6 项（db.host/user/password/database、mail.account.user/password）
  `_selfcheck()` 强制出厂为 None，仅支持库注入；`config.db` 命中 `.gitignore` 的 `*.db`。
- **db 域的 `eff_*` getter 收口**：`tools/db/_helper.py` 提供 `eff_max_rows`/`eff_max_affect`/
  `eff_list_tables_limit`/`eff_connect_timeout`/`eff_mongo_selection_timeout`/`eff_table_data_limit`/
  `eff_run_query_limit`，dialect/executors/方言入口只调这些，不各自 import config。

依赖方向：`tools/*` 21 个文件 → `config`（单向，config 不反向依赖任何工具域）。

---

## 八、跨域依赖

**五域互不依赖**，无任何跨文件夹 import。这意味着：

- 可以只挂其中一域起步
- 某一域的第三方依赖缺失（如 `crawl4ai`、`aioimaplib`）不影响其他域加载，
  甚至不影响**同域**的基础网络功能（`httpx` 与 `crawl4ai` 互不牵连）
- 装配层（`agent/builder.py` 或 `tools/__init__.py`）是唯一把六域聚拢的地方，需自己写

---

## 九、第三方依赖清单

| 域 | 必需 | 状态（当前 `.venv`） |
|------|------|------|
| db | `asyncpg` 0.32.0 / `pymysql`→用 `aiomysql` 0.3.2 / `pymongo` 4.20.1 / `sqlglot` 30.33.0 | 已装 |
| net（基础） | `httpx` | 已装 |
| net（高级） | `crawl4ai` | **未装**（延迟导入，模块可加载；缺时返回 400 信封） |
| mail | `aioimaplib` 2.0.3 / `aiosmtplib` 5.1.3 / `beautifulsoup4` 4.15.0 | 已装 |
| system | 无（仅 stdlib `asyncio`/`subprocess`/`platform`/`shlex`） | — |
| mcp | `agentscope.mcp`（→ `mcp` 2.3.0） | 已装 |

SQLite 走 stdlib `sqlite3`，无需驱动；`sqlglot` 仅在**启用表级管控时**才 import（`_sql_table_refs` 内延迟导入），不用管控可不装。

驱动多为**函数内延迟导入**（`import asyncpg` 在 `_pg_exec` 里），所以缺驱动时模块照常加载。
**第二轮变化**：缺驱动/缺依赖时原先裸抛 `ImportError`/`ModuleNotFoundError`，
现返回 400 信封并附 `pip install` 指引——`crawl4ai`、`asyncpg`、`aiomysql`、`pymongo`、`sqlglot`、`beautifulsoup4` 六处均已改。

⚠️ 但**构造成功仍不等于可用**（A11 未变）：`QdrantStore()` 之类要跑到第一次调用才暴露缺库；
第二轮只是把"崩"变成了"返回 400"，验证方式不变——必须执行到那条分支。

---

## 十、更新日志

| 日期 | 内容 |
|------|------|
| 2026-11-22 | 首版。记录 37 个文件的行数、符号清单与依赖图；含 db 四层结构的成环约束说明与六域零跨域依赖结论 |
| 2026-11-22 | **第二轮改造同步**。行数 3906 → 6550（+68%），函数增至 120（含 19 个信封机器）。六域章节全部重生成表格并补记：`net` 的 `_HTTP_CLIENT_INSECURE`（修连接泄漏）与 `verify` 严格化、`crawl` 的副作用豁免与文件闸门契约不变、`mail` 的分页元数据破坏性变更与 A17 未修、`mcp` 的三态语义保真与四处缺陷修复、`db` 的三处结构变化（`_err` 带 where / 校验器信封 / 去掉 raise 信号）与闸门未松动验证。目录总览补「信封机器」与「纯副作用」两种角色 |
| 2026-11-22 | **③ crawl 合并回 net**（用户决策，定位「高级网络请求」）。决定性依据：`agent_study/tools/__init__.py` 本就把 `async_crawl_tools` 挂进 `ToolGroup("net")`。`crawl/_helper.py` 按符号拆为 `_envelope`（信封机器，独立成层）/`_fs`（文件闸门，**提到域共用层**）/`_render`（配置构建与钳制）；旧信封层 3 个符号丢弃，信封机器 19→16。**修掉不对称**：`download` 原先直接落盘不过闸门而同域 `screenshot` 过，现共用 `_fs`，同路径判定一致。**消除跨域陷阱**：`crawl._err(where,msg)` 与 `net._err(message,func_name,...)` 参数顺序倒置，现全库统一。net 章节重写为 17 文件，crawl 章节删除，后续节号前移；统计 37 文件/120 函数 → **39/117** |
| 2026-11-22 | **④ config 层同步**。新增第七节 `config/`（基础设施层 4 文件 616 行）：schema 73 项 / store 进程级缓存+RLock+clamp_get / merge 三辅助；原七～九节号后移为八～十。顶部标题改 `scope CODE_INDEX`、阶段表加④、全仓规模 43 文件 7174 行 |
| 2026-11-22 | **⑤ 工具层收尾**。A17/C2 已修；`net/_fs.py` 的写/读闸门合并为内部 `_check_fs`，对外 `_check_write`/`_check_read` 契约不变；连接/身份类参数去源码兜底。规模重算为 39 文件 / 127 顶层函数 / 6726 行，全仓 43 文件 7345 行 |
