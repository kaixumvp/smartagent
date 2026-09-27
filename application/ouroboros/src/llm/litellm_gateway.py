import json
import logging

import litellm

from src.llm.base import LLMResponse, ToolCall, Usage

logger = logging.getLogger(__name__)


class LiteLLMGateway:
    """LiteLLM implementation of the LLM Gateway (single vendor, OpenAI-compatible)."""

    def __init__(self, model: str = "", api_key: str = "", api_base: str | None = None) -> None:
        self._model = model
        self._api_key = api_key
        self._api_base = api_base

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        model = model or self._model
        kwargs: dict = {"model": model, "messages": messages}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if tools:
            kwargs["tools"] = tools

        logger.debug("llm.chat: model=%s messages=%d tools=%d", model, len(messages), len(tools or []))
        resp = await litellm.acompletion(**kwargs)
        msg = resp.choices[0].message

        tool_calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            args: dict = {}
            raw = getattr(tc.function, "arguments", None)
            if raw:
                try:
                    args = json.loads(raw)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                ToolCall(id=getattr(tc, "id", "") or "", name=tc.function.name, arguments=args)
            )

        usage = resp.usage.model_dump() if resp.usage else {}
        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )
