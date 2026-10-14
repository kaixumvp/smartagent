from typing import TypedDict


class PlanStep(TypedDict):
    id: int
    description: str
    status: str  # pending|running|done|failed


class AgentState(TypedDict, total=False):
    agent_id: str
    run_id: str | None
    session_id: str
    tenant_id: str
    user_id: str | None
    task: str  # User input
    messages: list[dict]  # Conversation history (system + user + assistant + tool)
    plan: list[PlanStep]  # Produced by the Plan node
    action: str | None  # Chosen by the Decide node: a plugin function name or "__finish__"
    action_input: dict | None  # Plugin input arguments
    tool_call_id: str | None  # ID linking the assistant tool call to its tool result
    tool_calls: list[dict]  # All tool calls of the current round (V0.4 parallel execution)
    tool_call_ids: list[str]  # IDs of the executed calls (for appending N tool messages)
    tool_results: list[str]  # Per-call results (V0.4 parallel execution)
    last_tool_result: str | None  # Output of the most recent tool/skill call
    iteration: int  # Number of plugin executions so far
    max_iterations: int  # Upper bound on the Decide→Execute loop
    status: str  # running|completed|failed
    result: str | None  # Final answer
    error: str | None
    plugins: list[dict]  # Assembled plugin references [{type, ref, config}]
    memory_ctx: list[dict]  # Recalled long-term memories injected into planning
    approvals: list[str]  # High-risk resources already approved within this run
    pending_approvals: list[dict]  # High-risk plugins currently blocked on human approval
    subagent_depth: int  # Parent→child nesting depth (guards against runaway recursion)
    max_subagent_depth: int  # Hard cap on sub-agent nesting (V0.3 enforcement)
    trace_id: str | None  # Distributed-trace id, propagated into InvokeContext (V0.4)
    system_prompt: str | None
    token_usage: dict  # Accumulated token usage
