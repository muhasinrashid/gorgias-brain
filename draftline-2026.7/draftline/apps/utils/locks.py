"""Cross-process locks backed by the Django cache (Redis in dev/prod)."""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager

from django.core.cache import caches

logger = logging.getLogger(__name__)

LOCK_CACHE_ALIAS = "locks"


def lock_cache():
    """Redis-backed cache. The default cache is a DummyCache under DEBUG."""
    return caches[LOCK_CACHE_ALIAS]


@contextmanager
def single_flight(key: str, *, timeout: int = 3600):
    """Yield True when this caller owns ``key``, False when another holder does.

    ``timeout`` must exceed the longest expected run, otherwise a second copy
    can start while the first is still working.
    """
    cache = lock_cache()
    lock_key = f"lock:{key}"
    token = uuid.uuid4().hex
    acquired = bool(cache.add(lock_key, token, timeout))
    if not acquired:
        logger.info("single_flight busy for %s", key)
    try:
        yield acquired
    finally:
        if acquired and cache.get(lock_key) == token:
            cache.delete(lock_key)
