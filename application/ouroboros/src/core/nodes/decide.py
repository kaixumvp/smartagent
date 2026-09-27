import json
import logging

from src.core.state import AgentState
from src.ports import LLMGateway
from src.security import TOOL_RESULT_GUARD, wrap_tool_result

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM = "You are a general-purpose assistant. Call the calculator tool for arithmetic problems."


async def run_decide(
    state: AgentState,
    llm: LLMGateway,
    model: str,
    tool_schemas: list[dict],
    system_prompt: str | None = None,
) -> dict:
    system = system_prompt or _DEFAULT_SYSTEM
    messages: list[dict] = [{"role": "system", "content": system}]

    plan = state.get("plan") or []
    if plan:
        plan_text = "\n".join(f"{s['id']}. {s['description']}" for s in plan)
        messages.append({"role": "system", "content": f"Current plan:\n{plan_text}"})

    messages.extend(state.get("messages") or [])

    last = state.get("last_tool_result")
    if last:
        # Basic prompt-injection defense: mark the tool output as untrusted external data.
        messages.append({"role": "system", "content": TOOL_RESULT_GUARD})
        messages.append({"role": "user", "content": f"Tool result:\n{wrap_tool_result(last)}"})

    resp = await llm.chat(messages=messages, model=model, tools=tool_schemas or None)

    if resp.tool_calls:
        tool_calls = [
            {"id": tc.id or f"call_{tc.name}", "name": tc.name, "arguments": tc.arguments}
            for tc in resp.tool_calls
        ]
        messages_history = list(state.get("messages") or [])
        messages_history.append({
            "role": "assistant",
            "content": resp.content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ],
        })
        first = tool_calls[0]
        logger.debug("decide: action=%s (%d tool calls)", first["name"], len(tool_calls))
        return {
            "action": first["name"],
            "action_input": first["arguments"],
            "tool_call_id": first["id"],
            "tool_calls": tool_calls,
            "messages": messages_history,
            "token_usage": resp.usage.model_dump(),
        }

    logger.debug("decide: finish")
    return {"action": "__finish__", "result": resp.content or "", "token_usage": resp.usage.model_dump()}
