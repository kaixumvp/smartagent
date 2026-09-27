import logging

from src.core.state import AgentState

logger = logging.getLogger(__name__)


async def run_observe(state: AgentState) -> dict:
    iteration = state.get("iteration", 0) + 1
    messages = list(state.get("messages") or [])

    tool_results = state.get("tool_results")
    if tool_results:
        # V0.4: one tool message per parallel call, each linked by its tool_call_id.
        tool_call_ids = state.get("tool_call_ids") or []
        for i, result in enumerate(tool_results):
            msg = {"role": "tool", "content": result}
            if i < len(tool_call_ids):
                msg["tool_call_id"] = tool_call_ids[i]
            messages.append(msg)
    else:
        last = state.get("last_tool_result")
        if last is not None:
            msg = {"role": "tool", "content": last}
            tool_call_id = state.get("tool_call_id")
            if tool_call_id:
                msg["tool_call_id"] = tool_call_id
            messages.append(msg)

    updates: dict = {"messages": messages, "iteration": iteration}

    # Reached the iteration cap → finish as a fallback to avoid an infinite loop
    if iteration >= state.get("max_iterations", 20):
        logger.warning("iteration cap reached: run_id=%s iteration=%d", state.get("run_id"), iteration)
        updates["status"] = "completed"
        updates["result"] = state.get("result") or state.get("last_tool_result") or "Reached the iteration cap, task ended."
    return updates
