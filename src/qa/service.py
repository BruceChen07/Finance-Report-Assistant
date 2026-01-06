from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.qa.schemas import QaRequest, QaResponse, QaSource


@dataclass(frozen=True)
class QaConfig:
    llm_provider: str = field(default_factory=lambda: os.getenv(
        "FRA_LLM_PROVIDER", "qwen").strip().lower())
    model: str = field(default_factory=lambda: os.getenv(
        "FRA_LLM_MODEL", "qwen3-max-2025-09-23").strip())
    temperature: float = field(default_factory=lambda: float(
        os.getenv("FRA_LLM_TEMPERATURE", "0.0")))
    max_output_tokens: int = field(default_factory=lambda: int(
        os.getenv("FRA_LLM_MAX_OUTPUT_TOKENS", "800")))
    base_url: str | None = field(default_factory=lambda: (
        os.getenv("FRA_LLM_BASE_URL") or None))


def _pick_title(meta: dict[str, Any]) -> str | None:
    hs = meta.get("headings")
    if isinstance(hs, list) and hs:
        tail = [str(x) for x in hs[-3:] if isinstance(x,
                                                      (str, int, float)) or x is not None]
        t = " / ".join([x for x in tail if str(x).strip()])
        return t or None
    return None


def _resolve_api_key(provider: str) -> str:
    provider = (provider or "").strip().lower()

    if provider in {"qwen", "dashscope", "aliyun"}:
        api_key = (
            os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("FRA_DASHSCOPE_API_KEY")
            or os.getenv("FRA_LLM_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                "Missing API key. Set DASHSCOPE_API_KEY (recommended) or FRA_LLM_API_KEY.")
        return api_key

    if provider in {"openai"}:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv(
            "FRA_OPENAI_API_KEY") or os.getenv("FRA_LLM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing API key. Set OPENAI_API_KEY (recommended) or FRA_LLM_API_KEY.")
        return api_key

    api_key = os.getenv("FRA_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Missing API key. Set FRA_LLM_API_KEY.")
    return api_key


def _resolve_base_url(provider: str, base_url: str | None) -> str | None:
    if base_url:
        return base_url.strip().strip("`")

    provider = (provider or "").strip().lower()
    if provider in {"qwen", "dashscope", "aliyun"}:
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"

    return None


def _answer_openai_compatible(
    *,
    provider: str,
    base_url: str | None,
    question: str,
    context_blocks: list[str],
    model: str,
    temperature: float,
    max_output_tokens: int,
    strict: bool,
) -> str:
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("Missing dependency: openai") from e

    api_key = _resolve_api_key(provider)
    client = OpenAI(api_key=api_key,
                    base_url=_resolve_base_url(provider, base_url))

    rules = [
        "You are a financial report assistant.",
        "Use only the provided context.",
        "If the context is insufficient, answer exactly: There isn't enough data to answer this",
        "When you use information from a source block, cite it as [S1], [S2], ...",
        "If strict=true, be concise and avoid speculation.",
    ]
    system = "\n".join(rules)

    context = "\n\n".join(context_blocks).strip()
    user = f"strict={str(strict).lower()}\n\nQuestion:\n{question}\n\nContext:\n{context}"

    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_output_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    msg = resp.choices[0].message
    text = (msg.content or "").strip()
    return text or "There isn't enough data to answer this"


def answer_question(req: QaRequest, cfg: QaConfig, *, user: str) -> QaResponse:
    from src.indexing.index_service import query_index
    from src.db.connection import get_session_factory
    from src.db.metadata import Company, QaAnswer, QaQuestion, QaQuestionReport, Report

    selected_report_ids = list(req.file_ids or [])
    job_ids: list[str] | None = None
    job_id_to_file: dict[str, dict[str, Any]] = {}

    if selected_report_ids:
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            rows = (
                db.query(Report, Company)
                .join(Company, Report.company_id == Company.id)
                .filter(Report.user == user)
                .filter(Report.id.in_(selected_report_ids))
                .all()
            )
            job_ids = [r.job_id for r, _ in rows]
            for r, c in rows:
                job_id_to_file[str(r.job_id)] = {
                    "file_id": int(r.id),
                    "file_name": Path(str(r.markdown_path)).name,
                    "company_code": c.code,
                    "company_name": c.name,
                    "report_year": r.report_year,
                    "report_type": r.report_type,
                }
        finally:
            db.close()

    results = query_index(
        question=req.question,
        top_k=req.top_k,
        company_id=req.company_id,
        report_year=req.report_year,
        report_type=req.report_type,
        job_ids=job_ids,
    )

    if results and not job_id_to_file:
        found_job_ids = sorted(
            {str((r.get("metadata") or {}).get("job_id") or "") for r in results})
        found_job_ids = [x for x in found_job_ids if x]
        if found_job_ids:
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                rows = (
                    db.query(Report, Company)
                    .join(Company, Report.company_id == Company.id)
                    .filter(Report.user == user)
                    .filter(Report.job_id.in_(found_job_ids))
                    .all()
                )
                for r, c in rows:
                    job_id_to_file[str(r.job_id)] = {
                        "file_id": int(r.id),
                        "file_name": Path(str(r.markdown_path)).name,
                        "company_code": c.code,
                        "company_name": c.name,
                        "report_year": r.report_year,
                        "report_type": r.report_type,
                    }
            finally:
                db.close()

    sources: list[QaSource] = []
    context_blocks: list[str] = []

    for i, r in enumerate(results, 1):
        meta = dict((r.get("metadata") or {}))
        snippet = str(r.get("snippet") or "").strip()
        heading_title = _pick_title(meta)

        job_id = str(meta.get("job_id") or "")
        fi = job_id_to_file.get(job_id)
        file_name = fi.get("file_name") if isinstance(fi, dict) else None
        file_id = fi.get("file_id") if isinstance(fi, dict) else None

        title_parts = [x for x in [file_name, heading_title] if x]
        title = " / ".join(title_parts) if title_parts else heading_title

        if isinstance(fi, dict):
            meta = {**meta, **fi}
        if file_id is not None:
            meta["file_id"] = file_id

        sources.append(
            QaSource(
                kind="chunk",
                title=title,
                snippet=snippet,
                metadata=meta,
            )
        )

        header = f"[S{i}]" + (f" {title}" if title else "")
        context_blocks.append(f"{header}\n{snippet}")

    if not sources:
        return QaResponse(answer="There isn't enough data to answer this", sources=[])

    provider = (cfg.llm_provider or "qwen").strip().lower()
    temperature = 0.0 if req.strict else float(cfg.temperature)

    answer = _answer_openai_compatible(
        provider=provider,
        base_url=getattr(cfg, "base_url", None),
        question=req.question,
        context_blocks=context_blocks,
        model=cfg.model,
        temperature=temperature,
        max_output_tokens=cfg.max_output_tokens,
        strict=req.strict,
    )

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        qobj = QaQuestion(user=user, question_text=req.question,
                          strict=1 if req.strict else 0)
        db.add(qobj)
        db.flush()
        aobj = QaAnswer(
            question_id=int(qobj.id),
            answer_text=answer,
            llm_provider=provider,
            model=str(cfg.model),
        )
        db.add(aobj)
        for fid in selected_report_ids:
            db.add(QaQuestionReport(question_id=int(qobj.id), report_id=int(fid)))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    return QaResponse(answer=answer, sources=sources)
