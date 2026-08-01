"""Celery entrypoints for knowledge ingest (autodiscovered)."""

from apps.knowledge.services.ingest import ingest_gorgias_sources, ingest_website  # noqa: F401
