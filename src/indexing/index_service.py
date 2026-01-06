from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import ensure_dir, get_settings
from src.finance_parsing.mineru_auto_reader import find_auto_output
from src.indexing.chunking import Chunk, chunks_from_markdown_file
from src.indexing.embedding_provider import configure_embedding as _configure_embedding
from src.indexing.mineru_blocks import (
    load_content_list_blocks as _load_content_list_blocks,
    enrich_chunks_with_blocks as _enrich_chunks_with_blocks,
    chunks_to_documents as _chunks_to_documents,
    table_documents_from_blocks as _table_documents_from_blocks,
    image_documents_from_blocks as _image_documents_from_blocks,
)


@dataclass(frozen=True)
class IndexConfig:
    persist_dir: Path
    collection_name: str = "fra_finance_chunks"
    max_chars: int = 4000
    overlap_chars: int = 300


def default_index_config() -> IndexConfig:
    s = get_settings()
    persist_dir = Path(
        os.getenv("FRA_CHROMA_DIR", str((s.output_root / "chroma").resolve()))
    )
    ensure_dir(persist_dir)
    return IndexConfig(persist_dir=persist_dir)


def _import_llamaindex() -> Any:
    try:
        from llama_index.core import (  # type: ignore
            Document,
            Settings,
            StorageContext,
            VectorStoreIndex,
        )
        from llama_index.core.vector_stores import (
            MetadataFilters,
            MetadataFilter,
            FilterOperator,
        )
        from llama_index.vector_stores.chroma import ChromaVectorStore  # type: ignore

        return {
            "Document": Document,
            "Settings": Settings,
            "StorageContext": StorageContext,
            "VectorStoreIndex": VectorStoreIndex,
            "ChromaVectorStore": ChromaVectorStore,
            "MetadataFilters": MetadataFilters,
            "MetadataFilter": MetadataFilter,
            "FilterOperator": FilterOperator,
        }
    except Exception as e:
        raise RuntimeError(
            "LlamaIndex is not installed or incompatible. "
            "Please install llama-index and llama-index-vector-stores-chroma."
        ) from e


def _import_chroma() -> Any:
    try:
        import chromadb  # type: ignore

        return chromadb
    except Exception as e:
        raise RuntimeError(
            "ChromaDB is not installed. Please install chromadb."
        ) from e


