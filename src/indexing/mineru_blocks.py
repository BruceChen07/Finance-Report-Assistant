from __future__ import annotations

import bisect
import os
import re
from pathlib import Path
from typing import Any

from src.finance_parsing.mineru_auto_reader import read_json
from src.indexing.chunking import Chunk




_EXCLUDED_METADATA_KEYS = [
    "auto_dir",
    "markdown_path",
    "pdf_path",
    "source_path",
    "headings",
    "img_paths",
    "bbox",
]


def _flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float)) or v is None:
            flat[k] = v
            continue
        if k == "headings" and isinstance(v, list):
            parts = [str(x).strip() for x in v if str(x).strip()]
            flat[k] = " / ".join(parts) if parts else None
            continue
        if isinstance(v, list):
            flat[k] = ", ".join(str(x) for x in v)
        else:
            flat[k] = str(v)
    return flat


def make_document(Document: Any, *, text: str, metadata: dict[str, Any]) -> Any:
    flat = _flatten_metadata(metadata)
    return Document(
        text=text,
        metadata=flat,
        excluded_embed_metadata_keys=list(_EXCLUDED_METADATA_KEYS),
        excluded_llm_metadata_keys=list(_EXCLUDED_METADATA_KEYS),
    )


def chunks_to_documents(chunks: list[Chunk], Document: Any) -> list[Any]:
    docs: list[Any] = []
    for c in chunks:
        docs.append(make_document(
            Document, text=c.text, metadata=dict(c.metadata)))
    return docs


def _norm_text(text: str) -> str:
    s = str(text or "").lower()
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _html_to_text(html: str) -> str:
    raw = str(html or "")
    if not raw.strip():
        return ""
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(raw, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)


def _block_to_text(block: dict[str, Any]) -> str:
    t = str(block.get("type") or "").strip().lower()
    if t == "text":
        return str(block.get("text") or "")
    if t == "table":
        return _html_to_text(str(block.get("table_body") or ""))
    return _html_to_text(str(block.get("text") or "") or str(block.get("caption") or ""))


def load_content_list_blocks(auto_out: Any) -> list[dict[str, Any]]:
    p = getattr(auto_out, "content_list_json", None)
    if not p:
        return []
    try:
        data = read_json(Path(str(p)))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _build_block_text_index(
    blocks: list[dict[str, Any]]
) -> tuple[str, list[int], list[tuple[int, int]]]:
    parts: list[str] = []
    starts: list[int] = []
    spans: list[tuple[int, int]] = []

    pos = 0
    for b in blocks:
        txt = _norm_text(_block_to_text(b))
        starts.append(pos)
        parts.append(txt)
        pos += len(txt)
        spans.append((starts[-1], pos))
        pos += 1

    return "\n".join(parts), starts, spans


def _index_to_block_idx(i: int, starts: list[int]) -> int | None:
    if i < 0 or not starts:
        return None
    j = bisect.bisect_right(starts, i) - 1
    if j < 0:
        return None
    return int(j)


def enrich_chunks_with_blocks(chunks: list[Chunk], blocks: list[dict[str, Any]]) -> None:
    if not chunks or not blocks:
        return

    doc_text, starts, _spans = _build_block_text_index(blocks)

    for c in chunks:
        ch = _norm_text(c.text)
        if not ch:
            continue

        probe_a = ch[:200]
        probe_b = ch[-200:]
        pos_a = doc_text.find(probe_a) if len(probe_a) >= 30 else -1
        pos_b = doc_text.rfind(probe_b) if len(probe_b) >= 30 else -1

        ia = _index_to_block_idx(pos_a, starts) if pos_a >= 0 else None
        ib = _index_to_block_idx(pos_b, starts) if pos_b >= 0 else None

        if ia is None and ib is None:
            continue

        if ia is None:
            ia = ib
        if ib is None:
            ib = ia
        if ia is None or ib is None:
            continue

        lo = int(min(ia, ib))
        hi = int(max(ia, ib))
        span = blocks[lo: hi + 1]

        pages = [b.get("page_idx")
                 for b in span if isinstance(b.get("page_idx"), int)]
        block_types = sorted(
            {
                str(b.get("type") or "").strip().lower()
                for b in span
                if b.get("type")
            }
        )
        img_paths: list[str] = []
        for b in span:
            ip = b.get("img_path")
            if isinstance(ip, str) and ip.strip():
                img_paths.append(ip.strip())

        c.metadata["block_start"] = lo
        c.metadata["block_end"] = hi
        c.metadata["page_start"] = min(pages) if pages else None
        c.metadata["page_end"] = max(pages) if pages else None
        c.metadata["block_types"] = block_types
        if img_paths:
            c.metadata["img_paths"] = sorted(set(img_paths))


