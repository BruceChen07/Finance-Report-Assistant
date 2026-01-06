from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    headings: list[str]
    metadata: dict[str, Any]


def _is_heading(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") and (len(s) == 1 or s[1] in (" ", "\t", "#"))


def _heading_level(line: str) -> int:
    s = line.lstrip()
    n = 0
    for ch in s:
        if ch == "#":
            n += 1
        else:
            break
    return max(1, min(6, n))


def _heading_text(line: str) -> str:
    s = line.lstrip()
    s = s.lstrip("#").strip()
    return s


def _split_with_overlap(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return [p for p in parts if p]


def chunk_markdown(
    md_text: str,
    *,
    max_chars: int = 4000,
    overlap_chars: int = 300,
    base_metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    base_metadata = dict(base_metadata or {})
    lines = md_text.splitlines()

    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []
    buf: list[str] = []
    chunk_idx = 0

    def flush() -> None:
        nonlocal chunk_idx
        text = "\n".join(buf).strip()
        if not text:
            return

        headings = [t for _, t in heading_stack]
        for part in _split_with_overlap(text, max_chars=max_chars, overlap_chars=overlap_chars):
            chunk_id = f"c{chunk_idx:06d}"
            chunk_idx += 1
            meta = dict(base_metadata)
            meta["chunk_id"] = chunk_id
            meta["headings"] = headings
            chunks.append(Chunk(chunk_id=chunk_id, text=part,
                          headings=headings, metadata=meta))

    for line in lines:
        if _is_heading(line):
            flush()
            buf.clear()

            lvl = _heading_level(line)
            title = _heading_text(line)

            while heading_stack and heading_stack[-1][0] >= lvl:
                heading_stack.pop()
            heading_stack.append((lvl, title))
            continue

        if line.strip() == "":
            if buf and buf[-1].strip() != "":
                buf.append("")
            continue

        buf.append(line)

    flush()
    return chunks


def chunks_from_markdown_file(
    md_path: Path,
    *,
    max_chars: int = 4000,
    overlap_chars: int = 300,
    base_metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    meta = dict(base_metadata or {})
    meta.setdefault("source_path", str(md_path))
    return chunk_markdown(text, max_chars=max_chars, overlap_chars=overlap_chars, base_metadata=meta)
