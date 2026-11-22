# scope/docs

`scope/` 的配套文档。六份，按用途查，不必通读。

| 文档 | 什么时候读 | 内容 |
|------|-----------|------|
| **[参数说明.md](参数说明.md)** | **调任何工具前** | 五个通用工具域 + RAG 的入口签名、`function` 清单、入参表、返回契约、`db_config` 管控字段；开头「〇′ 统一契约」与「〇 全局调用契约」**必读** |
| **[CODE_INDEX.md](CODE_INDEX.md)** | 找文件 / 改代码前 | 39 个文件的行数、符号清单、依赖图；db 四层结构的成环约束；net 的双入口与四段辅助层；第三方依赖清单与已装状态 |
| **[工具拆分规范.md](工具拆分规范.md)** | 加新功能 / 重跑验证 | 六条组织规则（含入参统一与两类豁免）+ 刻意偏离及理由 + 新增功能流程 + **两轮各自的验证方法**（脚本已丢弃，方法留此）+ 切分器实现约束 |
| **[踩坑记录.md](踩坑记录.md)** | 报错时 / 装配前 | A 类 22 条使用侧坑（A17 IMAP 注入已修）、B 类 6 条 agentscope 集成坑、C 类 8 条**误诊与自查纠正** |
| **[配置说明.md](配置说明.md)** | 装配 Agent 前 / 改默认值前 | config 层（SQLite 默认配置中心）：读取优先级 data > sqlite > None（连接/身份类参数为 data > sqlite > 400）、110 项配置表、三类语义（93 自由 / 10 钳制只收紧 / 7 敏感出厂 None）、生命周期 API、**mail 环境变量移除与连接参数去兜底的破坏性变更**、什么进 config 什么不进 |
| **[框架层规划.md](框架层规划.md)** | **封装 Agent 框架 / 做审批与 RAG 前** | 对照 `agent_study/scope` 的框架层缺口（P0～P3）、目标目录结构、工具审批设计（PermissionEngine + Confirm 事件）、RAG 设计（官方 KnowledgeBase/RAGMiddleware）、禁止照搬清单与实施顺序 |

---

## 三十秒上手

```python
import sys; sys.path.insert(0, "<scope 目录>")   # 使 tools.* / config 可作包导入

# 装配期预载默认配置（可选；不载则首次 get 惰性建库）
import config; import asyncio; asyncio.run(config.aload())

from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit, ToolGroup, FunctionTool, Read
from agentscope.agent import Agent

from tools.db.main_db import async_db_tools, async_db_write_tools
from tools.net.main_net import async_req_tools
from tools.system.main_sys import async_sys_tools

# 凭证：base_url 挂在 Credential 上，不是 client_kwargs
cred = OpenAICredential(api_key="sk-...", base_url="http://localhost:1234/v1")
model = OpenAIChatModel(credential=cred, model="qwen3-max", stream=True, context_size=131072)

tk = Toolkit(
    tools=[FunctionTool(async_db_tools, name="async_db_tools", is_read_only=True)],  # basic 组：常驻
    tool_groups=[
        ToolGroup(name="dbw",  description="数据库写（高危）", tools=[FunctionTool(async_db_write_tools)]),
        ToolGroup(name="net",  description="网络请求、天气、下载", tools=[FunctionTool(async_req_tools)]),
        ToolGroup(name="sys",  description="Shell 命令（高危）", tools=[FunctionTool(async_sys_tools)]),
    ])

agent = Agent(name="assistant", system_prompt="你是数据分析师", model=model, toolkit=tk)
```

裸调工具（不经模型）：

```python
r = await async_db_tools({
    "function": "run_query",
    "db_config": {"db_type": "sqlite", "dir": "/path/to/db", "database": "orders",
                  "allowed_databases": ["orders"], "allowed_tables": ["customers", "orders"]},
    "sql": "SELECT COUNT(*) AS n FROM orders",
})
print(r["code"], r["message"], r["data"])     # 字段是 message，不是 msg
```

---

## 六个最容易致命的点

1. **`download` 现在也过文件闸门**（crawl 合并时补上）：写 cwd 之外的路径会被拒 400。
   合并前它完全不过闸门，所以**老调用方会突然失效**——平台必须注入 `check_write`
   放开到自己的 uploads 目录 → 踩坑记录.md A21
