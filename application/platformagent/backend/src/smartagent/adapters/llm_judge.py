"""LLM-as-judge (business adapter).

Implements the framework `Judge` port (`ouroboros.ports`). The framework ships only
`HeuristicJudge` (substring match, `evaluation/golden.py:41`), which is fine for smoke evals
but cannot score an answer that is right while worded differently — that is what this is for.

The judge never raises: a malformed verdict degrades to a presence check and says so in
`reason`, because an evaluation that dies on one unparseable response is worse than one that
reports a soft score.
"""

import json
import logging
import re

from src.ports import JudgeVerdict

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a strict evaluator of AI assistant answers. "
    "Reply with ONLY a JSON object, no prose and no code fences: "
    '{"score": <0..1 float>, "passed": <true|false>, "reason": "<one short sentence>"}'
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _build_prompt(task: str, output: str, reference: str | None) -> str:
    parts = [f"Task:\n{task}", f"Assistant answer:\n{output or '(empty)'}"]
    if reference:
        parts.append(f"Reference answer:\n{reference}")
        parts.append(
            "Score how well the assistant answer matches the reference in meaning. "
            "Different wording is acceptable; contradicting or missing key facts is not."
        )
    else:
        parts.append("No reference is available. Score the answer's relevance and usefulness for the task.")
    return "\n\n".join(parts)


class LlmJudge:
    """Scores an answer with an LLM. Bypasses tiered routing on purpose: the judge model is
    fixed so scores stay comparable across evaluations."""

    def __init__(self, gateway, model: str) -> None:
        self._gateway = gateway
        self._model = model

    async def judge(self, *, task: str, output: str, reference: str | None = None) -> JudgeVerdict:
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(task, output, reference)},
        ]
        try:
            resp = await self._gateway.chat(messages, model=self._model, tools=None)
        except Exception as exc:  # noqa: BLE001 — a judge outage must not abort the evaluation
            logger.warning("judge call failed: %s", exc)
            return _degraded(output, f"judge unavailable ({exc})")

        return _parse(resp.content or "", output)


def _parse(content: str, output: str) -> JudgeVerdict:
    """Parse the verdict, tolerating code fences and surrounding prose."""
    match = _JSON_BLOCK.search(content)
    if match is None:
        return _degraded(output, "judge returned no JSON verdict")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _degraded(output, "judge returned malformed JSON")

    try:
        score = min(1.0, max(0.0, float(data.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0
    passed = data.get("passed")
    if not isinstance(passed, bool):
        passed = score >= 0.6
    reason = str(data.get("reason") or "")[:500]
    return JudgeVerdict(score=score, passed=passed, reason=reason)


def _degraded(output: str, why: str) -> JudgeVerdict:
    """Fallback verdict: presence check, clearly labelled so nobody reads it as a real score."""
    present = bool((output or "").strip())
    return JudgeVerdict(
        score=0.5 if present else 0.0,
        passed=present,
        reason=f"[degraded] {why}; fell back to a presence check",
    )


__all__ = ["LlmJudge"]
