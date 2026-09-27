"""示例公共工具：离线可运行的脚本化 Mock LLM + 安全读取密钥。

所有示例默认离线运行（无需真实 API key）；要接真实模型时，设置环境变量并改用
`real_llm()`（见下方）。
"""

from __future__ import annotations

import os

from src.llm.base import LLMResponse, ToolCall, Usage
from src.llm.litellm_gateway import LiteLLMGateway


class ScriptedLLM:
    """按顺序返回预设响应的 LLM，并记录每次调用，用于离线演示与断言。

    - ``chat`` 依次 pop 一个响应（与 LLMGateway 协议一致）。
    - ``calls`` 记录每条请求的 messages/model/tools，方便观察 memory/知识上下文是否被注入。
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        return self._responses.pop(0)


def plan(description: str) -> LLMResponse:
    """计划节点的响应：一个单步计划。"""
    return LLMResponse(
        content=f'[{{"description": "{description}"}}]',
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def tool_call(name: str, arguments: dict, tool_call_id: str = "call_1") -> LLMResponse:
    """decide 节点的响应：让 LLM 选择调用某个插件。"""
    return LLMResponse(tool_calls=[ToolCall(id=tool_call_id, name=name, arguments=arguments)])


def finish(text: str) -> LLMResponse:
    """decide 节点的响应：收尾给最终答案。"""
    return LLMResponse(content=text)


def real_llm(default_model: str = "deepseek/deepseek-chat"):
    """从环境变量读取真实 LLM 配置；未设置 key 时抛错提示。

    环境变量：
        OUROBOROS_MODEL / DEEPSEEK_API_KEY（或 OUROBOROS_API_KEY）
    """
    model = os.getenv("OUROBOROS_MODEL", default_model)
    api_key = os.environ.get("OUROBOROS_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "请设置环境变量 OUROBOROS_API_KEY（或 DEEPSEEK_API_KEY）后重试。"
        )
    return LiteLLMGateway(model=model, api_key=api_key), model