2. **`mail` 的分页元数据换了位置**（第二轮唯一破坏性变更）：`total`/`has_more` 从信封顶层
   移进 `data`，`r["data"]` 现在是 `{"emails": [...]}` 而非邮件列表。**平台侧读取代码必须改**
   → 参数说明.md 第四节
3. **参数平铺顶层**，嵌进 `arguments` 会得到误导性错误「非法表名: None」→ 参数说明.md 〇-1
4. **经 `FunctionTool` 调用要包一层 `{"data": {...}}`**，否则 `unexpected keyword argument 'function'` → 踩坑记录.md B1
5. **`net` 的文件闸门必须服务端注入**，不注入只走 cwd 兜底 → 踩坑记录.md A10
6. **mail 的 `EMAIL_*` 环境变量已失效**（④ 移除）：靠环境变量注入邮箱配置的部署，
   必须改成写 `config.db`（`config.set_value("mail.account.user", ...)`）→ 配置说明.md 八-①

---

## 现状与出处

五个域经过**四轮改造**，基线不同（详见 工具拆分规范.md 第〇节）：

| 轮次 | 内容 | 与原件关系 |
|---|---|---|
| ① AST 拆分 | `agent_study/scope/tools`（agentscope 2.0.9）的 6 个单体 → 37 个文件，在 **agentscope 2.0.12 + Python 3.14.8** 下验证 | **逐字节等价**：137 个可执行体 AST 全等、127 用例一致（db 43 例含落盘终态） |
| ② 入参与错误返回统一 | 117 个函数改 `data` 入参 + `{code,data,message}` 信封；6 个纯副作用豁免；16 个信封机器豁免签名 | **故意破坏等价**（用户决策）。差异被预先分类为「新增校验」 |

验证 **655 项断言全部通过**：system 54 / net 117 / db 57 / net 的 crawl 部分 175 / mail 165 /
mcp 68 / 跨域一致性与 download 闸门 19。方法见 工具拆分规范.md 第四、五、六节。

| ③ crawl 合并回 net | 原独立成域的 `crawl/` 并回 `net/`，定位「高级网络请求」；`_helper.py` 拆为 `_envelope`/`_fs`/`_render`，download 补闸门（A21）、`_err` 签名倒置消除（A22） | 目录重组，行为对撞仍逐函数验证（175 项） |

- 改造后规模：工具层 **39 文件 / 127 顶层函数 / 6726 行** + 基础设施层 `config/` 4 文件（110 项默认配置，SQLite）
- ④ config 层：散落在各域的硬编码默认值收敛到 `config.db`，读取优先级 **data > sqlite > None**；
  10 个钳制项走 `clamp_get` 只收紧不放宽（铁律 #11），6 个敏感项出厂 None 仅库注入；
  **破坏性**：mail 的 `EMAIL_*` 环境变量兜底彻底移除（默认值只此一源）
- **框架层已实现**：`agent/`（子智能体、运行时、上下文、Plan、Pipeline、SOP）、`llm/`、`media/`、`rag/`、`permission/`、`middleware/`、`workspace/`、`skills/`；剩余 `storage/`、`main.py` 服务化入口；缺口与规划见《框架层规划.md》
- **原件仍是行为基准，不要删** `agent_study/scope/tools/`——所有对撞验证仍以它为准
- 未复制：`dingtalk_tools/`（`_config.py` 含明文生产密钥，按「密钥三不进」不入）、
  `async_rag_tools.py`（跨目录依赖 `rag/`；检索职责改由官方 `RAGMiddleware` 承担，落地规划见《框架层规划.md》）。

### 缺陷处置状态

**第二轮已修**（入参与错误返回统一时一并解决，均有对撞验证）：

