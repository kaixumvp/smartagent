# Ouroboros 多 Agent 上下文管理设计方案

> 文档状态：设计提案，尚未实现。
> 适用基线：Ouroboros 2.0.0；当前单 Agent 上下文设计见[上下文管理设计方案](./上下文管理设计方案.md)。

## 1. 目标与核心原则

多 Agent 运行不是把同一份聊天历史复制给多个 Agent。父 Agent、每个子 Agent、同级 Agent 和最终汇总 Agent 应有各自独立的运行上下文；只有经过显式授权和筛选的任务输入、证据或结果可以跨运行传递。

本方案目标：

- 限制父 Agent 的长历史、子 Agent 的工具输出和并行子任务结果造成的上下文放大；
- 避免把无关或敏感的父级对话泄漏给子 Agent；
- 让子 Agent 可以完成任务，同时知道必要目标、约束、输入和输出格式；
- 将父子运行的 token/成本、超时、取消和并发放进同一预算边界；
- 让最终汇总能追溯证据来源、识别冲突和报告部分失败；
- 兼容当前“父 Agent 通过 AgentSkill 调用子 Agent”的运行方式，并可扩展到未来任务图/团队协调。

核心原则：

1. **默认隔离**：子 Agent 不继承父 Agent 的完整 history、memory、system prompt、工具集合或权限。
2. **按任务交接**：父 Agent 只传完成子任务必需的上下文包，不传整段对话。
3. **结果有契约**：子 Agent 回传结构化状态、答案、证据和用量，不只返回自由文本。
4. **预算树形继承**：子运行从父运行可用预算中分配额度，所有后代共享总上限。
5. **共享显式且有范围**：需要共享数据时通过任务输入/结果或受 ACL 控制的 Task Store；不默认共享可变消息列表或长期记忆。
6. **原始记录独立保存**：每个 run 的 transcript 由宿主分别持久化；模型上下文只是该 run 的临时视图。

## 2. 当前实现与已知边界

### 2.1 当前调用链

```text
父 Agent 的 LLM
  → 选择 AgentSkill
  → AgentSkill 从参数生成 task 字符串
  → SubagentRunner(agent_ref, task, InvokeContext)
  → 宿主解析子 Agent 并启动独立 AgentRuntime
  → 子 Agent RunResult 被转换成字符串
  → 字符串作为父 Agent 的工具结果
```

当前 [AgentSkill](../../application/ouroboros/ouroboros/skills/agent_skill.py) 从 `task` 参数或其他参数的 JSON 序列化结果构造任务；[SubagentRunner](../../application/ouroboros/ouroboros/ports.py) 接收 `agent_ref`、task 字符串和 `InvokeContext`，返回字符串。PlatformAgent 的 [DbSubagentRunner](../../application/platformagent/backend/src/smartagent/adapters/subagent_runner.py) 为子 Agent 创建独立 Run，并通过 `parent_run_id` 关联父运行。

### 2.2 已有的隔离优势

- 子 Agent 获得单独的运行记录和独立运行时，不是直接修改父 Agent 的 `AgentState`。
- 当前子调用接口只传 task 和 `InvokeContext`，没有传父 Agent 的完整 `messages`；因此默认不存在自动复制完整父会话的问题。
- PlatformAgent 给子运行创建独立数据库 session，避免并行子运行共享不安全的 AsyncSession。
- `InvokeContext` 透传 tenant/user/run/trace/session 和 subagent depth 等元数据，可用于关联追踪及宿主侧租户检查。

### 2.3 仍然存在的问题

- 委派输入/结果是字符串，缺少 `task_id`、必需约束、数据引用、输出 schema、状态和来源证据。
- 没有明确说明：子 Agent 的 `session_id` 应否与父 Agent 共用；如果误用同一个 session，长期/短期记忆可能串话。
- 没有框架级预算对象约束父子总 token、成本、调用次数、总时长和并发数；深度上限不能防止宽度爆炸。
- 每个子 Agent 内部的 Context Builder 即使有局部预算，也需要知道父级剩余额度；否则多个子运行各自“合法”但合计超预算。
- 子 Agent 返回的大段结果会作为父 Agent 的工具结果，再进入父 Agent 后续上下文，可能造成父子结果重复、摘要重复和 token 成倍增长。
- 多个子 Agent 的证据可能矛盾、重复或有不同可信度；纯字符串汇总没有标准的来源、冲突和部分失败语义。
- 取消、超时和预算耗尽没有一个统一树级传播契约；父任务结束后，正在运行的子任务可能仍消耗资源。
- 若未来引入团队共享记忆或 blackboard，若不区分任务/租户/用户/Agent 范围，将有越权访问和跨任务污染风险。

