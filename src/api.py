import json
import os
import queue
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List
from fastapi import FastAPI, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from src.config import get_settings, ensure_dir
from src.auth import get_current_user, jwt_encode
from src.history import read_history, append_history
from src.converter import resolve_cli, MINERU_MODES, normalize_mineru_mode
from src.jobs import JobState, _JOBS, _JOBS_LOCK, get_job, _convert_job

app = FastAPI(title="Finance Report Assistant", version="0.1.0")
s = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=s.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if s.static_dist_dir.exists():
    assets_path = s.static_dist_dir / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path), html=False), name="assets")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/api/auth/login")
def login(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    username = str(body.get("username", ""))
    password = str(body.get("password", ""))
    if not (username == s.username and password == s.password):
        append_history({"type": "auth.login", "ok": False, "user": username})
        raise HTTPException(status_code=401, detail="bad credentials")
    exp = int(time.time()) + int(s.jwt_ttl_seconds)
    token = jwt_encode({"sub": username, "exp": exp}, s.jwt_secret)
    append_history({"type": "auth.login", "ok": True, "user": username})
    return {"access_token": token, "token_type": "bearer", "expires_in": s.jwt_ttl_seconds}

@app.get("/api/auth/me")
def me(user: str = Depends(get_current_user)) -> dict[str, str]:
    return {"username": user}

@app.get("/api/status")
def status(user: str = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "mineru": os.path.exists(resolve_cli("mineru")),
        "magic_pdf": os.path.exists(resolve_cli("magic-pdf")),
        "mineru_modes": list(MINERU_MODES),
        "output_root": str(s.output_root),
    }

@app.get("/api/history")
def history(limit: int = Query(200, ge=1, le=2000), user: str = Depends(get_current_user)) -> dict[str, Any]:
    return {"items": read_history(limit=limit)}

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: str = Depends(get_current_user)) -> dict[str, Any]:
    st = get_job(job_id)
    if not st or st.user != user: raise HTTPException(status_code=404 if not st else 403)
    return {
        "job_id": st.job_id, "stage": st.stage, "percent": st.percent,
        "ok": st.ok, "error": st.error, "pdf_name": st.pdf_name,
        "md_path": str(st.md_path) if st.md_path else None,
        "created_at": st.created_at, "updated_at": st.updated_at,
    }

@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, user: str = Depends(get_current_user)) -> Any:
    st = get_job(job_id)
    if not st or st.user != user: raise HTTPException(status_code=404 if not st else 403)
    q: queue.Queue[str] = queue.Queue(maxsize=1000)
    with _JOBS_LOCK: st.subscribers.append(q)
    def gen():
        try:
            yield f"event: message\ndata: {json.dumps({'type':'snapshot','job_id':st.job_id,'stage':st.stage,'percent':st.percent,'ok':st.ok,'pdf_name':st.pdf_name}, ensure_ascii=False)}\n\n"
            while True:
                try: yield f"event: message\ndata: {q.get(timeout=15)}\n\n"
                except queue.Empty: yield ": keepalive\n\n"
        finally:
            with _JOBS_LOCK:
                if st in _JOBS.values() and q in st.subscribers: st.subscribers.remove(q)
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/api/convert")
async def convert_endpoint(
    file: UploadFile = File(...), backend: str | None = Query(None),
    mode: str | None = Query(None), download: bool = Query(False),
    user: str = Depends(get_current_user),
) -> Any:
    filename = Path(file.filename or "upload.pdf").name
    mode_norm = normalize_mineru_mode(mode)
    if mode and not mode_norm: raise HTTPException(status_code=400, detail="invalid mode")
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job_dir = s.output_root / job_id
    ensure_dir(job_dir)
    pdf_path = job_dir / filename
    with open(pdf_path, "wb") as f: shutil.copyfileobj(file.file, f)
    st = JobState(job_id=job_id, user=user, stage="queued", percent=0, created_at=time.time(), updated_at=time.time(), ok=None, error=None, pdf_name=filename, job_dir=job_dir, md_path=None, subscribers=[])
    with _JOBS_LOCK: _JOBS[job_id] = st
    append_history({"type": "convert.start", "user": user, "job_id": job_id, "pdf": filename, "backend": backend, "mode": mode_norm})
    threading.Thread(target=_convert_job, args=(job_id, user, pdf_path, job_dir, backend, mode_norm), daemon=True).start()
    return {"job_id": job_id, "events_url": f"/api/jobs/{job_id}/events", "result_url": f"/api/jobs/{job_id}/result"}

@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str, download: bool = Query(True), user: str = Depends(get_current_user)) -> Any:
    job_dir = s.output_root / job_id
    st = get_job(job_id)
    if st and st.user != user: raise HTTPException(status_code=403)
    md_files = list(job_dir.rglob("*.md"))
    if not md_files: raise HTTPException(status_code=404)
    md_path = sorted(md_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    if download: return FileResponse(str(md_path), media_type="text/markdown", filename=md_path.name)
    return {"job_id": job_id, "status": "done", "markdown": md_path.read_text(encoding="utf-8", errors="ignore")}

@app.get("/api/jobs/{job_id}/pdf")
def job_pdf(job_id: str, user: str = Depends(get_current_user)) -> Any:
    job_dir = s.output_root / job_id
    st = get_job(job_id)
    if st and st.user != user: raise HTTPException(status_code=403)
    pdfs = sorted(list(job_dir.glob("*.pdf")), key=lambda p: p.stat().st_mtime)
    if not pdfs: raise HTTPException(status_code=404)
    return FileResponse(str(pdfs[0]), media_type="application/pdf", filename=pdfs[0].name)

@app.get("/", response_class=HTMLResponse)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_handler(full_path: str = "") -> Any:
    if full_path.startswith(("api/", "docs", "openapi")): raise HTTPException(status_code=404)
    index = s.static_dist_dir / "index.html"
    candidate = s.static_dist_dir / full_path
    if candidate.exists() and candidate.is_file(): return FileResponse(str(candidate))
    if index.exists(): return HTMLResponse(index.read_text(encoding="utf-8", errors="ignore"))
    return HTMLResponse("<html><body>Frontend not ready.</body></html>")
