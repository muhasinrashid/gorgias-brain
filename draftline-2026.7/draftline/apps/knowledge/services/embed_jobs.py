"""Embed Chunk / ResolutionPair rows via Azure OpenAI."""

from __future__ import annotations

import logging

from django.conf import settings

from apps.knowledge.models import Chunk, ResolutionPair
from apps.knowledge.services.embeddings import EMBEDDER_VERSION, embed_texts, embedder_ready
from apps.teams.celery import team_task
from apps.utils.locks import single_flight

logger = logging.getLogger(__name__)

EMBED_LOCK_TIMEOUT = 2 * 60 * 60
CHUNK_BATCH = 32


@team_task(bind=True, name="knowledge.embed_chunks", queue="sync", max_retries=2)
def embed_chunks(self, team_id: int, limit: int = 0, only_missing: bool = True):
    with single_flight(f"embed_chunks:{team_id}", timeout=EMBED_LOCK_TIMEOUT) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "already running"}
        return _embed_chunks(team_id=team_id, limit=limit, only_missing=only_missing)


def _embed_chunks(*, team_id: int, limit: int, only_missing: bool) -> dict:
    from apps.teams.models import Team

    if not embedder_ready():
        raise RuntimeError("Embedding provider not configured")

    team = Team.objects.get(pk=team_id)
    qs = Chunk.objects.filter(team=team).order_by("id")
    if only_missing:
        qs = qs.filter(embedding__isnull=True)
    if limit:
        qs = qs[:limit]

    ids = list(qs.values_list("id", flat=True))
    embedded = 0
    for start in range(0, len(ids), CHUNK_BATCH):
        batch_ids = ids[start : start + CHUNK_BATCH]
        chunks = list(Chunk.objects.filter(id__in=batch_ids).order_by("id"))
        vectors = embed_texts([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedder_version = EMBEDDER_VERSION
            chunk.save(update_fields=["embedding", "embedder_version", "updated_at"])
            embedded += 1
    return {"embedded": embedded, "requested": len(ids), "dims": settings.EMBEDDING_DIMENSIONS}


@team_task(bind=True, name="knowledge.embed_resolution_pairs", queue="sync", max_retries=2)
def embed_resolution_pairs(self, team_id: int, limit: int = 0, only_missing: bool = True):
    with single_flight(f"embed_rps:{team_id}", timeout=EMBED_LOCK_TIMEOUT) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "already running"}
        return _embed_resolution_pairs(team_id=team_id, limit=limit, only_missing=only_missing)


def _embed_resolution_pairs(*, team_id: int, limit: int, only_missing: bool) -> dict:
    from apps.teams.models import Team

    if not embedder_ready():
        raise RuntimeError("Embedding provider not configured")

    team = Team.objects.get(pk=team_id)
    qs = ResolutionPair.objects.filter(team=team).order_by("id")
    if only_missing:
        qs = qs.filter(embedding__isnull=True)
    if limit:
        qs = qs[:limit]

    ids = list(qs.values_list("id", flat=True))
    embedded = 0
    for start in range(0, len(ids), CHUNK_BATCH):
        batch_ids = ids[start : start + CHUNK_BATCH]
        pairs = list(ResolutionPair.objects.filter(id__in=batch_ids).order_by("id"))
        texts = [f"{p.question_text}\n\n{p.resolution_text}" for p in pairs]
        vectors = embed_texts(texts)
        for pair, vector in zip(pairs, vectors, strict=True):
            pair.embedding = vector
            pair.embedder_version = EMBEDDER_VERSION
            pair.save(update_fields=["embedding", "embedder_version", "updated_at"])
            embedded += 1
    return {"embedded": embedded, "requested": len(ids)}
