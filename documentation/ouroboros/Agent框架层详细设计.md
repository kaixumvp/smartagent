# Ouroboros Agent 框架层详细设计

## 1. 设计目标

Ouroboros 是可独立安装的业务无关 Agent Runtime。它提供运行机制和扩展协议，不持有 PlatformAgent 的
HTTP、数据库、租户、凭据或权限数据。

```text
宿主 API / Services
        │ 组装 AgentDefinition + RuntimeDeps
        ▼
AgentRuntime.run / resume
        │
        ├── Plan → Decide → Execute → Observe
        ├── PluginRegistry → Tools / Skills
        └── ports → 宿主适配器
```

当前发布版本 2.0.0 的包名为 `ouroboros`。版本细节见[框架路线图](./版本规划.md)。

## 2. 运行时职责

- `AgentDefinition` 描述 Agent 配置和注册插件。
- `RunContext` 绑定单次运行的标识、会话和调用上下文。
- `RuntimeConfig` 约束迭代数、超时、子 Agent 深度和 token 预算等运行策略。
- `RuntimeDeps` 注入 LLM、权限、记忆、知识、事件、checkpoint、指标和子 Agent 等能力。
- `AgentRuntime` 在内部状态上驱动 Plan → Decide → Execute → Observe，产出 `RunResult` 和运行时事件。
- `run()` 开始新运行；`resume()` 从宿主 checkpoint 恢复运行。

框架运行时不提供 durable task queue；宿主负责跨请求持久化、调度和服务重启后的恢复。

## 3. 扩展模型

`Plugin` 是 Tool、Skill、Knowledge 等能力的统一协议；`PluginManifest` 声明能力种类、调用 schema、
权限等级、审批需求与依赖。`PluginRegistry` 管理插件注册、解析及模型调用 schema。

Skill 执行分为：

- `prompt`：向运行上下文提供指令/提示内容。
- `function`：在受控执行边界调用函数。
- `flow`：委托宿主的流程执行器。
- `agent`：通过宿主 `SubagentRunner` 调度子 Agent。

工具/插件的真实副作用和网络访问仍由宿主配置及执行环境负责。

## 4. Ports & Adapters

框架在 `ouroboros.ports` 定义协议与纯数据类型，宿主在运行前注入实现。协议定义不等同于宿主实现已经存在：
例如框架可以定义 `Knowledge` 和 `Retriever`，PlatformAgent 仍需自行实现索引、摄取、查询和来源管理。

框架包含可选的 memory/gateway/registry 实现模块，但宿主不得把框架内部的 `AgentState`、节点调用顺序或私有
模块当成数据库 schema 或稳定跨版本接口。公共符号兼容性由框架 SemVer 契约管理。

## 5. 事件、恢复和安全边界

- `RuntimeEvent` 描述运行事件；SSE/HTTP 编码、持久化和事件重放由宿主负责。
- checkpoint 接口定义恢复机制；生产级持久化由宿主实现。
- PermissionChecker 是策略决策端口；用户、角色、Grant、审计和租户边界由宿主实现。
- 框架可以提供 function/tool 执行辅助与输入输出处理，但不能替代部署环境的 OS 级隔离、网络策略或密钥管理。

## 6. 对应实现

代码与测试位于 [`application/ouroboros/`](../../application/ouroboros/)；使用方式见
[框架使用文档](./Agent框架使用文档.md)，Plugins/Tools/Skills 关系见
[UML](./plugins-tools-skills-uml.md)。
