"""Citation helpers — prove chunk offsets resolve against source text."""

from __future__ import annotations

from dataclasses import dataclass

from apps.knowledge.models import Chunk


@dataclass
class CitationResolve:
    ok: bool
    expected: str
    actual: str
    message: str = ""


def resolve_chunk_citation(chunk: Chunk) -> CitationResolve:
    """Verify Source.normalised_content[start:end] matches chunk.text (whitespace-tolerant)."""
    source = chunk.source
    body = source.normalised_content or source.raw_content or ""
    start = int(chunk.char_offset_start or 0)
    end = int(chunk.char_offset_end or 0)
    if end < start or end > len(body) + 50:
        return CitationResolve(False, chunk.text, "", f"bad offsets {start}:{end} on source len={len(body)}")
    # Allow slight end overrun from truncation
    slice_ = body[start:min(end, len(body))]
    norm_slice = " ".join(slice_.split())
    norm_chunk = " ".join((chunk.text or "").split())
    if not norm_chunk:
        return CitationResolve(False, chunk.text, slice_, "empty chunk")
    # Exact or prefix (chunking may trim)
    if norm_slice == norm_chunk or norm_slice.startswith(norm_chunk[: min(80, len(norm_chunk))]):
        return CitationResolve(True, chunk.text, slice_)
    if norm_chunk[:60] in norm_slice or norm_slice[:60] in norm_chunk:
        return CitationResolve(True, chunk.text, slice_, "fuzzy match")
    return CitationResolve(False, chunk.text, slice_, "offset text mismatch")


def citation_dict(chunk: Chunk) -> dict:
    resolved = resolve_chunk_citation(chunk)
    return {
        "source_id": chunk.source_id,
        "chunk_id": chunk.id,
        "char_offset_start": chunk.char_offset_start,
        "char_offset_end": chunk.char_offset_end,
        "url": chunk.source.url or "",
        "title": chunk.source.title or "",
        "resolves": resolved.ok,
        "resolve_message": resolved.message,
    }
