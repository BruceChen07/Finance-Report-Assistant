from __future__ import annotations

import os
from typing import Any


def configure_embedding(Settings: Any) -> None:
    provider = (os.getenv("FRA_EMBEDDING_PROVIDER") or "bge").strip().lower()

    if provider == "openai":
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "OpenAI embedding support is missing. Please install llama-index-embeddings-openai."
            ) from e

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv(
            "FRA_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Set OPENAI_API_KEY (or FRA_OPENAI_API_KEY) "
                "to build/query the vector index with OpenAI embeddings."
            )

        Settings.embed_model = OpenAIEmbedding()
        return

    if provider in {"bge", "hf", "huggingface"}:
        try:
            import torch
            import torch.nn.functional as F
            from modelscope.hub.snapshot_download import snapshot_download
            from transformers import AutoModel, AutoTokenizer
            from llama_index.core.base.embeddings.base import BaseEmbedding
            from llama_index.core.bridge.pydantic import Field, PrivateAttr
        except Exception as e:
            raise RuntimeError(
                "Local BGE embeddings require torch + transformers + modelscope + llama_index.core."
            ) from e

        class _BgeEmbedding(BaseEmbedding):
            model_name: str = Field(default="BAAI/bge-small-en-v1.5")
            max_length: int = Field(default=512, gt=16, le=8192)
            pooling: str = Field(default="cls")
            normalize: bool = Field(default=True)
            query_prefix: str = Field(default="query: ")
            text_prefix: str = Field(default="passage: ")
            device: str = Field(default="auto")

            _tokenizer: Any = PrivateAttr()
            _model: Any = PrivateAttr()
            _device: Any = PrivateAttr()

            def __init__(
                self,
                *,
                model_name: str,
                embed_batch_size: int = 16,
                max_length: int = 512,
                pooling: str = "cls",
                normalize: bool = True,
                query_prefix: str = "query: ",
                text_prefix: str = "passage: ",
                device: str = "auto",
                **kwargs: Any,
            ) -> None:
                super().__init__(
                    model_name=model_name,
                    embed_batch_size=embed_batch_size,
                    max_length=max_length,
                    pooling=pooling,
                    normalize=normalize,
                    query_prefix=query_prefix,
                    text_prefix=text_prefix,
                    device=device,
                    **kwargs,
                )

                dev = (device or "auto").strip().lower()
                if dev == "auto":
                    dev = "cuda" if torch.cuda.is_available() else "cpu"
                self._device = torch.device(dev)

                cache_dir = os.getenv("FRA_BGE_MODELSCOPE_CACHE_DIR") or None
                model_id = os.getenv("FRA_BGE_MODELSCOPE_MODEL", "").strip() or str(
                    model_name
                )
                revision = os.getenv("FRA_BGE_MODELSCOPE_REVISION") or None
                trust_remote_code = (
                    os.getenv("FRA_BGE_TRUST_REMOTE_CODE", "0")
                    .strip()
                    .lower()
                    in {"1", "true", "yes"}
                )

                local_dir = snapshot_download(
                    model_id=model_id, cache_dir=cache_dir, revision=revision
                )

                self._tokenizer = AutoTokenizer.from_pretrained(
                    local_dir,
                    local_files_only=True,
                    trust_remote_code=trust_remote_code,
                )
                self._model = AutoModel.from_pretrained(
                    local_dir,
                    local_files_only=True,
                    trust_remote_code=trust_remote_code,
                )
                self._model.to(self._device)
                self._model.eval()

            def _encode(self, texts: list[str]) -> list[list[float]]:
                if not texts:
                    return []

                inputs = self._tokenizer(
                    texts,
                    padding=True,
                    truncation=True,
                    max_length=int(self.max_length),
                    return_tensors="pt",
                )
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

                with torch.no_grad():
                    out = self._model(**inputs)
                    last = out.last_hidden_state
                    if str(self.pooling).strip().lower() == "mean":
                        mask = inputs.get("attention_mask")
                        if mask is None:
                            emb = last.mean(dim=1)
                        else:
                            m = mask.unsqueeze(-1).to(last.dtype)
                            emb = (last * m).sum(dim=1) / torch.clamp(
                                m.sum(dim=1), min=1e-6
                            )
                    else:
                        emb = last[:, 0]

                    if bool(self.normalize):
                        emb = torch.nn.functional.normalize(emb, p=2, dim=1)

                return emb.detach().cpu().tolist()

            def _get_query_embedding(self, query: str) -> list[float]:
                q = f"{self.query_prefix}{query}" if self.query_prefix else str(
                    query)
                return self._encode([q])[0]

            async def _aget_query_embedding(self, query: str) -> list[float]:
                return self._get_query_embedding(query)

            def _get_text_embedding(self, text: str) -> list[float]:
                t = f"{self.text_prefix}{text}" if self.text_prefix else str(
                    text)
                return self._encode([t])[0]

            def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
                ts = [
                    f"{self.text_prefix}{t}" if self.text_prefix else str(t)
                    for t in texts
                ]
                return self._encode(ts)

        model_name = (
            os.getenv("FRA_BGE_MODEL", "BAAI/bge-small-en-v1.5").strip()
            or "BAAI/bge-small-en-v1.5"
        )
        batch_size = int(os.getenv("FRA_BGE_BATCH_SIZE", "16") or 16)
        max_length = int(os.getenv("FRA_BGE_MAX_LENGTH", "512") or 512)
        pooling = os.getenv("FRA_BGE_POOLING", "cls").strip().lower() or "cls"
        normalize = (
            os.getenv("FRA_BGE_NORMALIZE", "1").strip().lower()
            in {"1", "true", "yes"}
        )
        query_prefix = os.getenv("FRA_BGE_QUERY_PREFIX", "query: ")
        text_prefix = os.getenv("FRA_BGE_TEXT_PREFIX", "passage: ")
        device = os.getenv("FRA_BGE_DEVICE", "auto")

        Settings.embed_model = _BgeEmbedding(
            model_name=model_name,
            embed_batch_size=batch_size,
            max_length=max_length,
            pooling=pooling,
            normalize=normalize,
            query_prefix=query_prefix,
            text_prefix=text_prefix,
            device=device,
        )
        return

    raise RuntimeError(
        f"Unsupported FRA_EMBEDDING_PROVIDER={provider}. "
        "Supported: openai, bge"
    )
