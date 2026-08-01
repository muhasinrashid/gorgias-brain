"""Hybrid retrieval stub — lexical + vector with source-type precedence."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q
from pgvector.django import CosineDistance

from apps.knowledge.models import Chunk, CuratedKnowledge, CuratedStatus, ResolutionPair, SourceType
from apps.knowledge.services.embeddings import embed_query, embedder_ready

PRECEDENCE = {
    "curated": 1.0,
    SourceType.HELP_CENTER_ARTICLE: 0.85,
    SourceType.WEB_PAGE: 0.8,
    "resolution_pair": 0.7,
    SourceType.MACRO: 0.35,  # phrasing only
    SourceType.FILE: 0.5,
}


@dataclass
class RetrievalHit:
    kind: str
    score: float
    text: str
    title: str
    source_id: int | None
    char_offset_start: int | None
    char_offset_end: int | None
    metadata: dict


def _blend(vector_score: float, lexical_score: float, precedence: float) -> float:
    # CosineDistance is lower-is-better; convert to similarity in [0,1]
    sim = max(0.0, 1.0 - float(vector_score))
    lex = min(1.0, max(0.0, float(lexical_score or 0.0)))
    return precedence * (0.7 * sim + 0.3 * lex)


def retrieve(team, query: str, *, limit: int = 5) -> list[RetrievalHit]:
    """Return top hits for drafting context. Team-scoped; never a customer-send path."""
    query = (query or "").strip()
    if not query:
        return []

    hits: list[RetrievalHit] = []

    # Curated first (lexical for stub; embed later when approved rows are common)
    curated = (
        CuratedKnowledge.objects.filter(team=team, status=CuratedStatus.APPROVED)
        .filter(Q(question__icontains=query[:80]) | Q(answer__icontains=query[:80]))
        .order_by("-approved_at")[:limit]
    )
    for row in curated:
        hits.append(
            RetrievalHit(
                kind="curated",
                score=PRECEDENCE["curated"],
                text=f"Q: {row.question}\nA: {row.answer}",
                title="Curated knowledge",
                source_id=None,
                char_offset_start=None,
                char_offset_end=None,
                metadata={"curated_id": row.id, "intent": row.intent},
            )
        )

    vector = None
    if embedder_ready():
        try:
            vector = embed_query(query)
        except Exception:
            vector = None

    chunk_qs = Chunk.objects.filter(team=team, source__is_active=True).select_related("source")
    if vector is not None:
        chunk_qs = chunk_qs.exclude(embedding__isnull=True).annotate(
            distance=CosineDistance("embedding", vector)
        )
        # Prefer factual source types over macros in ordering before blend
        chunk_qs = chunk_qs.order_by("distance")[: max(limit * 4, 20)]
        for chunk in chunk_qs:
            st = chunk.source.source_type
            prec = PRECEDENCE.get(st, 0.4)
            if st == SourceType.MACRO:
                # Macros are phrasing-only — downrank hard unless query is short style match
                prec = PRECEDENCE[SourceType.MACRO]
            score = _blend(chunk.distance, 0.0, prec)
            hits.append(
                RetrievalHit(
                    kind="chunk",
                    score=score,
                    text=chunk.text,
                    title=chunk.source.title or chunk.source.external_id,
                    source_id=chunk.source_id,
                    char_offset_start=chunk.char_offset_start,
                    char_offset_end=chunk.char_offset_end,
                    metadata={
                        "chunk_id": chunk.id,
                        "source_type": st,
                        "distance": float(chunk.distance),
                    },
                )
            )
    else:
        # Lexical fallback when embeddings unavailable
        chunk_qs = chunk_qs.filter(text__icontains=query[:80]).order_by("-id")[: max(limit * 3, 15)]
        for chunk in chunk_qs:
            st = chunk.source.source_type
            hits.append(
                RetrievalHit(
                    kind="chunk",
                    score=PRECEDENCE.get(st, 0.4) * 0.5,
                    text=chunk.text,
                    title=chunk.source.title or chunk.source.external_id,
                    source_id=chunk.source_id,
                    char_offset_start=chunk.char_offset_start,
                    char_offset_end=chunk.char_offset_end,
                    metadata={"chunk_id": chunk.id, "source_type": st, "lexical": True},
                )
            )

    rp_qs = ResolutionPair.objects.filter(team=team)
    if vector is not None:
        rp_qs = (
            rp_qs.exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", vector))
            .order_by("distance")[: max(limit * 2, 10)]
        )
        for pair in rp_qs:
            score = _blend(pair.distance, 0.0, PRECEDENCE["resolution_pair"])
            if pair.is_exemplar:
                score *= 1.1
            hits.append(
                RetrievalHit(
                    kind="resolution_pair",
                    score=score,
                    text=f"Q: {pair.question_text}\nA: {pair.resolution_text}",
                    title=pair.intent or "Past resolution",
                    source_id=pair.source_id,
                    char_offset_start=None,
                    char_offset_end=None,
                    metadata={
                        "resolution_pair_id": pair.id,
                        "ticket_ids": pair.source_ticket_ids,
                        "quality_score": pair.quality_score,
                    },
                )
            )
    else:
        rp_qs = rp_qs.filter(
            Q(question_text__icontains=query[:80]) | Q(resolution_text__icontains=query[:80])
        ).order_by("-quality_score")[:limit]
        for pair in rp_qs:
            hits.append(
                RetrievalHit(
                    kind="resolution_pair",
                    score=PRECEDENCE["resolution_pair"] * 0.5,
                    text=f"Q: {pair.question_text}\nA: {pair.resolution_text}",
                    title=pair.intent or "Past resolution",
                    source_id=pair.source_id,
                    char_offset_start=None,
                    char_offset_end=None,
                    metadata={"resolution_pair_id": pair.id, "lexical": True},
                )
            )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