def table_documents_from_blocks(
    blocks: list[dict[str, Any]],
    base_meta: dict[str, Any],
    Document: Any,
) -> list[Any]:
    docs: list[Any] = []

    enable_cells = (
        os.getenv("FRA_TABLE_CELL_INDEX", "0").strip().lower()
        in {"1", "true", "yes"}
    )
    cell_cap = int(os.getenv("FRA_TABLE_CELL_CAP", "2000") or 2000)
    cell_count = 0

    for bi, b in enumerate(blocks):
        if str(b.get("type") or "").strip().lower() != "table":
            continue

        html = str(b.get("table_body") or "").strip()
        if not html:
            continue

        try:
            from bs4 import BeautifulSoup  # type: ignore

            soup = BeautifulSoup(html, "html.parser")
            trs = soup.find_all("tr")
            rows: list[list[str]] = []
            for tr in trs:
                tds = tr.find_all(["td", "th"])
                cells = [td.get_text(" ", strip=True) for td in tds]
                rows.append([c for c in cells if c is not None])
        except Exception:
            continue

        rows = [r for r in rows if any((c or "").strip() for c in r)]
        if not rows:
            continue

        headers: list[str] = []
        body_rows = rows
        if len(rows) >= 2:
            headers = [c.strip() for c in rows[0]]
            body_rows = rows[1:]

        page_idx = b.get("page_idx") if isinstance(
            b.get("page_idx"), int) else None
        bbox = b.get("bbox") if isinstance(b.get("bbox"), list) else None
        img_path = b.get("img_path") if isinstance(
            b.get("img_path"), str) else None

        for ri, r in enumerate(body_rows):
            pairs: list[str] = []
            for ci, cell in enumerate(r):
                h = headers[ci] if ci < len(
                    headers) and headers[ci] else f"col_{ci + 1}"
                v = (cell or "").strip()
                if v:
                    pairs.append(f"{h}: {v}")

            row_text = (
                " ; ".join(pairs)
                if pairs
                else " ; ".join([c for c in r if (c or "").strip()])
            )
            row_text = row_text.strip()
            if not row_text:
                continue

            meta = dict(base_meta)
            meta.update(
                {
                    "source_kind": "mineru_table_row",
                    "block_index": bi,
                    "table_row": int(ri),
                    "page_idx": page_idx,
                    "bbox": bbox,
                    "img_path": img_path,
                }
            )
            docs.append(
                make_document(
                    Document, text=f"TABLE ROW\n{row_text}", metadata=meta
                )
            )

            if enable_cells and cell_count < cell_cap:
                for ci, cell in enumerate(r):
                    v = (cell or "").strip()
                    if not v:
                        continue
                    h = (
                        headers[ci]
                        if ci < len(headers) and headers[ci]
                        else f"col_{ci + 1}"
                    )
                    meta2 = dict(base_meta)
                    meta2.update(
                        {
                            "source_kind": "mineru_table_cell",
                            "block_index": bi,
                            "table_row": int(ri),
                            "table_col": int(ci),
                            "header": h,
                            "page_idx": page_idx,
                            "bbox": bbox,
                            "img_path": img_path,
                        }
                    )
                    docs.append(
                        make_document(
                            Document, text=f"TABLE CELL\n{h}: {v}", metadata=meta2
                        )
                    )
                    cell_count += 1
                    if cell_count >= cell_cap:
                        break

    return docs


def image_documents_from_blocks(
    blocks: list[dict[str, Any]],
    base_meta: dict[str, Any],
    Document: Any,
) -> list[Any]:
    docs: list[Any] = []

    for i, b in enumerate(blocks):
        img_path = b.get("img_path")
        if not isinstance(img_path, str) or not img_path.strip():
            continue

        page_idx = b.get("page_idx") if isinstance(
            b.get("page_idx"), int) else None
        bbox = b.get("bbox") if isinstance(b.get("bbox"), list) else None
        btype = str(b.get("type") or "").strip().lower()

        cap = b.get("table_caption") if isinstance(
            b.get("table_caption"), list) else None
        foot = (
            b.get("table_footnote")
            if isinstance(b.get("table_footnote"), list)
            else None
        )
        cap_text = " ".join(
            [str(x).strip() for x in (cap or []) if str(x).strip()]
        )
        foot_text = " ".join(
            [str(x).strip() for x in (foot or []) if str(x).strip()]
        )

        neigh: list[str] = []
        for j in range(max(0, i - 2), min(len(blocks), i + 3)):
            if j == i:
                continue
            bj = blocks[j]
            if page_idx is not None and bj.get("page_idx") != page_idx:
                continue
            if str(bj.get("type") or "").strip().lower() != "text":
                continue
            t = str(bj.get("text") or "").strip()
            if t:
                neigh.append(t)

        ctx = "\n".join(
            [x for x in [cap_text, foot_text, "\n".join(neigh)] if x.strip()]
        ).strip()
        if not ctx:
            continue

        meta = dict(base_meta)
        meta.update(
            {
                "source_kind": "mineru_image_evidence",
                "block_index": int(i),
                "block_type": btype,
                "page_idx": page_idx,
                "bbox": bbox,
                "img_path": img_path.strip(),
            }
        )
        docs.append(
            make_document(
                Document, text=f"IMAGE EVIDENCE\n{ctx}", metadata=meta
            )
        )

    return docs
