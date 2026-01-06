from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.indexing.index_service import query_index
from src.db.metadata import Company, Fact, Report
from src.db.connection import get_session_factory


def query_sql_facts(
    question: str,
    *,
    user: str | None = None,
    company_code: str | None = None,
    report_year: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    SessionLocal = get_session_factory()
    db: Session = SessionLocal()
    try:
        q = (
            db.query(Fact, Report, Company)
            .join(Report, Fact.report_id == Report.id)
            .join(Company, Report.company_id == Company.id)
        )
        if user:
            q = q.filter(Report.user == user)
        if company_code:
            q = q.filter(Company.code == company_code)
        if report_year is not None:
            q = q.filter(Report.report_year == report_year)

        for term in ["收入", "营收", "利润", "净利润"]:
            if term in question:
                q = q.filter(Fact.key.contains(term))
                break

        q = q.order_by(Fact.id.desc()).limit(limit)
        rows = q.all()
        out: list[dict[str, Any]] = []
        for fact, report, company in rows:
            out.append(
                {
                    "key": fact.key,
                    "value_text": fact.value_text,
                    "value_num": fact.value_num,
                    "company_code": company.code,
                    "company_name": company.name,
                    "report_year": report.report_year,
                    "report_type": report.report_type,
                    "job_id": report.job_id,
                    "source_heading": fact.source_heading,
                }
            )
        return out
    finally:
        db.close()


def hybrid_search(
    question: str,
    *,
    user: str | None = None,
    company_code: str | None = None,
    report_year: int | None = None,
    report_type: str | None = None,
    top_k_vector: int = 8,
    top_k_sql: int = 20,
) -> dict[str, Any]:
    sql_results = query_sql_facts(
        question,
        user=user,
        company_code=company_code,
        report_year=report_year,
        limit=top_k_sql,
    )
    vector_results = query_index(
        question=question,
        top_k=top_k_vector,
        company_id=company_code,
        report_year=report_year,
        report_type=report_type,
    )
    return {"sql": sql_results, "vector": vector_results}
