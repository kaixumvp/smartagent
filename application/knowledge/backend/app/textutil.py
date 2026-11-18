import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text or "")]


def l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def hashed_embedding(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for token in tokenize(text):
        vec[hash(token) % dim] += 1.0
    return l2_normalize(vec)


def term_overlap(query_tokens: list[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    counts = Counter(tokenize(text))
    hit = sum(1 for t in query_tokens if counts[t] > 0)
    return hit / len(set(query_tokens))
