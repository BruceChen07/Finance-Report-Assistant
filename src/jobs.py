import json
import os
import re
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from src.config import get_settings, ensure_dir
from src.converter import candidate_commands, search_md, search_default_md, normalize_mineru_mode, resolve_cli
from src.history import append_history

@dataclass
class JobState:
    job_id: str
    user: str
    stage: str
    percent: int
    created_at: float
    updated_at: float
    ok: bool | None
    error: str | None
    pdf_name: str
    job_dir: Path
    md_path: Path | None
    subscribers: List[queue.Queue[str]]

_JOBS: Dict[str, JobState] = {}
_JOBS_LOCK = threading.Lock()

def get_job(job_id: str) -> JobState | None:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)

def publish_event(job_id: str, event: dict[str, Any]) -> None:
    payload = dict(event)
    payload.setdefault("job_id", job_id)
    payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
    data = json.dumps(payload, ensure_ascii=False)

    with _JOBS_LOCK:
        st = _JOBS.get(job_id)
        if st is not None:
            if "stage" in payload and isinstance(payload.get("stage"), str):
                st.stage = str(payload["stage"])
            if "percent" in payload and isinstance(payload.get("percent"), (int, float)):
                st.percent = int(payload["percent"])
            if "ok" in payload and (payload.get("ok") is None or isinstance(payload.get("ok"), bool)):
                st.ok = payload.get("ok")
            if "error" in payload:
                st.error = None if payload.get("error") is None else str(payload.get("error"))
            if "md_path" in payload and payload.get("md_path"):
                st.md_path = Path(str(payload["md_path"]))
            st.updated_at = time.time()

            for q in list(st.subscribers):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    try: q.get_nowait()
                    except Exception: pass
                    try: q.put_nowait(data)
                    except Exception: pass

def _log_job(job_id: str, level: str, stage: str, message: str, percent: int | None = None, elapsed_ms: int | None = None) -> None:
    evt: dict[str, Any] = {"type": "log", "level": level, "stage": stage, "message": message}
    if percent is not None: evt["percent"] = int(percent)
    if elapsed_ms is not None: evt["elapsed_ms"] = int(elapsed_ms)
    publish_event(job_id, evt)

def _run_cmd_stream(job_id: str, cmd: list[str], stage: str, percent_base: int, percent_span: int) -> tuple[bool, str | None, str]:
    step = int(os.getenv("FRA_PROGRESS_PERCENT_STEP", "1"))
    last_sent = -1
    start_ts = time.time()
    error_lines = []
    full_output = []
    try:
        s = get_settings()
        env = os.environ.copy()
        env["FITZ_QUIET"] = "1"
        if s.use_modelscope:
            env["MODELSCOPE_SAMESITE"] = "True"
        env_device = getattr(s, "device", "cpu")
        env["FRA_DEVICE"] = env_device
        if env_device == "cuda":
            if "CUDA_VISIBLE_DEVICES" not in env and os.getenv("CUDA_VISIBLE_DEVICES"):
                env["CUDA_VISIBLE_DEVICES"] = os.getenv("CUDA_VISIBLE_DEVICES")
            vram_limit = getattr(s, "vram_limit", 0)
            if vram_limit and vram_limit > 0 and "PYTORCH_CUDA_ALLOC_CONF" not in env:
                env["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:{vram_limit}"
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False, bufsize=1, env=env)
    except FileNotFoundError:
        _log_job(job_id, "ERROR", stage, f"command not found: {cmd[0]}")
        return False, "Command not found", ""
    except Exception as e:
        _log_job(job_id, "ERROR", stage, f"failed to start command: {cmd[0]} ({e})")
        return False, str(e), ""
    try:
        assert p.stdout is not None
        for line in p.stdout:
            line = line.rstrip("\r\n")
            full_output.append(line)
            if any(x in line for x in ["Traceback", "Error", "Exception", "RuntimeError", "ModelWrapper", "ProtocolError", "ChunkedEncodingError", "IncompleteRead"]):
                if len(error_lines) < 10: error_lines.append(line)
            
            pct_m = re.search(r"(\d{1,3})\s*%", line)
            if pct_m:
                pct = int(pct_m.group(1))
                mapped = percent_base + int((pct / 100.0) * percent_span)
                mapped = max(0, min(99, mapped))
                if mapped - last_sent >= step:
                    last_sent = mapped
                    _log_job(job_id, "INFO", stage, line, percent=mapped, elapsed_ms=int((time.time() - start_ts) * 1000))
                else:
                    _log_job(job_id, "INFO", stage, line)
            else:
                if line.strip(): _log_job(job_id, "INFO", stage, line)
        rc = p.wait()
    finally:
        if p.stdout: p.stdout.close()
    
    hint = "; ".join(error_lines) if error_lines else None
    return rc == 0 and not error_lines, hint, "\n".join(full_output)