## 3. 目标上下文模型

### 3.1 每个 Agent Run 独立上下文

```text
Run Tree
root_run
  ├─ child_run_A：独立 transcript + 独立 Context View
  ├─ child_run_B：独立 transcript + 独立 Context View
  └─ synthesis_run（可选）：仅接收父级选中的子结果

跨 Run 数据只通过：
  DelegationEnvelope（父 → 子）
  TaskResult / EvidenceRef（子 → 父）
  Scoped Task Store（显式共享，受 ACL 控制）
```

- 每个 run 有自己的短期对话历史、当前计划、工具结果、模型上下文预算和摘要。
- `trace_id`、`parent_run_id`、`task_id` 等用于关联，不是载荷本身，不应通过 trace/session ID 隐式读取父上下文。
- 用户和租户标识用于权限边界；不能因父子关系就跳过子 Agent 自身的授权校验。
- 每个子 Agent 的 Agent 配置、system prompt、工具 allowlist 和 memory policy 由宿主根据目标 Agent 单独装配。

### 3.2 Delegation Envelope（委派上下文包）

父 Agent 每次委派前构造一个最小、显式、可审计的上下文包：

```json
{
  "task_id": "research_vendor_a",
  "goal": "查找供应商 A 当前公开的产品价格和关键规格",
  "inputs": {
    "vendor": "供应商 A",
    "region": "中国大陆"
  },
  "constraints": [
    "仅使用公开来源",
    "没有可靠证据时明确标注未知"
  ],
  "output_contract": {
    "type": "object",
    "required": ["findings", "sources", "unknowns"],
    "properties": {
      "findings": {"type": "array"},
      "sources": {"type": "array"},
      "unknowns": {"type": "array"}
    }
  },
  "context_refs": [],
  "budget": {
    "max_input_tokens": 0,
    "max_output_tokens": 0,
    "max_total_tokens": 0,
    "deadline": null
  }
}
```

上面数值 `0` 仅作字段示意；实际预算必须由父级调度器计算和分配，不代表零预算的默认值。

建议 Envelope 包含：

| 字段 | 说明 |
|---|---|
| `task_id` | 父运行内稳定唯一的委派任务 ID，用于结果、事件、重试幂等关联 |
| `goal` | 子 Agent 应完成的明确目标，不包含父级所有推理过程 |
| `inputs` | 完成任务必需的结构化输入，避免让子 Agent 从长对话中猜 |
| `constraints` | 任务范围、时效、隐私和禁止事项 |
| `output_contract` | JSON Schema 或等价类型，约束回传内容 |
| `context_refs` | 父级明确允许子 Agent 读取的消息/证据/artifact 引用 |
| `budget` | 父运行分配的输入、输出、总用量、调用次数或截止时间 |
| `provenance` | 来源消息、父 run、任务创建时间和委派者信息 |

`context_refs` 默认为空。只有在子任务确实需要原文时才传入受授权引用；引用读取通过宿主校验租户、用户、run/task 范围和敏感级别。不能给子 Agent 一个父 `session_id` 后让它自行加载整个历史。

### 3.3 子 Agent 的本地上下文

子 Agent Context Builder 只从以下输入构建上下文：

1. 子 Agent 自己的 system prompt、策略和工具 schema；
2. Envelope 的 `goal`、`inputs`、`constraints` 和 `output_contract`；
3. 子 Agent 自己 run 内的对话与工具结果；
4. 明确允许、且通过授权读取的 `context_refs`；
5. 宿主允许的子 Agent 专属记忆。

不自动包含：

- 父 Agent 完整 history、system prompt 或内部 chain-of-thought；
- 父 Agent 的所有工具 schema、插件凭据或审批状态；
- 其他 sibling Agent 的对话和中间结果；
- 父级长期记忆或相同 session 的全部短期记忆。

父 Agent 的“推理过程”不作为默认 handoff 内容；如需解释，父级将任务依据整理成可验证的事实、约束或引用，不复制隐藏推理。

### 3.4 子 Agent 的结果契约

子 Agent 返回 `TaskResult`（建议类型，尚未实现）：

```json
{
  "task_id": "research_vendor_a",
  "status": "completed",
  "output": {
    "findings": [],
    "sources": [],
    "unknowns": []
  },
  "summary": "找到两个可核验的公开价格来源；规格信息部分缺失。",
  "evidence_refs": [],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  },
  "error": null,
  "truncated": false,
  "child_run_id": "run_child"
}
```

