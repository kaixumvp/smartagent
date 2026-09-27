# Plugins, Tools and Skills UML

本文档描述 Ouroboros 当前实现中 plugins、tools、skills 的核心结构和调用关系。

## 1. 核心类图

```mermaid
classDiagram
    direction LR

    class Plugin {
        <<Protocol>>
        +kind: str
        +manifest: PluginManifest
        +setup(config: dict) async
        +invoke(ctx: InvokeContext, **kw) async
        +teardown() async
    }

    class PluginManifest {
        <<Pydantic Model>>
        +name: str
        +version: str
        +kind: str
        +description: str
        +parameters: dict
        +permission: str
        +requires_approval: bool
        +function_name: str
    }

    class InvokeContext {
        <<Pydantic Model>>
        +tenant_id: str
        +user_id: str
        +run_id: str
        +session_id: str
        +subagent_depth: int
    }

    class PluginRegistry {
        -_by_key: dict
        -_by_fn: dict
        +register(plugin: Plugin)
        +register_tool(tool: Tool)
        +get(key: str) Plugin
        +resolve(keys: list[str]) list~Plugin~
        +to_openai_schema(keys: list[str]) list~dict~
        +invoke(key: str, ctx: InvokeContext, **kw) async
    }

    class Tool {
        <<Protocol>>
        +name: str
        +description: str
        +parameters: dict
        +permission: str
        +run(**kwargs) async
    }

    class BaseTool {
        <<Abstract Base Class>>
        +id: str
        +name: str
        +description: str
        +permission: str
        +parameters: dict
        +run(**kwargs) async
    }

    class ToolAsPlugin {
        <<Adapter>>
        -_tool: Tool
        +kind: tool
        +manifest: PluginManifest
        +invoke(ctx: InvokeContext, **kw) async
    }

    class CalculatorTool {
        +name: calculator
        +run(expression: str) async
    }

    class HttpTool {
        +name: http_request
        +run(method, url, ...) async
    }

    class Skill {
        <<Abstract Base Class>>
        +kind: skill
        +type: str
        -_manifest: PluginManifest
        -_body: dict
        +manifest: PluginManifest
        +body: dict
        +invoke(ctx: InvokeContext, **kw) async
    }

    class PromptSkill {
        +type: prompt
        +invoke(ctx, **kw) async
    }

    class FunctionSkill {
        +type: function
        +invoke(ctx, **kw) async
    }

    class FlowSkill {
        +type: flow
        +invoke(ctx, **kw) async
    }

    class AgentSkill {
        +type: agent
        +invoke(ctx, **kw) async
    }

    class SkillManager {
        -_run_subagent: RunSubagent
        -_run_flow: RunFlow
        +build(record: dict) Skill
    }

    class Graph {
        +plan(state)
        +decide(state)
        +execute(state)
        +observe(state)
    }

    Plugin <|.. ToolAsPlugin : implements
    Plugin <|.. Skill : implements
    Tool <|.. BaseTool : implements
    BaseTool <|-- CalculatorTool
    BaseTool <|-- HttpTool
    Skill <|-- PromptSkill
    Skill <|-- FunctionSkill
    Skill <|-- FlowSkill
    Skill <|-- AgentSkill
    ToolAsPlugin o-- Tool : wraps
    PluginRegistry o-- Plugin : stores
    Plugin --> PluginManifest : exposes
    Plugin --> InvokeContext : receives
    SkillManager ..> Skill : builds
    SkillManager ..> PluginManifest : creates
    Graph ..> PluginRegistry : executes through
```

### 关键设计点

- `Plugin` 是统一运行时协议，要求插件提供 `manifest`、`setup`、`invoke` 和 `teardown`。
- `Tool` 保留旧的 `run(**kwargs)` 接口；`ToolAsPlugin` 将它适配为 `Plugin.invoke(ctx, **kw)`。
- `Skill` 是 `Plugin` 的抽象实现，具体形式由 `type` 区分：`prompt`、`function`、`flow`、`agent`。
- `PluginManifest.function_name` 负责生成提供给 LLM 的函数名：普通 tool 使用原名，skill 使用 `skill_` 前缀。
- `PluginRegistry` 不区分 tool 和 skill 的执行入口，统一通过 `register`、`get`、`invoke` 管理。

## 2. Graph 调用时序图

```mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant SM as SkillManager
    participant R as PluginRegistry
    participant G as Graph
    participant LLM as LLM Gateway
    participant E as Execute Node
    participant S as Skill/Tool

    App->>SM: build(skill_record)
    SM->>SM: build_skill(type, manifest, body)
    SM-->>App: Skill instance
    App->>R: register(skill)
    App->>R: register_tool(tool)
    R->>R: ToolAsPlugin(tool)
    R->>R: index by name/ref/function_name

    App->>G: build_graph(llm, registry, model, config)
    App->>G: run_agent(initial_state)
    G->>LLM: plan messages
    LLM-->>G: plan
    G->>R: to_openai_schema()
    R-->>G: tools + skills schemas
    G->>LLM: decide(messages, tools)
    LLM-->>G: assistant tool call
    G->>E: execute(state.action, state.action_input)
    E->>R: invoke(action, context, **input)
    R->>S: invoke(context, **input)
    S-->>R: result
    R-->>E: result
    E-->>G: last_tool_result
    G->>G: observe(result, iteration)
    G->>LLM: next decide request
    LLM-->>G: final answer
    G-->>App: final state + steps
```

## 3. 注册和解析关系

```mermaid
flowchart TD
    A[Application assembly] --> B[SkillManager.build(record)]
    B --> C[Concrete Skill]
    D[Legacy Tool] --> E[PluginRegistry.register_tool]
    E --> F[ToolAsPlugin]
    C --> G[PluginRegistry.register]
    F --> G
    G --> H{Plugin indexes}
    H --> H1[bare name]
    H --> H2[kind:name@version]
    H --> H3[manifest.function_name]
    H1 --> I[PluginRegistry.get/resolve/invoke]
    H2 --> I
    H3 --> I
    I --> J[Unified Plugin.invoke]
```

## 4. 当前代码对应关系

| UML 元素 | 代码位置 |
| --- | --- |
| `Plugin`, `PluginManifest`, `InvokeContext`, `ToolAsPlugin` | `src/ouroboros/plugins/base.py` |
| `PluginRegistry` | `src/ouroboros/plugins/registry.py` |
| `Tool`, `BaseTool`, `ToolResult` | `src/ouroboros/tools/base.py` |
| Built-in tools | `src/ouroboros/tools/builtin/` |
| `Skill`, `build_skill` | `src/ouroboros/skills/base.py` |
| `PromptSkill`, `FunctionSkill`, `FlowSkill`, `AgentSkill` | `src/ouroboros/skills/` |
| `SkillManager` | `src/ouroboros/skills/manager.py` |
| Graph execution | `src/ouroboros/core/graph.py` and `src/ouroboros/core/nodes/` |

## 5. 示例

在 Graph 中集成 skill 的最小示例见 `example/skills_example.py`：

1. 用 `SkillManager` 从 record 构建 skill。
2. 用 `PluginRegistry.register` 注册 skill。
3. 用 `build_graph` 将 registry 交给运行图。
4. LLM 根据 schema 选择 skill。
5. `execute` 节点通过 `registry.invoke` 执行 skill。
