from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    reports: Mapped[list["Report"]] = relationship(back_populates="company")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    user: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True)
    report_year: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    report_type: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    auto_dir: Mapped[str] = mapped_column(Text)
    markdown_path: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_file_mtime_ms: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    source_file_sha256: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="reports")
    facts: Mapped[list["Fact"]] = relationship(back_populates="report")
    qa_question_links: Mapped[list["QaQuestionReport"]] = relationship(back_populates="report")


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id"), index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value_text: Mapped[str] = mapped_column(Text)
    value_num: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_heading: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True)

    report: Mapped["Report"] = relationship(back_populates="facts")


class QaQuestion(Base):
    __tablename__ = "qa_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String(128), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    strict: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    answers: Mapped[list["QaAnswer"]] = relationship(back_populates="question")
    report_links: Mapped[list["QaQuestionReport"]] = relationship(back_populates="question")


class QaAnswer(Base):
    __tablename__ = "qa_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("qa_questions.id"), index=True)
    answer_text: Mapped[str] = mapped_column(Text)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    question: Mapped["QaQuestion"] = relationship(back_populates="answers")


class QaQuestionReport(Base):
    __tablename__ = "qa_question_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("qa_questions.id"), index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)

    question: Mapped["QaQuestion"] = relationship(back_populates="report_links")
    report: Mapped["Report"] = relationship(back_populates="qa_question_links")