返回状态至少包括 `completed`、`partial`、`failed`、`awaiting_human`、`canceled`、`budget_exceeded`。父 Agent 不能把非 completed 状态当作成功答案；必要时应向用户报告部分结果或请求人工介入。

- `output` 受输出 schema 校验和大小预算限制。
- `summary` 是供父 Agent 快速理解的短摘要，不代替结构化输出或证据。
- `evidence_refs` 指向可审计来源；不将所有原文重复嵌入父上下文。
- `child_run_id` 用于追踪；父级不能仅凭 ID 绕过授权读取子 Agent 全量 transcript。
- 若输出过大，应保留关键摘要和授权引用，并清楚标记 `truncated`/`partial`，不能静默截断。

## 4. 预算、并发与取消的树形管理

### 4.1 分层预算

上下文预算由 root run 初始化，沿委派树分配：

```text
Root Run Budget
  ├─ Parent own-context reserve
  ├─ Child A allocation
  ├─ Child B allocation
  └─ Synthesis reserve
```

- Root budget 包括总 token/成本、最大并发子任务数、最大委派数、最大深度和截止时间。
- 父级为每个 child 预留额度；子 Agent 的 Context Builder 不能超过本地 allocation。
- 多个并发子 Agent 使用同一个树级预算协调器或由宿主原子分配额度，避免各自读取同一个旧余额而超支。
- 子任务结束后将实际 usage 记到账户；未用完额度是否回收由预算协调器决定。
- `RunContext` 只传递不可伪造的预算引用/执行上下文，不让 LLM 自己修改额度。
- 运行成本换算涉及模型价格，应由宿主成本策略实现；框架至少传递每模型 usage 和限制。

建议预算维度：

| 预算 | 约束 |
|---|---|
| 树级最大总 token/成本 | 父子和汇总调用总额 |
| 单子任务最大 token/成本 | 防止单个 Agent 消耗过多 |
| 单请求输入与输出 token | 由单 Agent Context Management 控制 |
| 最大委派任务数/并发数 | 防止宽度爆炸 |
| 最大深度 | 防止递归嵌套失控 |
| 总 deadline 与子任务 timeout | 防止长时间挂起 |
| 每个结果的输出大小 | 防止大结果回灌父上下文 |

深度上限和 token budget 不能互相替代：深度限制递归层数，委派数/并发限制树的宽度，token/成本限制实际消耗。

### 4.2 并发交接与父上下文

- 并发 child 收到的是各自独立的 Envelope 快照，不共享父 Agent 的可变 `messages` 或 `AgentState`。
- 父级只在每个 child 完成后将受限 `TaskResult` 合并到自己的上下文；中间过程默认不持续灌入父 prompt。
- 同一批 sibling 的结果按 `task_id` 存放，不以完成顺序决定语义。
- 若后续任务依赖 sibling 的中间数据，应由父调度器将选定结果显式加入新的 Envelope，或使用受限 Task Store，不允许 sibling 互相扫描运行记录。
- 对允许取消的运行，在父图取消/超时后停止派发新 child，并向在途 child 传播取消；不支持安全取消的外部操作必须通过宿主执行器声明和管理。

### 4.3 取消和超时

树级执行上下文包含取消令牌和 deadline。取消状态应传播给所有子级。运行时应区分：

- 用户取消；
- 父运行超时；
- 子运行本地超时；
- 树级预算耗尽；
- 审批暂停。

子 Agent 到达本地预算上限时返回 `budget_exceeded`，父 Agent 可根据策略终止整树、削减其他任务预算或返回部分结果；不能将预算耗尽包装成空字符串。

## 5. 结果汇总与跨 Agent 共享

### 5.1 默认采用父级汇总，不做共享对话

对多数任务，建议：

```text
Parent dispatches N children
  → each child returns bounded TaskResult
  → parent validates result status/schema
  → parent receives summaries + selected structured fields
  → parent synthesizes final answer with citations/provenance
```

父级不需要读取每个 child 的全部 messages。遇到冲突或需要核验时，再按 `evidence_refs` 读取有限原文/证据。

### 5.2 Task Store / Blackboard（仅在需要时启用）

若多个子任务需要共享中间产物，优先使用显式的、任务范围内的 `TaskStore`，而不是共享聊天历史：

- key 以 `tenant_id / root_run_id / task_id / artifact_id` 形成范围；
- 每个写入项带 schema、来源 child run、创建时间、敏感级别和版本；
- 读访问通过宿主授权检查，限制 sibling 可见范围；
- 数据默认只在 root task 生命周期内有效，按宿主 retention 清理；
- 对大内容使用 artifact 引用，父/子上下文只携带摘要和必要字段；
- 一个 Agent 的 memory 不应默认成为其他 Agent 的 memory；跨任务长期记忆写入必须由宿主明确授权和治理。

