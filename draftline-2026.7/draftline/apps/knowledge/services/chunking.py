"""Split Source content into Chunk rows (embeddings filled later)."""

from __future__ import annotations

import re

from apps.knowledge.models import Chunk, Source, SourceType

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def split_text(text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[tuple[int, int, str]]:
    """Return list of (start, end, piece) with character offsets into original text."""
    text = text or ""
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [(0, len(text), text)]

    separators = ["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]
    pieces: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            window = text[start:end]
            best_rel = -1
            for sep in separators:
                if not sep:
                    best_rel = len(window)
                    break
                idx = window.rfind(sep)
                if idx >= chunk_size // 4:
                    best_rel = idx + len(sep)
                    break
            if best_rel > 0:
                end = start + best_rel
        piece = text[start:end]
        if piece.strip():
            pieces.append((start, end, piece))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return pieces


def estimate_tokens(text: str) -> int:
    # Rough heuristic until tiktoken wired
    return max(1, len(re.findall(r"\S+", text or "")))


def chunk_source(source: Source, *, replace: bool = True) -> int:
    """Create Chunk rows for a Source. Does not embed. Returns chunk count."""
    if source.source_type == SourceType.MACRO and (source.metadata or {}).get("as_phrasing_only"):
        # Macros: keep as single phrasing chunk tagged in metadata path later
        body = source.normalised_content or source.raw_content or ""
    else:
        body = source.normalised_content or source.raw_content or ""

    spans = split_text(body)
    if replace:
        Chunk.objects.filter(team=source.team, source=source).delete()

    created = 0
    for ordinal, (start, end, piece) in enumerate(spans):
        Chunk.objects.create(
            team=source.team,
            source=source,
            ordinal=ordinal,
            text=piece,
            token_count=estimate_tokens(piece),
            char_offset_start=start,
            char_offset_end=end,
            language=source.language or "",
        )
        created += 1
    return created


def chunk_sources_for_team(team, *, source_types: list[str] | None = None, limit: int = 0) -> dict:
    qs = Source.objects.filter(team=team, is_active=True).order_by("id")
    if source_types:
        qs = qs.filter(source_type__in=source_types)
    if limit:
        qs = qs[:limit]
    total_sources = 0
    total_chunks = 0
    for source in qs.iterator():
        total_chunks += chunk_source(source, replace=True)
        total_sources += 1
    return {"sources": total_sources, "chunks": total_chunks}
