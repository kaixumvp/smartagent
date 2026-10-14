# VERSIONS.md · 版本真源

> 本文件是本仓库**唯一的版本真源**。任何文档、README、注释里的版本号与它冲突，以本文件为准。
> 各项目的详细路线图仍由各自文档承载（见每行的「路线图」列），但**当前版本与边界**在这里定义。

最后更新：2026-10-14

---

## 一、三个独立版本轴，一个随平台发布的控制台

平台后端、`ouroboros` 框架和 Capability Registry 各自演进；Console 随平台交付，不单独维护
发布节奏。三个独立版本号互不可比。

| 项目 | 路径 | 当前版本 | 版本轴 | 路线图 |
|---|---|---|---|---|
| `smartagent` | `application/platformagent/backend/` | **0.3.0** | 平台线（跟随产品交付节奏） | `documentation/platformagent/版本规划.md` |
| `smartagent-console` | `application/platformagent/frontend/` | 平台功能基线 **0.3.0**；`package.json` 仍为 **0.1.0** | 随平台线，不单独发版 | `documentation/platformagent/版本规划.md` |
| `ouroboros` | `application/ouroboros/` | **2.0.0** | 独立 SemVer（API 已冻结） | `documentation/ouroboros/版本规划.md` |
| `capability` (Capability Registry) | `application/capability/` | **0.3.0** | 独立服务版本线，通过 HTTP 与平台集成 | `documentation/capability/version-roadmap.md` |

> Console 的 `package.json` 版本字段尚未随平台功能线更新；在该字段调整前，不应把它当作 Console
> 独立发布版本。

**为什么是三条轴**：`ouroboros` 是业务无关的框架，可以被任意宿主复用，因此必须能独立于
`smartagent` 发布（否则宿主升级与框架升级会互相绑死）。`capability` 不共享 Python 代码或数据库，
但由平台通过受共享密钥保护的内部 HTTP API 消费；版本线仍可独立演进。

---

## 二、边界：谁依赖谁

```
                    ┌──────────────────────────┐
                    │  ouroboros  (2.0.0)      │  框架层：业务无关
                    │  Plan→Decide→Execute→Observe │
                    │  只定义 ports，不 import 宿主 │
                    └───────────▲──────────────┘
                                │ 依赖（import ouroboros.*）
                    ┌───────────┴──────────────┐
                    │  smartagent  (0.3.0)     │  业务层：FastAPI
                    │  实现 ports 为 adapters   │
                    └───────────▲──────────────┘
                                │ HTTP /v1
                    ┌───────────┴──────────────┐
                    │  smartagent-console      │  控制台：瘦 UI
                    └──────────────────────────┘

   Capability 管理端 ──管理 HTTP──► Capability Registry (0.3.0)
                                      │
                                      │ 内部 HTTP + 共享密钥
                                      ▼
                              smartagent adapters
                              (目录读取 / Tool 调用)
```

规则：

1. **依赖方向单向**：`smartagent → ouroboros`，永不反向。框架不 import 业务层的
   HTTP / DB / 配置 / 租户概念。
2. **业务层通过框架公开契约集成**：使用 `ports.py`、`core/runtime.py` 和框架文档公开的可组合模块
  （如 registry、gateway、memory）；不依赖 `core` 的私有节点/状态实现。
3. **`capability` 通过 HTTP 接入运行时**：平台 adapter 经共享密钥调用 Capability 内部 API，
   并把 API/MCP Tool manifest 注册为标准 Ouroboros Tools；两项目之间没有 Python package 或数据库依赖。

---

## 三、兼容矩阵

| 宿主 | 依赖 | 允许区间 | 说明 |
|---|---|---|---|
| `smartagent` 0.3.0 | `ouroboros` | `>=2.0,<3.0` | 包名 `src`→`ouroboros` 是 2.0 的破坏性变更，1.x 不兼容 |
| `ouroboros` 2.0.0 | Python | `>=3.11,<3.15` | 上界由 `litellm` 决定：没有任何已发布版本允许 3.15 |
| `smartagent` 0.3.0 | Python | `>=3.11,<3.15` | 同上 |

> **Python 上界不要动**。`litellm` 最新版仍是 `requires_python = <3.15`，放宽本仓库的上界
> 只会把「poetry 明确拒绝」变成「pip 深处报 No matching distribution」，错误更难读。

---

## 四、平台线（`smartagent`）：0.1 → 1.0

实际交付顺序曾偏离依赖链（跳过 V0.3/V1.0 先做了 V1.1 的评测与成本），本表按**真实交付**重排，
不再跳号。旧 V 号保留为里程碑别名，仅用于对照历史文档。

