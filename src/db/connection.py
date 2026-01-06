from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings, ensure_dir


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_db_path() -> Path:
    s = get_settings()
    env_path = os.getenv("FRA_SQLITE_PATH")
    if env_path:
        p = Path(env_path)
    else:
        p = s.output_root / "fra.sqlite3"
    ensure_dir(p.parent)
    return p


def get_engine():
    global _engine
    if _engine is None:
        db_path = get_db_path()
        url = f"sqlite:///{db_path}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _SessionLocal


def init_db() -> None:
    from src.db.metadata import Base

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    db_path = get_db_path()
    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(reports)")
            cols = [str(r[1]) for r in cur.fetchall()]
            if "user" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN user VARCHAR(128)")
            if "pdf_path" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN pdf_path TEXT")
            if "source_file_name" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN source_file_name VARCHAR(255)")
            if "source_file_size_bytes" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN source_file_size_bytes INTEGER")
            if "source_file_size_bytes" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN source_file_size_bytes INTEGER")
            if "source_file_mtime_ms" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN source_file_mtime_ms INTEGER")
            if "source_file_sha256" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN source_file_sha256 VARCHAR(64)")
            if "indexed_at" not in cols:
                cur.execute("ALTER TABLE reports ADD COLUMN indexed_at DATETIME")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_source_file_sha256 ON reports(source_file_sha256)")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
