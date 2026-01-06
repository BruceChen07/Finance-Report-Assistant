from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


class QaRequest(BaseModel):
    question: str = Field(min_length=1)
    company_id: str | None = None
    report_year: int | None = None
    report_type: str | None = None
    strict: bool = True
    top_k: int = 8
    file_ids: list[int] | None = None
    report_ids: list[int] | None = None


class QaSource(BaseModel):
    kind: Literal["chunk", "sql_row"]
    title: str | None = None
    snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QaResponse(BaseModel):
    answer: str
    sources: list[QaSource] = Field(default_factory=list)
