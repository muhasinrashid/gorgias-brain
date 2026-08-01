"""Embedding adapter — Azure OpenAI text-embedding-3-small (1536-d)."""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

EMBEDDER_VERSION = "azure-text-embedding-3-small-v1"
BATCH_SIZE = 64


class EmbeddingError(RuntimeError):
    pass


def embedder_ready() -> bool:
    return bool(
        getattr(settings, "AZURE_OPENAI_API_KEY", "")
        and getattr(settings, "AZURE_OPENAI_ENDPOINT", "")
        and getattr(settings, "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "")
    )


def _client():
    from openai import AzureOpenAI

    if not embedder_ready():
        raise EmbeddingError(
            "Azure OpenAI embedding settings missing "
            "(AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME)."
        )
    return AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=getattr(settings, "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT.rstrip("/"),
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings; empty strings become zero vectors of configured dim."""
    if not texts:
        return []
    dims = int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))
    deployment = settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME
    client = _client()
    out: list[list[float] | None] = [None] * len(texts)
    pending_idx: list[int] = []
    pending_text: list[str] = []
    for i, text in enumerate(texts):
        cleaned = (text or "").strip()
        if not cleaned:
            out[i] = [0.0] * dims
        else:
            pending_idx.append(i)
            pending_text.append(cleaned[:8000])

    for start in range(0, len(pending_text), BATCH_SIZE):
        batch = pending_text[start : start + BATCH_SIZE]
        batch_idx = pending_idx[start : start + BATCH_SIZE]
        response = client.embeddings.create(model=deployment, input=batch)
        by_index = {item.index: item.embedding for item in response.data}
        for j, original_i in enumerate(batch_idx):
            out[original_i] = list(by_index[j])

    return [vec if vec is not None else [0.0] * dims for vec in out]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
