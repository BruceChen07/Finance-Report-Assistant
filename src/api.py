import hashlib
import json
import os
import queue
import shutil
import threading
import time
import uuid
import zipfile
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
from src.qa.schemas import QaRequest, QaResponse
from src.qa.service import QaConfig, answer_question
from src.db.normalizer import ingest_report_from_job_id
from src.db.query_route import hybrid_search as hybrid_search_db
from src.db.connection import get_session_factory
from src.db.metadata import Company, Report

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
        "static_dist_dir": str(s.static_dist_dir),
    }

def _dir_size_bytes(root: Path) -> int:
    total = 0
    try:
        for p in root.rglob("*"):
            try:
                if p.is_file():
                    total += int(p.stat().st_size)
            except Exception:
                pass
    except Exception:
        pass
    return total


def _latest_file(p: Path) -> Path | None:
    try:
        files = [x for x in p.glob("*") if x.is_file()]
    except Exception:
        return None
    if not files:
        return None
    return sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[0]


@app.get("/api/storage/status")
def storage_status(user: str = Depends(get_current_user)) -> dict[str, Any]:
    from src.db.connection import get_db_path

    try:
        from src.indexing.index_service import default_index_config

        cfg = default_index_config()
        chroma_dir = Path(str(cfg.persist_dir))
        chroma_collection = str(cfg.collection_name)
    except Exception:
        chroma_dir = (s.output_root / "chroma").resolve()
        chroma_collection = "fra_finance_chunks"

    sqlite_path = get_db_path()
    sqlite_size = int(sqlite_path.stat().st_size) if sqlite_path.exists() else 0

    chroma_size = _dir_size_bytes(chroma_dir) if chroma_dir.exists() else 0

    vector_count: int | None = None
    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(chroma_dir))
        col = client.get_or_create_collection(chroma_collection)
        vector_count = int(col.count())
    except Exception:
        vector_count = None

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        reports_count = int(db.query(Report).filter(Report.user == user).count())
        last_indexed_at = (
            db.query(Report.indexed_at)
            .filter(Report.user == user)
            .order_by(Report.indexed_at.desc())
            .first()
        )
        last_indexed_at_iso = last_indexed_at[0].isoformat() if last_indexed_at and last_indexed_at[0] else None
    finally:
        db.close()

    backups_dir = (s.output_root / "backups").resolve()
    latest = _latest_file(backups_dir) if backups_dir.exists() else None
    latest_iso = datetime.fromtimestamp(latest.stat().st_mtime).isoformat() if latest else None

    return {
        "output_root": str(s.output_root),
        "sqlite_path": str(sqlite_path),
        "sqlite_size_bytes": sqlite_size,
        "chroma_dir": str(chroma_dir),
        "chroma_collection": chroma_collection,
        "chroma_size_bytes": int(chroma_size),
        "chroma_vector_count": vector_count,
        "reports_count": reports_count,
        "last_indexed_at": last_indexed_at_iso,
        "latest_backup": str(latest) if latest else None,
        "latest_backup_at": latest_iso,
    }


