import json
import os
from datetime import datetime, timezone
from typing import Any, List
from src.config import get_settings, ensure_dir

def append_history(event: dict[str, Any]) -> None:
    s = get_settings()
    ensure_dir(s.history_path.parent)
    event = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with open(s.history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def read_history(limit: int = 200) -> List[dict[str, Any]]:
    s = get_settings()
    if not s.history_path.exists():
        return []
    lines: List[str] = []
    with open(s.history_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = 8192
        buf = b""
        while size > 0 and len(lines) <= limit:
            step = block if size >= block else size
            size -= step
            f.seek(size)
            buf = f.read(step) + buf
            while b"\n" in buf:
                line, _, rest = buf.rpartition(b"\n")
                buf = line
                if rest:
                    try:
                        lines.append(rest.decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
                if len(lines) >= limit:
                    break
        if buf and len(lines) < limit:
            lines.append(buf.decode("utf-8", errors="ignore"))
    events: List[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except Exception:
            continue
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return events[:limit]