def _convert_job(job_id: str, user: str, pdf_path: Path, job_dir: Path, backend: str | None, mode: str | None) -> None:
    job_start = time.time()
    publish_event(job_id, {"type": "progress", "stage": "prepare", "percent": 1, "ok": None})
    _log_job(job_id, "INFO", "prepare", f"job started: {pdf_path.name}")

    cmds = candidate_commands(pdf_path, job_dir, mode=mode)
    if backend and backend.strip():
        b = backend.strip()
        mineru_cli = resolve_cli("mineru")
        if b == "pipeline":
            m = normalize_mineru_mode(mode) or "auto"
            cmds = [[mineru_cli, "-p", str(pdf_path), "-o", str(job_dir), "-b", b, "-m", m]] + cmds
        else:
            cmds = [[mineru_cli, "-p", str(pdf_path), "-o", str(job_dir), "-b", b]] + cmds

    publish_event(job_id, {"type": "progress", "stage": "convert", "percent": 5, "ok": None})
    ok = False
    last_error_log = ""
    for idx, cmd in enumerate(cmds):
        _log_job(job_id, "INFO", "convert", f"Attempt {idx+1}/{len(cmds)}: {' '.join(cmd)}")
        for item in job_dir.iterdir():
            if item.is_dir() or (item.is_file() and item.suffix.lower() != ".pdf"):
                try:
                    if item.is_dir(): shutil.rmtree(item)
                    else: item.unlink()
                except Exception: pass

        cmd_ok, cmd_hint, full_log = _run_cmd_stream(job_id, cmd, stage="convert", percent_base=5, percent_span=80)
        md_path = search_md(job_dir, pdf_path.stem)
        if cmd_ok and md_path:
            ok = True
            break
        else:
            last_error_log = full_log

    if not ok:
        # Save the error log for debugging
        with open(job_dir / "conversion.log", "w", encoding="utf-8") as f:
            f.write(last_error_log)
        
        msg = "Failed to convert. "
        if "ModelWrapper" in last_error_log:
            msg += "Detected Layout engine issue."
        elif any(x in last_error_log for x in ["ProtocolError", "ChunkedEncodingError", "IncompleteRead"]):
            msg += "Model download failed due to network instability. Please run 'mineru-models-download' manually in the environment."
        else:
            msg += "Check logs for detailed traceback."
        
        publish_event(job_id, {"type": "progress", "stage": "error", "percent": 100, "ok": False, "error": msg})
        append_history({"type": "convert.done", "user": user, "job_id": job_id, "ok": False, "error": msg})
        return

    # Save the successful log
    with open(job_dir / "conversion.log", "w", encoding="utf-8") as f:
        f.write(full_log)

    publish_event(job_id, {"type": "progress", "stage": "collect_output", "percent": 90, "ok": None})
    md_path = search_md(job_dir, pdf_path.stem) or search_default_md(pdf_path.stem)
    if md_path:
        target = job_dir / f"{pdf_path.stem}.md"
        if md_path.resolve() != target.resolve():
            ensure_dir(target.parent)
            shutil.copy2(md_path, target)
        total_ms = int((time.time() - job_start) * 1000)
        s = get_settings()
        device = getattr(s, "device", "cpu")
        publish_event(job_id, {"type": "progress", "stage": "done", "percent": 100, "ok": True, "md_path": str(target), "elapsed_ms": total_ms, "device": device})
        append_history({"type": "convert.done", "user": user, "job_id": job_id, "ok": True, "md": str(target), "device": device})

def perform_cleanup() -> None:
    s = get_settings()
    now = time.time()
    ttl_seconds = s.job_ttl_hours * 3600
    if not s.output_root.exists(): return
    for item in s.output_root.iterdir():
        if item.is_dir() and item.name != "logs":
            try:
                if (now - item.stat().st_mtime) > ttl_seconds:
                    shutil.rmtree(item)
                    with _JOBS_LOCK:
                        if item.name in _JOBS: del _JOBS[item.name]
            except Exception: pass