@app.post("/api/storage/backup")
def storage_backup(user: str = Depends(get_current_user)) -> dict[str, Any]:
    try:
        from src.indexing.index_service import default_index_config

        cfg = default_index_config()
        chroma_dir = Path(str(cfg.persist_dir))
    except Exception:
        chroma_dir = (s.output_root / "chroma").resolve()

    backups_dir = (s.output_root / "backups").resolve()
    ensure_dir(backups_dir)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backups_dir / f"chroma_{ts}.zip"

    if chroma_dir.exists() and chroma_dir.is_dir():
        with zipfile.ZipFile(str(out), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in chroma_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(chroma_dir)
                    zf.write(str(p), arcname=str(rel))

    return {"ok": True, "backup_path": str(out), "chroma_dir": str(chroma_dir)}


@app.get("/api/history")
def history(limit: int = Query(200, ge=1, le=2000), user: str = Depends(get_current_user)) -> dict[str, Any]:
    return {"items": read_history(limit=limit)}

@app.get("/api/files")
def list_files(
    q: str | None = Query(None),
    company_code: str | None = Query(None),
    report_year: int | None = Query(None),
    order_by: str = Query("created_at"),
    limit: int = Query(200, ge=1, le=500),
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        query = (
            db.query(Report, Company)
            .join(Company, Report.company_id == Company.id)
            .filter(Report.user == user)
        )
        if company_code:
            query = query.filter(Company.code == company_code)
        if report_year is not None:
            query = query.filter(Report.report_year == report_year)
        if q:
            query = query.filter(Report.markdown_path.contains(q))

        if order_by == "size_bytes":
            rows = query.all()
            items: list[dict[str, Any]] = []
            for report, company in rows:
                md_path = Path(str(report.markdown_path))
                size_bytes = md_path.stat().st_size if md_path.exists() else 0
                items.append(
                    {
                        "id": report.id,
                        "job_id": report.job_id,
                        "file_name": md_path.name,
                        "file_type": "markdown",
                        "size_bytes": size_bytes,
                        "created_at": report.created_at.isoformat() if report.created_at else None,
                        "indexed_at": report.indexed_at.isoformat() if getattr(report, "indexed_at", None) else None,
                        "company_code": company.code,
                        "company_name": company.name,
                        "report_year": report.report_year,
                        "report_type": report.report_type,
                    }
                )
            items.sort(key=lambda x: int(x.get("size_bytes") or 0), reverse=True)
            return {"items": items[:limit]}

        if order_by == "created_at":
            query = query.order_by(Report.created_at.desc())
        else:
            query = query.order_by(Report.id.desc())

        rows = query.limit(limit).all()
        items: list[dict[str, Any]] = []
        for report, company in rows:
            md_path = Path(str(report.markdown_path))
            size_bytes = md_path.stat().st_size if md_path.exists() else 0
            items.append(
                {
                    "id": report.id,
                    "job_id": report.job_id,
                    "file_name": md_path.name,
                    "file_type": "markdown",
                    "size_bytes": size_bytes,
                    "created_at": report.created_at.isoformat() if report.created_at else None,
                    "indexed_at": report.indexed_at.isoformat() if getattr(report, "indexed_at", None) else None,
                    "company_code": company.code,
                    "company_name": company.name,
                    "report_year": report.report_year,
                    "report_type": report.report_type,
                }
            )
        return {"items": items}
    finally:
        db.close()

@app.get("/api/files/{file_id}")
def file_detail(file_id: int, preview_chars: int = Query(12000, ge=1000, le=50000), user: str = Depends(get_current_user)) -> dict[str, Any]:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        row = (
            db.query(Report, Company)
            .join(Company, Report.company_id == Company.id)
            .filter(Report.id == file_id)
            .filter(Report.user == user)
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="file not found")
        report, company = row
        md_path = Path(str(report.markdown_path))
        preview = ""
        if md_path.exists() and md_path.is_file():
            preview = md_path.read_text(encoding="utf-8", errors="ignore")[:preview_chars]
        size_bytes = md_path.stat().st_size if md_path.exists() else 0
        return {
            "id": report.id,
            "job_id": report.job_id,
            "file_name": md_path.name,
            "file_type": "markdown",
            "size_bytes": size_bytes,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "company_code": company.code,
            "company_name": company.name,
            "report_year": report.report_year,
            "report_type": report.report_type,
            "preview_markdown": preview,
        }
    finally:
        db.close()

@app.post("/api/qa", response_model=QaResponse)
def qa_endpoint(req: QaRequest, user: str = Depends(get_current_user)) -> QaResponse:
    cfg = QaConfig()
    return answer_question(req, cfg, user=user)

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
    file: UploadFile = File(...),
    backend: str | None = Query(None),
    mode: str | None = Query(None),
    download: bool = Query(False),
    company_code: str | None = Query(None),
    company_name: str | None = Query(None),
    report_year: int | None = Query(None),
    report_type: str | None = Query(None),
    source_file_mtime_ms: int | None = Query(None),
    user: str = Depends(get_current_user),
) -> Any:
    filename = Path(file.filename or "upload.pdf").name
    mode_norm = normalize_mineru_mode(mode)
    if mode and not mode_norm:
        raise HTTPException(status_code=400, detail="invalid mode")

    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job_dir = s.output_root / job_id
    ensure_dir(job_dir)
    pdf_path = job_dir / filename

    h = hashlib.sha256()
    size_bytes = 0
    with open(pdf_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            size_bytes += len(chunk)

    sha256 = h.hexdigest()

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        dup = (
            db.query(Report)
            .filter(Report.user == user)
            .filter(Report.source_file_sha256 == sha256)
            .first()
        )
        if not dup:
            q = (
                db.query(Report)
                .filter(Report.user == user)
                .filter(Report.source_file_name == filename)
                .filter(Report.source_file_size_bytes == int(size_bytes))
            )
            if source_file_mtime_ms is not None:
                q = q.filter(Report.source_file_mtime_ms == int(source_file_mtime_ms))
            dup = q.first()
    finally:
        db.close()

    if dup is not None and dup.job_id:
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass

        existing_job_id = str(dup.job_id)
        existing_dir = s.output_root / existing_job_id
        md_path = Path(str(dup.markdown_path)) if getattr(dup, "markdown_path", None) else None
        st = JobState(
            job_id=existing_job_id,
            user=user,
            stage="done",
            percent=100,
            created_at=time.time(),
            updated_at=time.time(),
            ok=True,
            error=None,
            pdf_name=str(getattr(dup, "source_file_name", None) or filename),
            job_dir=existing_dir,
            md_path=md_path if (md_path and md_path.exists()) else None,
            subscribers=[],
        )
        with _JOBS_LOCK:
            _JOBS[existing_job_id] = st

        return {
            "job_id": existing_job_id,
            "events_url": f"/api/jobs/{existing_job_id}/events",
            "result_url": f"/api/jobs/{existing_job_id}/result",
            "dedup": True,
            "existing_file_id": int(getattr(dup, "id")),
        }

    st = JobState(
        job_id=job_id,
        user=user,
        stage="queued",
        percent=0,
        created_at=time.time(),
        updated_at=time.time(),
        ok=None,
        error=None,
        pdf_name=filename,
        job_dir=job_dir,
        md_path=None,
        subscribers=[],
    )
    with _JOBS_LOCK:
        _JOBS[job_id] = st

    append_history(
        {
            "type": "convert.start",
            "user": user,
            "job_id": job_id,
            "pdf": filename,
            "backend": backend,
            "mode": mode_norm,
            "sha256": sha256,
            "size_bytes": int(size_bytes),
            "source_file_mtime_ms": int(source_file_mtime_ms) if source_file_mtime_ms is not None else None,
        }
    )

    threading.Thread(
        target=_convert_job,
        args=(job_id, user, pdf_path, job_dir, backend, mode_norm),
        kwargs={
            "company_code": company_code,
            "company_name": company_name,
            "report_year": report_year,
            "report_type": report_type,
            "source_file_name": filename,
            "source_file_size_bytes": int(size_bytes),
            "source_file_mtime_ms": int(source_file_mtime_ms) if source_file_mtime_ms is not None else None,
            "source_file_sha256": sha256,
        },
        daemon=True,
    ).start()

    return {
        "job_id": job_id,
        "events_url": f"/api/jobs/{job_id}/events",
        "result_url": f"/api/jobs/{job_id}/result",
    }

@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str, download: bool = Query(True), user: str = Depends(get_current_user)) -> Any:
    job_dir = s.output_root / job_id
    st = get_job(job_id)
    if st and st.user != user: raise HTTPException(status_code=403)
    md_files = list(job_dir.rglob("auto/*.md"))
    if not md_files:
        md_files = list(job_dir.rglob("*.md"))
    if not md_files: raise HTTPException(status_code=404)
    md_path = sorted(md_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    if download: return FileResponse(str(md_path), media_type="text/markdown", filename=md_path.name)
    return {"job_id": job_id, "status": "done", "markdown": md_path.read_text(encoding="utf-8", errors="ignore")}

@app.post("/api/db/ingest/{job_id}")
def ingest_report(job_id: str, body: dict[str, Any] = Body(...), user: str = Depends(get_current_user)) -> dict[str, Any]:
    company_code = str(body.get("company_code") or "").strip()
    if not company_code:
        raise HTTPException(status_code=400, detail="company_code is required")
    company_name = body.get("company_name")
    report_year = body.get("report_year")
    report_type = body.get("report_type")
    try:
        ingest_report_from_job_id(
            job_id,
            user=user,
            company_code=company_code,
            company_name=company_name,
            report_year=int(report_year) if report_year is not None else None,
            report_type=report_type,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job output not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ingest failed: {e}")
    return {"ok": True, "job_id": job_id}

@app.post("/api/db/hybrid-search")
def hybrid_search_endpoint(body: dict[str, Any] = Body(...), user: str = Depends(get_current_user)) -> dict[str, Any]:
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    company_code = body.get("company_code") or body.get("company_id")
    report_year = body.get("report_year")
    report_type = body.get("report_type")
    results = hybrid_search_db(
        question=question,
        user=user,
        company_code=company_code,
        report_year=int(report_year) if report_year is not None else None,
        report_type=report_type,
    )
    return results

@app.get("/api/jobs/{job_id}/auto-bundle")
def job_auto_bundle(job_id: str, user: str = Depends(get_current_user)) -> Any:
    from src.finance_parsing.mineru_auto_reader import find_auto_output

    job_dir = s.output_root / job_id
    st = get_job(job_id)
    if st and st.user != user:
        raise HTTPException(status_code=403)

    try:
        auto_out = find_auto_output(job_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="mineru output not found")

    auto_dir = auto_out.auto_dir

    zip_path = job_dir / "auto_bundle.zip"
    tmp_path = job_dir / f".auto_bundle_{uuid.uuid4().hex}.zip"

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in auto_dir.rglob("*"):
            if p.is_file():
                arc = str(p.relative_to(auto_dir)).replace("\\", "/")
                zf.write(str(p), arcname=arc)

    try:
        if zip_path.exists():
            zip_path.unlink()
        tmp_path.replace(zip_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

    base_name = auto_dir.name or job_id
    return FileResponse(str(zip_path), media_type="application/zip", filename=f"{base_name}.zip")

@app.get("/api/jobs/{job_id}/pdf")
def job_pdf(job_id: str, user: str = Depends(get_current_user)) -> Any:
    job_dir = s.output_root / job_id
    st = get_job(job_id)
    if st and st.user != user: raise HTTPException(status_code=403)
    pdfs = sorted(list(job_dir.glob("*.pdf")), key=lambda p: p.stat().st_mtime)
    if not pdfs: raise HTTPException(status_code=404)
    return FileResponse(str(pdfs[0]), media_type="application/pdf", filename=pdfs[0].name)


@app.get("/api/jobs/{job_id}/asset")
def job_asset(
    job_id: str,
    path: str = Query(..., min_length=1),
    user: str = Depends(get_current_user),
) -> Any:
    from src.finance_parsing.mineru_auto_reader import find_auto_output

    job_dir = s.output_root / job_id
    st = get_job(job_id)
    if st and st.user != user:
        raise HTTPException(status_code=403)

    if not st:
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            r = (
                db.query(Report)
                .filter(Report.user == user)
                .filter(Report.job_id == str(job_id))
                .first()
            )
            if r is None:
                raise HTTPException(status_code=404)
        finally:
            db.close()

    try:
        auto_out = find_auto_output(job_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="mineru output not found")

    base_dir = Path(str(auto_out.auto_dir)).resolve()
    images_dir = (
        Path(str(auto_out.images_dir)).resolve()
        if getattr(auto_out, "images_dir", None)
        else None
    )

    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=400, detail="path is required")

    cand: Path | None = None
    p = Path(raw)

    if p.is_absolute():
        try:
            rp = p.resolve()
            if rp.is_relative_to(base_dir):
                cand = rp
            elif images_dir and rp.is_relative_to(images_dir):
                cand = rp
        except Exception:
            cand = None
    else:
        try:
            rp = (base_dir / raw).resolve()
            if rp.is_relative_to(base_dir):
                cand = rp
        except Exception:
            cand = None

        if (cand is None) or (not cand.exists()):
            if images_dir:
                try:
                    rp2 = (images_dir / raw).resolve()
                    if rp2.is_relative_to(images_dir):
                        cand = rp2
                except Exception:
                    pass

    if cand is None or not cand.exists() or not cand.is_file():
        raise HTTPException(status_code=404)

    return FileResponse(str(cand), filename=cand.name)


@app.get("/", response_class=HTMLResponse)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_handler(full_path: str = "") -> Any:
    if full_path.startswith(("api/", "docs", "openapi")): raise HTTPException(status_code=404)
    index = s.static_dist_dir / "index.html"
    candidate = s.static_dist_dir / full_path
    if candidate.exists() and candidate.is_file(): return FileResponse(str(candidate))
    if index.exists(): return HTMLResponse(index.read_text(encoding="utf-8", errors="ignore"))
    return HTMLResponse("<html><body>Frontend not ready.</body></html>")
