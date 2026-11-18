from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass
class ChunkDraft:
    text: str
    heading_path: str
    start_offset: int
    end_offset: int


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            cut = text.rfind("\n", start, end)
            if cut <= start + max_chars // 2:
                cut = end
            end = cut
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


def chunk_markdown(markdown: str, max_chars: int = 800, overlap: int = 120) -> list[ChunkDraft]:
    markdown = markdown or ""
    headings: list[tuple[int, str, str]] = [
        (m.start(), m.group(1), m.group(2).strip()) for m in HEADING_RE.finditer(markdown)
    ]
    if not headings:
        pieces = _split_long(markdown, max_chars, overlap)
        drafts = []
        cursor = 0
        for piece in pieces:
            idx = markdown.find(piece, cursor)
            if idx < 0:
                idx = cursor
            drafts.append(ChunkDraft(piece, "", idx, idx + len(piece)))
            cursor = idx + len(piece)
        return drafts

    sections: list[tuple[str, str, int, int]] = []
    for i, (pos, hashes, title) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(markdown)
        body = markdown[pos:end].strip()
        sections.append((hashes, title, pos, body))

    stack: list[tuple[int, str]] = []
    drafts: list[ChunkDraft] = []
    for hashes, title, pos, body in sections:
        level = len(hashes)
        stack = [item for item in stack if item[0] < level]
        stack.append((level, title))
        path = " / ".join(t for _, t in stack)
        for piece in _split_long(body, max_chars, overlap):
            idx = markdown.find(piece, pos)
            if idx < 0:
                idx = pos
            drafts.append(ChunkDraft(piece, path, idx, idx + len(piece)))
    return drafts
