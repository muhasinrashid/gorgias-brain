"""Hybrid retrieval — lexical + vector with precedence, language, recency, diversity."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from django.db.models import Q
from django.utils import timezone
from pgvector.django import CosineDistance

from apps.knowledge.models import Chunk, CuratedKnowledge, CuratedStatus, ResolutionPair, SourceType
from apps.knowledge.services.embeddings import embed_query, embedder_ready
from apps.knowledge.services.language import detect_language, language_match_bonus

PRECEDENCE = {
    "curated": 1.2,
    SourceType.HELP_CENTER_ARTICLE: 1.0,
    SourceType.WEB_PAGE: 0.85,
    "resolution_pair": 0.5,
    "macro_phrasing": 0.28,  # phrasing only — never factual source of truth
    SourceType.MACRO: 0.28,
    SourceType.FILE: 0.5,
}

_WORD = re.compile(r"[a-z0-9']+", re.I)
_TRACKING = re.compile(
    r"\b(?:1Z[A-Z0-9]{16}|\d{20,}|(?:tracking|return)\s*label[:\s#-]*[A-Z0-9]{8,})\b",
    re.I,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
_PII_NAME_LINE = re.compile(
    r"\b(?:dear|hi|hello)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b|"
    r"\b(?:mr\.|mrs\.|ms\.)\s+[A-Z][a-z]+\b|"
    r"Serial\s*#?\s*\d+",
    re.I,
)
_ADDRESSISH = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+\s*(?:St|Street|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr)\b",
    re.I,
)

_FAQ_URL = re.compile(r"/faqs?/|hcUrl=|/help|/articles?/|/support", re.I)
_NOISE_URL = re.compile(
    r"/login|/search|/collections?/|/cart|/checkout|/products?/|"
    r"/accessories/|/formex-world|/our-story",
    re.I,
)
_LEGAL_URL = re.compile(r"/terms|/privacy", re.I)
_LEGALISH = re.compile(
    r"\b(?:terms of service|privacy policy|cookie|governing law|hereby|hereinafter|"
    r"\d+\.\s+[A-Z])\b",
    re.I,
)

_INTENT_TOKENS = {
    "return": {"return", "returns", "refund", "exchange", "send back"},
    "shipping": {"ship", "shipping", "shipment", "delivery", "deliver", "transit", "carrier"},
    "warranty": {"warranty", "warranties", "guarantee", "service", "repair", "defective"},
    "payment": {"payment", "pay", "invoice", "refund", "charge"},
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


def _detect_intents(query: str) -> set[str]:
    q = (query or "").lower()
    found: set[str] = set()
    for intent, toks in _INTENT_TOKENS.items():
        if any(t in q for t in toks) or intent in q:
            found.add(intent)
    if "return" in found and "shipping" in found and "ship" not in q and "deliver" not in q:
        if not any(t in q for t in ("ship", "deliver", "transit")):
            found.discard("shipping")
    return found


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD.findall(text or "") if len(t) > 2}


def _lexical_overlap(query: str, text: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    t = _tokens(text)
    return len(q & t) / len(q)


def _intent_token_hits(intent: str, blob: str) -> int:
    return sum(1 for tok in _INTENT_TOKENS[intent] if tok in blob)


def _topical_score(intents: set[str], text: str, title: str) -> float:
    if not intents:
        return 0.0
    blob = f"{title}\n{text}".lower()
    title_l = (title or "").lower()
    score = 0.0
    matched = 0
    for intent in intents:
        n = _intent_token_hits(intent, blob)
        if n == 0:
            continue
        matched += 1
        score += 0.08 if n == 1 else 0.16
        if intent in title_l or any(tok in title_l for tok in _INTENT_TOKENS[intent]):
            score += 0.18
    if matched == 0:
        return -0.4
    if "shipping" in intents and any(w in title_l for w in ("return", "refund")) and not any(
        w in title_l for w in ("ship", "deliver")
    ):
        score -= 0.45
    if "warranty" in intents and "return" in title_l and "warrant" not in title_l:
        score -= 0.45
    if "warranty" in intents and any(
        w in title_l for w in ("ordered the wrong", "pay for shipping", "gift wrapping", "payment option")
    ):
        score -= 0.4
    if "return" in intents and any(w in title_l for w in ("ship", "deliver")) and "return" not in title_l:
        score -= 0.35
    if "warranty" in intents and re.search(r"\b(?:three|3)\s*-?\s*year[s]?\b.{0,40}\bwarrant", blob):
        score += 0.25
    if "shipping" in intents and re.search(
        r"\b(?:business days|working days|within \d+ days).{0,30}\b(?:ship|deliver)", blob
    ):
        score += 0.2
    return score


def _title_boost(query: str, title: str, url: str, metadata: dict | None) -> float:
    score = 0.0
    title_l = (title or "").lower()
    url_l = (url or "").lower()
    meta = metadata or {}
    q = _tokens(query)
    if q and _tokens(title) & q:
        score += 0.2
    if _FAQ_URL.search(url_l) or _FAQ_URL.search(title_l):
        score += 0.25
    if "?" in (title or "") or title_l.startswith(("can i ", "how ", "what ", "where ", "do you ")):
        score += 0.15
    if _NOISE_URL.search(url_l):
        score -= 0.4
    if _LEGAL_URL.search(url_l) or meta.get("noise_tier") == "legal":
        score -= 0.12
    if title_l in {"reef", "home", "search", "login"} or len(title_l) < 3:
        score -= 0.08
    if title_l.endswith("help center and contact") or "get more information" in title_l:
        score -= 0.08
    return score


def _chunk_quality(text: str, url: str) -> float:
    score = 0.0
    n = len(text or "")
    if 200 <= n <= 2500:
        score += 0.08
    elif n > 4000:
        score -= 0.1
    if _LEGALISH.search(text or "") and not _FAQ_URL.search(url or ""):
        score -= 0.12
    linkish = (text or "").count("](")
    if linkish >= 6 and n < 1200:
        score -= 0.15
    return score


def _pair_is_noisy(question: str, answer: str) -> bool:
    blob = f"{question}\n{answer}"
    if _TRACKING.search(blob) or _EMAIL.search(blob) or _PHONE.search(blob):
        return True
    if _ADDRESSISH.search(blob):
        return True
    if _PII_NAME_LINE.search(answer or "") and len((answer or "").strip()) < 400:
        if not any(k in blob.lower() for k in ("policy", "warranty", "return", "ship within", "business day")):
            return True
    if len((answer or "").strip()) < 80:
        return True
    if re.search(r"\b(?:thanks|lol|nj|fla|as discussed)\b", blob, re.I) and len(blob) < 240:
        return True
    return False


def _recency_csat_boost(pair: ResolutionPair, ticket_meta: dict) -> float:
    """Recent + high-CSAT resolving replies beat stale ones."""
    boost = 0.0
    tickets = list(pair.source_ticket_ids or [])
    ages = []
    csats = []
    for tid in tickets[:5]:
        meta = ticket_meta.get(str(tid)) or ticket_meta.get(tid)
        if not meta:
            continue
        created = meta.get("created")
        if created:
            ages.append((timezone.now() - created).days)
        if meta.get("csat") is not None:
            csats.append(float(meta["csat"]))
    if ages:
        age = min(ages)
        if age <= 30:
            boost += 0.12
        elif age <= 90:
            boost += 0.06
        elif age <= 180:
            boost += 0.02
        elif age >= 365:
            boost -= 0.08
    elif pair.updated_at:
        age = (timezone.now() - pair.updated_at).days
        if age <= 30:
            boost += 0.06
        elif age >= 365:
            boost -= 0.05
    if csats:
        avg = sum(csats) / len(csats)
        if avg >= 4.5:
            boost += 0.08
        elif avg >= 4.0:
            boost += 0.04
        elif avg <= 2.0:
            boost -= 0.06
    return boost


def _ticket_meta_for_pairs(team, pairs) -> dict:
    from apps.tickets.models import Ticket

    ids: set[str] = set()
    for p in pairs:
        for tid in p.source_ticket_ids or []:
            ids.add(str(tid))
    if not ids:
        return {}
    meta = {}
    for t in Ticket.objects.filter(team=team, external_id__in=list(ids)[:500]).only(
        "external_id", "created_at_external", "csat_score"
    ):
        meta[str(t.external_id)] = {
            "created": t.created_at_external,
            "csat": t.csat_score,
        }
    return meta


def _blend(distance: float, lexical: float, precedence: float, extras: float = 0.0) -> float:
    sim = max(0.0, 1.0 - float(distance))
    lex = min(1.0, max(0.0, float(lexical)))
    return precedence * (0.5 * sim + 0.5 * lex) + extras


def _content_key(hit: RetrievalHit) -> str:
    raw = re.sub(r"\s+", " ", (hit.text or "")[:400].lower()).strip()
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _diversify(hits: list[RetrievalHit], *, limit: int) -> list[RetrievalHit]:
    selected: list[RetrievalHit] = []
    per_source: dict[int | str, int] = {}
    seen_content: set[str] = set()
    pair_count = 0
    phrasing_count = 0
    max_pairs = max(1, limit // 2)
    max_phrasing = 1

    def source_key(hit: RetrievalHit):
        if hit.source_id is not None:
            return hit.source_id
        return f"{hit.kind}:{hit.metadata.get('resolution_pair_id') or hit.metadata.get('curated_id')}"

    for hit in hits:
        ck = _content_key(hit)
        if ck in seen_content:
            continue
        if hit.kind == "resolution_pair" and pair_count >= max_pairs:
            continue
        if hit.kind == "macro_phrasing" and phrasing_count >= max_phrasing:
            continue
        key = source_key(hit)
        if per_source.get(key, 0) >= 1:
            continue
        selected.append(hit)
        seen_content.add(ck)
        per_source[key] = per_source.get(key, 0) + 1
        if hit.kind == "resolution_pair":
            pair_count += 1
        if hit.kind == "macro_phrasing":
            phrasing_count += 1
        if len(selected) >= limit:
            return selected

    for hit in hits:
        if hit in selected:
            continue
        ck = _content_key(hit)
        if ck in seen_content:
            continue
        if hit.kind == "resolution_pair" and pair_count >= max_pairs:
            continue
        if hit.kind == "macro_phrasing" and phrasing_count >= max_phrasing:
            continue
        key = source_key(hit)
        if per_source.get(key, 0) >= 2:
            continue
        selected.append(hit)
        seen_content.add(ck)
        per_source[key] = per_source.get(key, 0) + 1
        if hit.kind == "resolution_pair":
            pair_count += 1
        if hit.kind == "macro_phrasing":
            phrasing_count += 1
        if len(selected) >= limit:
            break
    return selected


def retrieve(team, query: str, *, limit: int = 5, include_macro_phrasing: bool = True) -> list[RetrievalHit]:
    """Return top hits for drafting context. Team-scoped; never a customer-send path."""
    query = (query or "").strip()
    if not query:
        return []

    intents = _detect_intents(query)
    query_lang = detect_language(query)
    hits: list[RetrievalHit] = []
    candidate_limit = max(limit * 16, 48)

    curated = CuratedKnowledge.objects.filter(team=team, status=CuratedStatus.APPROVED).order_by("-approved_at")[
        :50
    ]
    for row in curated:
        lex = max(
            _lexical_overlap(query, row.question),
            _lexical_overlap(query, row.answer),
        )
        topical = _topical_score(intents, row.answer, row.question)
        lang_b = language_match_bonus(query_lang, row.language or detect_language(row.question))
        if lex < 0.15 and topical <= 0 and query.lower() not in (row.question or "").lower():
            continue
        hits.append(
            RetrievalHit(
                kind="curated",
                score=PRECEDENCE["curated"] * (0.45 + 0.55 * lex) + topical + lang_b,
                text=f"Q: {row.question}\nA: {row.answer}",
                title="Curated knowledge",
                source_id=None,
                char_offset_start=None,
                char_offset_end=None,
                metadata={
                    "curated_id": row.id,
                    "intent": row.intent,
                    "lexical": lex,
                    "language": row.language or query_lang,
                    "citation": {"kind": "curated", "curated_id": row.id},
                },
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
        chunk_qs = (
            chunk_qs.exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", vector))
            .order_by("distance")[:candidate_limit]
        )
    else:
        tokens = list(_tokens(query))[:6]
        q_filter = Q()
        for tok in tokens:
            q_filter |= Q(text__icontains=tok) | Q(source__title__icontains=tok)
        chunk_qs = chunk_qs.filter(q_filter).order_by("-id")[:candidate_limit] if tokens else chunk_qs.none()

    for chunk in chunk_qs:
        st = chunk.source.source_type
        url = chunk.source.url or ""
        title = chunk.source.title or chunk.source.external_id
        meta = chunk.source.metadata or {}
        distance = float(getattr(chunk, "distance", 0.35))
        lex = max(
            _lexical_overlap(query, chunk.text),
            _lexical_overlap(query, title),
        )
        lang = chunk.language or chunk.source.language or detect_language(chunk.text)
        lang_b = language_match_bonus(query_lang, lang)

        if st == SourceType.MACRO:
            if not include_macro_phrasing:
                continue
            # Phrasing-only: require strong lexical overlap so macros never invent policy
            if lex < 0.35:
                continue
            score = _blend(distance, lex, PRECEDENCE["macro_phrasing"], extras=lang_b)
            hits.append(
                RetrievalHit(
                    kind="macro_phrasing",
                    score=score,
                    text=chunk.text,
                    title=f"[Phrasing] {title}",
                    source_id=chunk.source_id,
                    char_offset_start=chunk.char_offset_start,
                    char_offset_end=chunk.char_offset_end,
                    metadata={
                        "chunk_id": chunk.id,
                        "source_type": st,
                        "phrasing_only": True,
                        "distance": distance,
                        "lexical": lex,
                        "language": lang,
                        "citation": {
                            "source_id": chunk.source_id,
                            "chunk_id": chunk.id,
                            "char_offset_start": chunk.char_offset_start,
                            "char_offset_end": chunk.char_offset_end,
                        },
                    },
                )
            )
            continue

        topical = _topical_score(intents, chunk.text, title)
        extras = (
            _title_boost(query, title, url, meta)
            + _chunk_quality(chunk.text, url)
            + topical
            + lang_b
        )
        score = _blend(distance, lex, PRECEDENCE.get(st, 0.4), extras=extras)
        if topical < 0 and distance > 0.28:
            continue
        hits.append(
            RetrievalHit(
                kind="chunk",
                score=score,
                text=chunk.text,
                title=title,
                source_id=chunk.source_id,
                char_offset_start=chunk.char_offset_start,
                char_offset_end=chunk.char_offset_end,
                metadata={
                    "chunk_id": chunk.id,
                    "source_type": st,
                    "distance": distance,
                    "lexical": lex,
                    "topical": topical,
                    "url": url,
                    "language": lang,
                    "citation": {
                        "source_id": chunk.source_id,
                        "chunk_id": chunk.id,
                        "char_offset_start": chunk.char_offset_start,
                        "char_offset_end": chunk.char_offset_end,
                        "url": url,
                        "title": title,
                    },
                },
            )
        )

    rp_list = []
    rp_qs = ResolutionPair.objects.filter(team=team)
    if vector is not None:
        rp_qs = (
            rp_qs.exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", vector))
            .order_by("distance")[:candidate_limit]
        )
        rp_list = list(rp_qs)
    else:
        tokens = list(_tokens(query))[:6]
        q_filter = Q()
        for tok in tokens:
            q_filter |= Q(question_text__icontains=tok) | Q(resolution_text__icontains=tok)
        rp_list = list(
            rp_qs.filter(q_filter).order_by("-quality_score")[:candidate_limit] if tokens else []
        )

    ticket_meta = _ticket_meta_for_pairs(team, rp_list)

    for pair in rp_list:
        if _pair_is_noisy(pair.question_text, pair.resolution_text):
            continue
        distance = float(getattr(pair, "distance", 0.4))
        lex = max(
            _lexical_overlap(query, pair.question_text),
            _lexical_overlap(query, pair.resolution_text),
        )
        topical = _topical_score(intents, pair.resolution_text, pair.question_text)
        if topical < 0 and distance > 0.25:
            continue
        lang = pair.language or detect_language(pair.question_text)
        extras = topical + language_match_bonus(query_lang, lang) + _recency_csat_boost(pair, ticket_meta)
        if pair.is_exemplar:
            extras += 0.06
        if pair.quality_score:
            extras += min(0.08, float(pair.quality_score) * 0.08)
        score = _blend(distance, lex, PRECEDENCE["resolution_pair"], extras=extras)
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
                    "lexical": lex,
                    "distance": distance,
                    "topical": topical,
                    "language": lang,
                    "citation": {
                        "kind": "resolution_pair",
                        "resolution_pair_id": pair.id,
                        "ticket_ids": pair.source_ticket_ids,
                    },
                },
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return _diversify(hits, limit=limit)
