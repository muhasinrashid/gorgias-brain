"""Language detection for retrieval / eval (EN, DE, FR, ES, IT)."""

from __future__ import annotations

import re

_LANG_MARKERS = {
    "de": re.compile(r"[äöüß]|\b(?:und|nicht|bitte|wurde|werden|sich|mit|für|eine|dieser)\b", re.I),
    "fr": re.compile(
        r"[àâäéèêëïîôùûüçœæ]|\b(?:bonjour|merci|votre|nous|avec|pour|cette|commande)\b",
        re.I,
    ),
    "es": re.compile(
        r"[ñ¿¡]|\b(?:gracias|pedido|hola|usted|nuestro|envío|devolución)\b",
        re.I,
    ),
    "it": re.compile(
        r"\b(?:grazie|ordine|ciao|prego|vorrei|spedizione|garanzia|restituzione)\b",
        re.I,
    ),
}


def detect_language(text: str) -> str:
    """Return ISO-ish code: en|de|fr|es|it|und."""
    sample = (text or "")[:2500]
    if not sample.strip():
        return "und"
    scores: dict[str, int] = {}
    for lang, pat in _LANG_MARKERS.items():
        scores[lang] = len(pat.findall(sample))
    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        # Prefer DE over FR when both diacritics fire
        if best == "fr" and scores.get("de", 0) >= scores["fr"]:
            return "de"
        return best
    if re.search(r"[A-Za-zÀ-ÿ]", sample):
        return "en"
    return "und"


def language_match_bonus(query_lang: str, candidate_lang: str) -> float:
    """Boost same-language material; soft-penalize clear mismatches."""
    q = (query_lang or "").lower()[:2]
    c = (candidate_lang or "").lower()[:2]
    if not q or q == "und" or not c or c == "und":
        return 0.0
    if q == c:
        return 0.12
    # Cross-language policy docs still useful but downranked
    return -0.08