| 版本 | 里程碑别名 | 内容 | 状态 |
|---|---|---|---|
| 0.1.0 | 原 V0.1 骨架 | 单 Agent 最小闭环 + 工具调用 + Working Brain | ✅ 已交付 |
| 0.2.0 | 原 V0.2 能力 | 插件体系 / Skill / Tool / 多租户 / JWT / RBAC+Grant / 记忆起步 / HITL mid-run / 子 Agent / 审计 | ✅ 已交付 |
| **0.3.0** | 原 V1.1 评测与成本 | 评测（Golden Set + LLM-as-Judge）/ 灰度 A/B / 成本归因；另外并入原 V0.3 提前落地的 checkpoint 持久化 | ✅ **当前** |
| 0.4.0 | 原 V0.3 知识与可靠 | 实现 `Knowledge`/`Retriever` 端口（RAG 摄取/切块/embedding/检索）、可靠执行补齐 | ⏳ 未开始 |
| 0.5.0 | 原 V1.0 生产 | 可观测（OTel/Prometheus）+ Console 查询端点 + 安全（mTLS/脱敏/PII）+ 部署 + 原 V1.1 未交付的 Playground 与成本基线对比 | ⏳ 未开始 |
| 1.0.0 | — | 平台 API 冻结 + 生产验收 | ⏳ 未开始 |

**0.3.0 的诚实说明**：原 V1.1 的「成本较 V1.0 下降」这一验收标准**无法验证**——V1.0 的可观测
基线不存在。0.3.0 做到的是让成本数据第一次是真的（此前 `runs.cost` 恒为 0）。
Console Playground 与成本基线对比明确移入 0.5.0，不留在 0.3.0 里充数。

---

## 五、框架线（`ouroboros`）：独立 SemVer

| 版本 | 内容 | 状态 |
|---|---|---|
| 0.1 – 0.4 | 运行循环 → 插件/Skill/记忆 → 端口收口 + `AgentRuntime` 门面 + Retry/Pause → 可观测 + 沙箱 + fallback | ✅ |
| 1.0.0 | 公共 API 面冻结、破坏性变更只进 major、`py.typed` | ✅ |
| 1.1.0 | 确定性重放 + `Judge` 端口 + 成本感知（分级路由/预算/缓存） | ✅ |
| **2.0.0** | **导入包名 `src` → `ouroboros`**（破坏性）；移除无人 import 的 `langgraph` | ✅ **当前** |
| 2.1 | 多智能体（多 Agent 协同、反思/重规划） | 🔭 远期 |

**为什么 2.0.0 是必要的**：发行包 `ouroboros` 此前导出的顶层包字面就叫 `src`。宿主若是 src-layout
（本仓库的业务层就是），把宿主根放进 `sys.path` 后 `import src` 会**静默**绑定成宿主自己的命名空间包，
同一个文件被双地址化——两套 `@lru_cache` 的 `Settings` 单例、两套 `DeclarativeBase` 注册表。
它还违反了 v1.0 冻结契约里白纸黑字写的「顶层 `ouroboros`」。`__all__` 里的符号一个未动。

---

## 六、`capability` 线：独立并行

| 版本 | 内容 | 状态 |
|---|---|---|
| 0.1.0 | Tool CRUD + PostgreSQL(JSONB Manifest) + 管理页面 | ✅ 已交付 |
| 0.2.0 | MCP Provider CRUD + `tools/list` 同步 + remote_missing 检测 | ✅ 已交付 |
| **0.3.0** | API Service/API Tool、凭据加密、HTTP Tool 执行、内部共享密钥 API、平台 Runtime 集成 | ✅ **当前** |
| 0.5.0 | Discovery（`POST /discover`）+ 关键词/tag 检索 + 权限分组 | ⏳ 未开始 |
| 1.0.0 | Dashboard + Tool Lifecycle + Sync History | ⏳ 未开始 |

当前状态需注意：
- 管理 API **无用户鉴权**且 CORS 为 `*`；平台 Runtime 集成 API 使用独立共享密钥。
- Registry 除同步 MCP manifest 外，也可执行 API/MCP Tools；平台后端经内部 API 代理目录读取与调用。
- Platform 与 Registry **不共享 Python 包或数据库**，只通过 HTTP 集成。
- `auto_create_tables` 默认开启。
- 宿主端口已从 5432/8000/3000 移到 **5433/8010/3010**，以便与业务层同时运行。

---

## 七、发布记录

截至 2026-10-14，仓库**没有 git tag**（`git tag -l` 为空）；版本号由项目清单和文档维护。
正式打 tag 时使用：

```
smartagent-v0.3.0
ouroboros-v2.0.0
capability-v0.3.0
```

---

## 八、已知的待决问题

1. **`ouroboros` 这个发行名在 PyPI 上已被占用**（`steiflab/Ouroboros`，scRNA-seq 工具）。
   要发布必须换发行名或走私有源。这是与包名归一无关的第二个问题。
2. **`agent_tools` 表与 `AgentTool` 模型是死代码**，迁移和模型还在，无任何 route/service/test 引用。
3. **三处 `Tool` 概念 schema 互不兼容**（框架 `BaseTool` / 业务层 `tools` 表 / capability `Tool` 模型），
   且无映射层。合并属功能开发，未做。
4. **`V1.1实施规格.md` 不存在**，已交付的评测/灰度/成本是最大的一块增量却没有规格文档。
