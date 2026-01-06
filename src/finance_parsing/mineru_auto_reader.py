from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MinerUAutoOutput:
    auto_dir: Path
    markdown_path: Path
    images_dir: Path | None
    content_list_json: Path | None
    model_json: Path | None


def _pick_latest(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def find_auto_output(job_dir: Path) -> MinerUAutoOutput:
    md: Path | None = None
    for pat in ("auto/*.md", "txt/*.md", "ocr/*.md"):
        md = _pick_latest(list(job_dir.rglob(pat)))
        if md is not None:
            break

    if md is None:
        md = _pick_latest(list(job_dir.rglob("*.md")))

    if md is None:
        raise FileNotFoundError("No Markdown found under job_dir.")

    out_dir = md.parent
    images_dir = out_dir / "images"
    if not images_dir.exists():
        images_dir = None

    content_list_json = _pick_latest(list(out_dir.glob("*_content_list.json")))
    model_json = _pick_latest(list(out_dir.glob("*_model.json")))

    return MinerUAutoOutput(
        auto_dir=out_dir,
        markdown_path=md,
        images_dir=images_dir,
        content_list_json=content_list_json,
        model_json=model_json,
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