| 项 | 原症状 | 现行为 |
|---|---|---|
| mcp 无入参类型检查 | 非 dict 裸抛 `AttributeError`（A12） | 400 信封 |
| db 非 dict 入参裸抛 | str/list/int 抛 `ValueError`/`TypeError`（A13） | 400 信封 |
| db 非法列名静默跳过 | `filters`/`order_by` 畸形列 → `code=200` **残缺结果集**（A16） | 400 报错 |
| crawl `_clamp_configs` 穿透 | `downloads_path` 越界裸抛 `ValueError`（A18） | 400 信封 |
| mail 坏端口裸抛 | `smtp_port:"abc"` → `ValueError`（A20） | 400 报错 |
| db 错误位置无诊断价值 | 全部报同一位置（A15） | 报实际出错**函数名**（文件层面仍是 `_helper.py`，见 A15 订正） |
| 内部异常文案泄漏 | `invalid literal for int() with base 10: 'abc'` 直接给用户 | 「limit / offset 必须是整数」 |
| 驱动/依赖缺失裸抛 | `crawl4ai`/`asyncpg`/`aiomysql`/`pymongo` 未装时 `ModuleNotFoundError` | 400 信封 + pip 安装指引 |
| 表不存在/主键冲突记 500 | 属参数问题却报内部异常 | 改 400 |
| **download 与 screenshot 闸门不对称** | download 直接 `open` 落盘、完全不过闸门，而同域 screenshot 过 —— 租户策略被一个工具绕过（A21） | 共用 `net/_fs.py`，同路径判定一致 |
| **IMAP 搜索表达式注入** | `mail/find_email.py` 三处引号未转义，`x" OR (UNSEEN OR DELETED)"` 可扩大搜索范围（A17） | `_imap_quote` 转义 `\\` 与 `"`，注入串成为普通字面量 |
| db 白名单输出过滤不一致 | 启用 `allowed_databases` 后 SQLite 文件夹模式 `list_databases` 恒空（C2） | 与黑名单统一走 `_db_same`，`orders` 能匹配 `orders.db` |

**仍未修**（需你决策，改动会变更对外行为）：

| 项 | 位置 | 说明 |
|---|---|---|
| 流式进度污染最终结果 | `net/download.py` + agentscope 累积 | 进度文本与 JSON 无分隔拼接，模型拿到的不是合法 JSON。**A5** |
| 业务错误记为 `success` | agentscope `_convert_func_result_to_chunk` | `{"code":400}` 在框架侧是 `state=success`，`tool_retries_limit` 形同虚设。**B3**，需工具改返 `ToolChunk(state=ERROR)` |
| 模型看到的是黑盒 schema | 六域全部 | `{"data": {"additionalProperties": true}}`，参数靠 docstring 约束。**B1**，需 pydantic `input_schema` 结构化 |
| 路由文案跨域不一致 | `db` vs 其余四域 | 「未知 function」带前缀 vs 「暂不支持」不带。**A19**，原件既有，本轮保持 |
| db 错误位置只到函数级 | `db/_helper.py` `_err` 用自身 `__file__` | 位置形如 `_helper.py__tbl_gate`：函数名精确、**文件仍是信封层**。追求文件级精确要付 `inspect.stack()` 的代价，未采纳。见 A15 |

后五项的修法都会改变对外行为或需要动 agentscope 侧，故**刻意不混进本轮改造**——
每项都应独立成一次改动并重跑验证（教训见 C3：为了"顺手改进"偏离原件，会摧毁可证明性等价这一保证）。

`import agentscope.app` 缺 `apscheduler` 一项已装好，`create_app` 可用。

---

## 更新日志

| 日期 | 内容 |
|------|------|
| 2026-11-22 | 首版。四份文档的导航、三十秒上手示例、三个致命点索引、已知未修清单 |
| 2026-11-22 | **第二轮改造同步**。致命点 3→4 条（首位是 mail 分页元数据位置变更，平台侧必须改）；「已知未修」重写为「已修 / 仍未修」两栏（9 项已修、6 项仍未修含 **A17 未修的 IMAP 注入**）；现状段区分两轮基线并给出 632 项验证分解；导航计数 A 类 15→20、C 类 3→5 |
| 2026-11-22 | **⑤ 工具层收尾优化**。修 A17（IMAP 搜索引号转义）与 C2（`list_databases` 白名单用 `_db_same`）；连接/身份类参数去源码兜底（`db.type`、`db.port.*`、`db.database`、mail smtp/imap host+port，优先级改为 data > sqlite > 400）；仍未修从 6 项降至 5 项 |
| 2026-11-22 | 新增《框架层规划.md》：对照 `agent_study/scope` 盘点框架层缺口（7 个空目录 / `main.py` 0 字节 / 无 pyproject 与 tools 装配）；给出 P0～P3 路线、工具审批与 RAG 设计、禁止照搬的明文密钥与旧 API |
| 2026-11-22 | **④ config 层同步**。导航加配置说明.md（四→五份）；现状段三轮→四轮并加 config 层规模；致命点 5→6 条（新增 mail `EMAIL_*` 环境变量移除的破坏性变更）；三十秒上手加 config 装配；C 类 6→8 条 |