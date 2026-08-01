"""Celery entrypoints for knowledge ingest (autodiscovered)."""

from apps.knowledge.services.embed_jobs import embed_chunks, embed_resolution_pairs  # noqa: F401
from apps.knowledge.services.ingest import ingest_gorgias_sources, ingest_website  # noqa: F401