第一阶段不建议实现通用共享 Blackboard。若确有并行研究协作需求，应先限定共享数据类型和访问关系，避免共享可变自由文本状态带来的竞争、污染和信息泄漏。

## 6. 目标架构与时序

### 6.1 组件架构

```text
Host / Root Orchestrator
  ├─ DelegationPolicy：可调用子 Agent allowlist、深度/数量/权限策略
  ├─ BudgetCoordinator：树级 token/成本/并发/deadline 分配
  ├─ Context Handoff Builder：从父状态构造最小 DelegationEnvelope
  ├─ SubagentRunner：宿主解析 Agent、创建 child run、装配独立 deps
  └─ Result Collector：校验 TaskResult、限流、保存关联关系
          │
          ├── Child AgentRuntime A
          │     ├─ 独立 ContextBuilder
          │     ├─ 子 Agent 专属工具 allowlist / memory policy
          │     └─ 独立 transcript / checkpoint
          ├── Child AgentRuntime B
          │     └─ 独立 transcript / checkpoint
          └── Parent ContextBuilder
                └─ 只纳入选定 TaskResult summary/output/evidence refs

可选 Host TaskStore / ArtifactStore
  └─ 受租户、root task、task ID 和权限约束的显式共享数据
```

### 6.2 调用时序

```text
1. Parent Decide 选择 delegate(agent_ref, task_spec)
2. DelegationPolicy 校验目标 Agent 是否在 parent allowlist 且可调用
3. Handoff Builder 选择最小输入，验证 schema/引用权限和敏感级别
4. BudgetCoordinator 原子分配 child allocation，检查并发/数量/deadline
5. Host SubagentRunner 创建独立 child run 与 transcript
6. Child AgentRuntime 用 child 自身配置构造 Context View 并执行
7. Child 返回结构化 TaskResult；执行状态、usage 和结果被持久化/计量
8. Result Collector 验证状态、schema、大小、证据引用和预算
9. Parent ContextBuilder 只将有用 summary/结构化字段加入后续请求
10. Parent 汇总；完整 child transcript 仍按独立权限访问
```

任何步骤被拒绝都应返回明确的委派错误/状态，并留下可审计事件；失败不能伪装成成功文本。

## 7. 与现有 Ouroboros 的改动点

### 7.1 框架层

| 改动 | 建议位置 | 目的 |
|---|---|---|
| 结构化委派请求与结果 | `ports.py` / 新的 `agents/` 或 `tasks/` 模块 | 替代仅有 task 字符串和字符串结果的交接契约 |
| Agent 调用策略 | Runtime deps 或宿主提供的 Policy port | 限制 parent 可调用 Agent allowlist；与工具权限分开 |
| 子运行上下文 | `InvokeContext` 或新 `DelegationContext` | 透传 parent/root/task IDs、deadline、预算引用和取消令牌 |
| 树级预算协调 | 框架协议 + 宿主实现 | 原子分配并累计并发子运行的 token/成本 |
| 结果限流和验证 | SubagentRunner/Result Collector 边界 | 防止子结果无界回灌，校验 output schema 与来源 |
| 事件与追踪 | `RuntimeEvent` / `EventSink` | 记录 delegation requested/started/completed/failed/budget/canceled |
| Context Builder | 单 Agent 上下文管理组件 | 每个子 Agent 独立构建并遵循 child allocation |
| 保持向后兼容 | `AgentSkill`、`SubagentRunner` | 先提供适配器或新版本协议，不直接破坏现有公共 API |

### 7.2 PlatformAgent 宿主层

- 子 Agent 仍由宿主解析和装配；增加显式可调用 Agent allowlist，不让 `agent_ref` 只通过租户同属就自动可调用。
- 每个 child 使用独立运行 transcript；`session_id` 默认隔离。若业务要复用会话记忆，需显式开启并按 tenant/user/agent 范围授权。
- 从父级创建 child run 时持久化 `root_run_id`、`parent_run_id`、`task_id`、分配预算、实际 usage 和最终状态。
- 更新 `DbSubagentRunner`，接收结构化 Envelope，返回结构化结果；保留当前独立 DB session 规则。
- 实现 BudgetCoordinator 的原子扣减/用量结算，处理多个并行 child 竞态。
- 前端呈现运行树、委派输入摘要、child 状态/耗时/用量、结果摘要、证据来源、预算和取消状态；敏感原文仍按权限显示。
- 如不做持久共享 TaskStore，短期可以让结果完全经父级 Result Collector 回传，不需要新数据库模型。

