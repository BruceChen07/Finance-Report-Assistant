from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.finance_parsing.mineru_auto_reader import find_auto_output
from src.indexing.chunking import chunk_markdown
from src.db.metadata import Company, Report, Fact
from src.db.connection import get_session_factory
from src.config import get_settings


def _parse_number(text: str) -> Optional[float]:
    cleaned = text.replace(",", "")
    m = re.search(r"(-?\d[\d.]*)(?!\d)", cleaned)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def upsert_company(db: Session, code: str, name: str | None = None) -> Company:
    obj = db.query(Company).filter(Company.code == code).first()
    if obj:
        if name and not obj.name:
            obj.name = name
        return obj
    obj = Company(code=code, name=name or code)
    db.add(obj)
    db.flush()
    return obj


def ingest_report_from_job(
    job_id: str,
    job_dir: Path,
    db: Session,
    *,
    user: str,
    company_code: str,
    company_name: str | None = None,
    report_year: int | None = None,
    report_type: str | None = None,
    pdf_path: str | None = None,
    source_file_name: str | None = None,
    source_file_size_bytes: int | None = None,
    source_file_mtime_ms: int | None = None,
    source_file_sha256: str | None = None,
) -> Report:
    auto_out = find_auto_output(job_dir)
    company = upsert_company(db, company_code, company_name)

    existing = db.query(Report).filter(Report.job_id == job_id).first()
    if existing:
        db.query(Fact).filter(Fact.report_id == existing.id).delete()
        report = existing
        report.user = user
        report.company_id = company.id
        report.report_year = report_year
        report.report_type = report_type
        report.auto_dir = str(auto_out.auto_dir)
        report.markdown_path = str(auto_out.markdown_path)
        report.pdf_path = pdf_path
        report.source_file_name = source_file_name
        report.source_file_size_bytes = source_file_size_bytes
        report.source_file_mtime_ms = source_file_mtime_ms
        report.source_file_sha256 = source_file_sha256
    else:
        report = Report(
            user=user,
            company_id=company.id,
            report_year=report_year,
            report_type=report_type,
            job_id=job_id,
            auto_dir=str(auto_out.auto_dir),
            markdown_path=str(auto_out.markdown_path),
            pdf_path=pdf_path,
            source_file_name=source_file_name,
            source_file_size_bytes=source_file_size_bytes,
            source_file_mtime_ms=source_file_mtime_ms,
            source_file_sha256=source_file_sha256,
        )
        db.add(report)
        db.flush()

    md_text = auto_out.markdown_path.read_text(
        encoding="utf-8", errors="ignore")
    chunks = chunk_markdown(md_text, max_chars=800,
                            overlap_chars=0, base_metadata={})

    for c in chunks:
        lines = [ln.strip() for ln in c.text.splitlines() if ln.strip()]
        if not lines:
            continue
        heading = None
        hs = c.metadata.get("headings")
        if isinstance(hs, list) and hs:
            heading = " / ".join(str(x) for x in hs)
        for ln in lines:
            if ":" in ln:
                parts = ln.split(":", 1)
            elif "：" in ln:
                parts = ln.split("：", 1)
            else:
                continue
            key = parts[0].strip()
            value_text = parts[1].strip()
            if not key or not value_text:
                continue
            value_num = _parse_number(value_text)
            fact = Fact(
                report_id=report.id,
                key=key,
                value_text=value_text,
                value_num=value_num,
                unit=None,
                source_heading=heading,
            )
            db.add(fact)

    return report


def ingest_report_from_job_id(
    job_id: str,
    *,
    user: str,
    company_code: str | None = None,
    company_name: str | None = None,
    report_year: int | None = None,
    report_type: str | None = None,
    pdf_path: str | None = None,
    source_file_name: str | None = None,
    source_file_size_bytes: int | None = None,
    source_file_mtime_ms: int | None = None,
    source_file_sha256: str | None = None,
) -> Report:
    s = get_settings()
    job_dir = s.output_root / job_id
    SessionLocal = get_session_factory()
    db = SessionLocal()
    company_code_norm = (company_code or "").strip() or "UNKNOWN"
    try:
        report = ingest_report_from_job(
            job_id=job_id,
            job_dir=job_dir,
            db=db,
            user=user,
            company_code=company_code_norm,
            company_name=company_name,
            report_year=report_year,
            report_type=report_type,
            pdf_path=pdf_path,
            source_file_name=source_file_name,
            source_file_size_bytes=source_file_size_bytes,
            source_file_mtime_ms=source_file_mtime_ms,
            source_file_sha256=source_file_sha256,
        )
        db.commit()
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()