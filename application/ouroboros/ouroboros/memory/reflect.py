"""Rule-based importance reflection for memory consolidation (V0.3 baseline).

`reflect` scores a candidate fragment 0..1 without calling an LLM: durable, first-person
facts and preferences rank higher than transient chatter. V0.4 may replace this with an
LLM-based scorer behind the same ``score(content) -> float`` interface.
"""

from __future__ import annotations

import re

_PREFERENCE = re.compile(
    r"(喜欢|偏好|想要|希望|认为|觉得|必须|不要|总是|从不|prefer|like|want|should|must|always|never|don't)",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(i|me|my|mine|we|our|我|我们|我的|咱们)\b", re.IGNORECASE)


class Reflector:
    """Scores a memory candidate by simple heuristics. Output is clamped to [0, 1]."""

    def __init__(
        self,
        min_words: int = 4,
        preference_bonus: float = 0.3,
        first_person_bonus: float = 0.15,
    ) -> None:
        self._min_words = min_words
        self._preference_bonus = preference_bonus
        self._first_person_bonus = first_person_bonus

    def score(self, content: str) -> float:
        text = (content or "").strip()
        if not text:
            return 0.0
        score = 0.3
        if len(text.split()) >= self._min_words:
            score += 0.1
        if _PREFERENCE.search(text):
            score += self._preference_bonus
        if _FIRST_PERSON.search(text):
            score += self._first_person_bonus
        return round(min(1.0, score), 3)


__all__ = ["Reflector"]