def build_or_update_index_for_job(
    job_id: str,
    job_dir: Path,
    *,
    company_id: str | None = None,
    report_year: int | None = None,
    report_type: str | None = None,
    report_id: int | None = None,
    user: str | None = None,
    pdf_path: str | None = None,
    source_file_name: str | None = None,
    source_file_size_bytes: int | None = None,
    source_file_mtime_ms: int | None = None,
    source_file_sha256: str | None = None,
    cfg: IndexConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or default_index_config()

    li = _import_llamaindex()
    chromadb = _import_chroma()

    Document = li["Document"]
    Settings = li["Settings"]
    StorageContext = li["StorageContext"]
    VectorStoreIndex = li["VectorStoreIndex"]
    ChromaVectorStore = li["ChromaVectorStore"]

    _configure_embedding(Settings)

    try:
        Settings.chunk_size = int(
            os.getenv("FRA_LLAMA_CHUNK_SIZE", "4096") or 4096
        )
        Settings.chunk_overlap = int(
            os.getenv("FRA_LLAMA_CHUNK_OVERLAP", "0") or 0
        )
    except Exception:
        pass

    auto_out = find_auto_output(job_dir)

    base_meta: dict[str, Any] = {
        "job_id": job_id,
        "user": user,
        "company_id": company_id,
        "report_year": report_year,
        "report_type": report_type,
        "report_id": report_id,
        "source_kind": "mineru_auto_md",
        "auto_dir": str(auto_out.auto_dir),
        "markdown_path": str(auto_out.markdown_path),
        "pdf_path": pdf_path,
        "source_file_name": source_file_name,
        "source_file_size_bytes": source_file_size_bytes,
        "source_file_mtime_ms": source_file_mtime_ms,
        "source_file_sha256": source_file_sha256,
    }

    chunks: list[Chunk] = chunks_from_markdown_file(
        auto_out.markdown_path,
        max_chars=cfg.max_chars,
        overlap_chars=cfg.overlap_chars,
        base_metadata=base_meta,
    )

    blocks = _load_content_list_blocks(auto_out)
    if blocks:
        _enrich_chunks_with_blocks(chunks, blocks)

    docs = _chunks_to_documents(chunks, Document)
    table_docs = (
        _table_documents_from_blocks(
            blocks, base_meta, Document) if blocks else []
    )
    image_docs = (
        _image_documents_from_blocks(
            blocks, base_meta, Document) if blocks else []
    )

    docs.extend(table_docs)
    docs.extend(image_docs)

    client = chromadb.PersistentClient(path=str(cfg.persist_dir))
    collection = client.get_or_create_collection(cfg.collection_name)

    try:
        collection.delete(where={"job_id": str(job_id)})
    except Exception:
        pass

    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    _ = VectorStoreIndex.from_documents(docs, storage_context=storage_context)

    persist = getattr(client, "persist", None)
    if callable(persist):
        persist()

    return {
        "ok": True,
        "job_id": job_id,
        "collection": cfg.collection_name,
        "persist_dir": str(cfg.persist_dir),
        "chunks": len(chunks),
        "table_docs": len(table_docs),
        "image_docs": len(image_docs),
        "markdown_path": str(auto_out.markdown_path),
        "content_list_json": str(
            getattr(auto_out, "content_list_json", "") or ""
        )
        or None,
        "model_json": str(getattr(auto_out, "model_json", "") or "") or None,
    }


def query_index(
    question: str,
    *,
    top_k: int = 8,
    company_id: str | None = None,
    report_year: int | None = None,
    report_type: str | None = None,
    job_ids: list[str] | None = None,
    cfg: IndexConfig | None = None,
) -> list[dict[str, Any]]:
    cfg = cfg or default_index_config()

    li = _import_llamaindex()
    chromadb = _import_chroma()

    Settings = li["Settings"]
    StorageContext = li["StorageContext"]
    VectorStoreIndex = li["VectorStoreIndex"]
    ChromaVectorStore = li["ChromaVectorStore"]
    MetadataFilters = li["MetadataFilters"]
    MetadataFilter = li["MetadataFilter"]
    FilterOperator = li["FilterOperator"]

    _configure_embedding(Settings)

    client = chromadb.PersistentClient(path=str(cfg.persist_dir))
    collection = client.get_or_create_collection(cfg.collection_name)

    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store, storage_context=storage_context
    )

    filters_list: list[Any] = []
    if company_id is not None:
        filters_list.append(
            MetadataFilter(
                key="company_id", value=company_id, operator=FilterOperator.EQ
            )
        )
    if report_year is not None:
        filters_list.append(
            MetadataFilter(
                key="report_year", value=report_year, operator=FilterOperator.EQ
            )
        )
    if report_type is not None:
        filters_list.append(
            MetadataFilter(
                key="report_type", value=report_type, operator=FilterOperator.EQ
            )
        )
    if job_ids:
        ids = list(set(str(x) for x in job_ids if x))
        if ids:
            filters_list.append(
                MetadataFilter(key="job_id", value=ids, operator=FilterOperator.IN)
            )

    metadata_filters = (
        MetadataFilters(filters=filters_list) if filters_list else None
    )

    retriever = index.as_retriever(
        similarity_top_k=top_k, filters=metadata_filters
    )

    nodes = retriever.retrieve(question)
    results: list[dict[str, Any]] = []

    for n in nodes:
        meta = dict(getattr(n.node, "metadata", {}) or {})
        text_fn = getattr(n.node, "get_content", None)
        snippet = (
            n.node.get_content()
            if callable(text_fn)
            else str(getattr(n.node, "text", ""))
        )

        results.append(
            {
                "score": float(getattr(n, "score", 0.0) or 0.0),
                "snippet": snippet[:1200],
                "metadata": meta,
            }
        )

    return results