## 8. 失败语义与安全规则

- 子 Agent 目标无权调用、已禁用或跨租户：委派前拒绝，不泄露目标 Agent 是否存在。
- Envelope 引用无权访问或过期：拒绝读取该引用，返回具体可处理的权限错误。
- 子 Agent 失败：返回 `failed` 和安全错误摘要，不把堆栈或密钥交给父模型。
- 部分结果：返回 `partial`、已完成字段及缺失项，父级可选择继续或向用户披露。
- 输出 schema 错误或超限：保留原始子运行结果，拒绝当作合格输出；允许有限格式修复但不重复执行副作用任务。
- 预算耗尽：阻止后续 LLM/工具调用，结算已用预算，返回 `budget_exceeded`。
- 父级取消：阻止新委派并传播取消；已执行的外部副作用由宿主执行器报告不可撤销状态。
- 子 Agent 输入、记忆、artifact 和工具结果均视为不可信内容；保留来源和安全边界标注。
- 父子/兄弟关系不自动构成数据访问权限；所有引用读取由宿主鉴权。

## 9. 分阶段落地

### 阶段一：巩固现有父子调用边界

- 明确 child 独立 history、独立 session、独立 memory 的默认规则。
- 定义简单的结构化 `DelegationRequest`/`SubagentResult` 适配器，旧字符串 API 暂时兼容。
- 增加 child 结果大小上限、状态映射和 parent/root/task/child 追踪 ID。
- 先实现每个 child 的局部上下文预算和 root 总用量统计；总量超限后停止继续委派。

### 阶段二：最小交接与树级预算

- Envelope 支持结构化输入、约束、输出 schema 和显式证据引用。
- 增加原子预算分配、并发上限、总 deadline 和树级取消。
- 前端/运行追踪能够观察各 child 的用量和结果，不暴露无权原文。

### 阶段三：有范围的结果共享

- 根据真实任务需求引入 scoped TaskStore/ArtifactStore。
- 实施 ACL、TTL、引用审计和跨 Agent 数据治理。
- 增加结果冲突检测、证据核验和结构化汇总。

### 阶段四：团队/DAG 协作

- 在存在明确需求时，将 Envelope、TaskResult、预算协调和取消能力接入任务 DAG 调度器。
- 共享内容采用显式数据依赖，不让 Agent 之间共享可变对话状态。
- 对动态协作、re-plan 和共享黑板分别做权限、预算和故障语义设计，不与基本委派能力混为一谈。

## 10. 测试与验收标准

1. 父 Agent history、system prompt 和工具列表不会自动出现在 child prompt 中。
2. child 只收到 Envelope 指定字段和已授权 context refs；越权引用不能读取。
3. 不同 child 的消息、短期记忆和运行状态相互隔离；并行执行没有共享可变 state。
4. 子结果 schema、状态和大小经过校验；失败/暂停/部分成功不被伪装成普通成功字符串。
5. 多个并行 child 的用量累计不能超过 root budget；竞态下预算扣减是原子的。
6. 父运行取消、截止时间或预算耗尽能阻止新子任务，并传播给可取消的在途 child。
7. 父级上下文只纳入经筛选的结果摘要/字段；大结果通过受权引用访问。
8. child 的完整 transcript 仍然可独立追踪和审计；父级通过 run ID 不能绕过访问控制。
9. 所有事件可关联 root、parent、child、task 和 trace ID，但普通日志不包含未脱敏正文。
10. 现有单 Agent `run()`、`resume()` 和父子调用兼容适配器继续工作。

## 11. 决策摘要

- 默认“每个 Agent Run 独立上下文”，而不是共享同一聊天历史。
- 父到子使用最小 `DelegationEnvelope`；子到父使用限长、结构化、带来源的 `TaskResult`。
- 多 Agent 的上下文上限必须与单 Agent Context Builder 和树级预算协调器结合。
- 默认不共享长期记忆；需要跨 Agent 共享时，用显式授权的任务范围 Store/Artifact 引用。
- 先做隔离、结果契约、预算与取消，再做 blackboard、共享记忆或开放式 Agent 协作。

## 12. 相关文档

- [单 Agent 上下文管理设计方案](./上下文管理设计方案.md)：每次模型请求的预算、压缩、工具与历史治理。
- [多任务依赖调度与新架构设计](./多任务依赖调度与新架构设计.md)：任务图、依赖调度和结果合并方案。
- [Ouroboros 架构总结](./架构总结.md)：当前 AgentRuntime、端口、AgentSkill 和宿主边界。
- [Agent 框架层详细设计](./Agent框架层详细设计.md)：Ports & Adapters 责任划分。
