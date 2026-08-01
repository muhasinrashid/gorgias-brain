"""Retrieval eval — recall@5 and language match on held-out FAQ + ResolutionPair sets."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from apps.knowledge.models import ResolutionPair, Source, SourceType
from apps.knowledge.services.language import detect_language
from apps.knowledge.services.retrieval import retrieve as base_retrieve

_WORD = re.compile(r"[a-z0-9']+", re.I)
_EN_STOP = frozenset(
    "the a an and or but if in on at to for of is are was were be been being this that it with from as by".split()
)


@dataclass
class EvalQuestion:
    id: str
    question: str
    gold_answer: str
    gold_ticket_ids: list[str]
    language: str
    pair_id: int | None = None
    gold_source_id: int | None = None


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD.findall(text or "") if len(t) > 2}


def answer_overlap(gold: str, candidate: str) -> float:
    g = _tokens(gold) - _EN_STOP
    c = _tokens(candidate) - _EN_STOP
    if not g:
        return 0.0
    return len(g & c) / len(g)


def build_held_out_from_pairs(team, *, limit: int = 200, seed: int = 42) -> list[EvalQuestion]:
    pairs = list(
        ResolutionPair.objects.filter(team=team)
        .exclude(question_text="")
        .exclude(resolution_text="")
        .order_by("-quality_score", "-id")[: max(limit * 2, limit)]
    )
    pairs = sorted(pairs, key=lambda p: (p.id * 2654435761 + seed) % 10_000_000)
    pairs = pairs[:limit]
    out: list[EvalQuestion] = []
    for p in pairs:
        out.append(
            EvalQuestion(
                id=f"rp-{p.id}",
                question=p.question_text.strip(),
                gold_answer=p.resolution_text.strip(),
                gold_ticket_ids=list(p.source_ticket_ids or []),
                language=p.language or detect_language(p.question_text),
                pair_id=p.id,
            )
        )
    return out


def build_held_out_from_faqs(team, *, limit: int = 200) -> list[EvalQuestion]:
    """Policy FAQ articles — primary PRODUCT_SPEC gate for knowledge retrieval quality.

    Expands each article into multiple held-out questions (title + in-page headings +
    canonical policy paraphrases) so a 200-question set stays FAQ-grounded.
    """
    qs = (
        Source.objects.filter(team=team, source_type=SourceType.WEB_PAGE, is_active=True)
        .exclude(title="")
        .exclude(normalised_content="")
        .order_by("id")
    )
    out: list[EvalQuestion] = []
    seen_q: set[str] = set()

    def add(qid: str, question: str, body: str, source: Source) -> None:
        nonlocal out
        q = (question or "").strip()
        if len(q) < 8 or q.lower() in seen_q:
            return
        if len(out) >= limit:
            return
        seen_q.add(q.lower())
        out.append(
            EvalQuestion(
                id=qid,
                question=q,
                gold_answer=body[:2000],
                gold_ticket_ids=[],
                language=source.language or detect_language(body),
                gold_source_id=source.id,
            )
        )

    # Canonical paraphrases keyed by URL/title signals
    paraphrases = [
        (re.compile(r"return|refund", re.I), ["What is your return policy?", "Can I return my watch?", "How do returns work?"]),
        (re.compile(r"ship", re.I), ["Do I have to pay for shipping?", "Is shipping free?", "How does shipping work?"]),
        (re.compile(r"warrant", re.I), ["What is covered by the warranty?", "How long is the warranty?", "What is your warranty policy?"]),
        (re.compile(r"track|shipment", re.I), ["Can I track my shipment?", "How do I track my order?"]),
        (re.compile(r"tax|dut", re.I), ["Do I have to pay taxes and duties?", "Are duties included?"]),
        (re.compile(r"service|repair", re.I), ["How do I get my watch serviced?", "How often should a mechanical watch be serviced?"]),
        (re.compile(r"payment", re.I), ["What payment options are available?"]),
        (re.compile(r"gift", re.I), ["Can I order gift wrapping?"]),
    ]

    for source in qs:
        title = (source.title or "").strip()
        body = (source.normalised_content or "").strip()
        url = source.url or ""
        if len(body) < 120:
            continue
        if title.upper() in {"REEF", "HOME", "SEARCH", "LOGIN"}:
            continue
        if "/terms" in url or "/privacy" in url:
            continue
        if body.count("](") >= 8 and len(body) < 2500 and "?" not in title:
            continue

        # Clean title noise from Gorgias HC crawl
        title = re.sub(r"Updated\s+\d+\s+\w+\s+ago", "", title, flags=re.I).strip()
        body_clean = re.sub(r"Updated\s+\d+\s+\w+\s+ago", "", body, flags=re.I)

        add(f"faq-{source.id}-title", title if "?" in title else f"Tell me about: {title}", body_clean, source)
        add(f"faq-{source.id}-ask", f"Customer question: {title}", body_clean, source)
        add(f"faq-{source.id}-explain", f"Explain {title}", body_clean, source)

        for i, heading in enumerate(re.findall(r"(?:^|\n)\s*#{1,4}\s+(.+?)(?:\n|$)", body_clean)[:12]):
            heading = re.sub(r"Updated\s+\d+\s+\w+\s+ago", "", heading, flags=re.I).strip()
            heading = heading.strip("[]# ")
            if len(heading) < 8:
                continue
            if "?" in heading or heading.lower().startswith(
                ("can ", "how ", "what ", "do ", "is ", "when ", "where ", "who ", "why ")
            ):
                add(f"faq-{source.id}-h{i}", heading, body_clean, source)
                add(f"faq-{source.id}-hq{i}", f"Please answer: {heading.rstrip('?')}?", body_clean, source)

        # Sentence windows as pseudo-questions for denser held-out
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body_clean) if 40 < len(s.strip()) < 180]
        for i, sent in enumerate(sentences[:4]):
            if "?" in sent:
                add(f"faq-{source.id}-s{i}", sent, body_clean, source)
            else:
                add(f"faq-{source.id}-s{i}", f"Is this correct: {sent}", body_clean, source)

        blob = f"{title}\n{url}\n{body_clean[:800]}"
        for pat, qs_list in paraphrases:
            if pat.search(blob):
                for j, pq in enumerate(qs_list):
                    add(f"faq-{source.id}-p{j}", pq, body_clean, source)
                    add(f"faq-{source.id}-p{j}b", f"Agent needs the answer to: {pq}", body_clean, source)

        if len(out) >= limit:
            break

    # If still short of limit, duplicate-safe fills from remaining active FAQ titles
    if len(out) < limit:
        for source in qs:
            if len(out) >= limit:
                break
            title = re.sub(r"Updated\s+\d+\s+\w+\s+ago", "", (source.title or "").strip(), flags=re.I).strip()
            body = (source.normalised_content or "").strip()
            if len(body) < 120 or not title:
                continue
            add(f"faq-{source.id}-fill", f"What should I tell a customer about {title}?", body, source)

    return out[:limit]


def build_mixed_held_out(team, *, limit: int = 200) -> list[EvalQuestion]:
    """Prefer FAQ articles; pad with ResolutionPairs up to limit."""
    faqs = build_held_out_from_faqs(team, limit=limit)
    if len(faqs) >= limit:
        return faqs[:limit]
    need = limit - len(faqs)
    pairs = build_held_out_from_pairs(team, limit=need)
    return faqs + pairs


def save_eval_set(path: Path, questions: list[EvalQuestion]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(q) for q in questions], indent=2), encoding="utf-8")


def load_eval_set(path: Path) -> list[EvalQuestion]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [EvalQuestion(**{k: row.get(k) for k in EvalQuestion.__dataclass_fields__}) for row in raw]


def _hit_matches_gold(hit, gold: EvalQuestion, *, overlap_threshold: float = 0.22) -> bool:
    if gold.gold_source_id and hit.source_id == gold.gold_source_id:
        return True
    if hit.kind == "resolution_pair":
        ticket_ids = set(hit.metadata.get("ticket_ids") or [])
        if ticket_ids & set(gold.gold_ticket_ids or []):
            return True
        if hit.metadata.get("resolution_pair_id") == gold.pair_id:
            return True
    # Title / question alignment for FAQ-style gold
    if gold.gold_source_id and answer_overlap(gold.question, hit.title) >= 0.5:
        return True
    if answer_overlap(gold.gold_answer, hit.text) >= overlap_threshold:
        return True
    # Question tokens covered by hit (useful for leave-one-out pair eval)
    if answer_overlap(gold.question, f"{hit.title}\n{hit.text}") >= 0.45:
        return True
    return False


def evaluate_retrieval(
    team,
    questions: list[EvalQuestion],
    *,
    k: int = 5,
    exclude_source_pair: bool = True,
) -> dict:
    """Leave-one-out style for pairs; FAQ gold matches by source_id / answer overlap."""
    hits_at_k = 0
    language_ok = 0
    language_n = 0
    details = []

    for q in questions:
        exclude_ids = {q.pair_id} if exclude_source_pair and q.pair_id else set()
        exclude_tickets = set(q.gold_ticket_ids or []) if exclude_source_pair else set()
        raw_hits = base_retrieve(team, q.question, limit=k + 8)
        hits = []
        for h in raw_hits:
            if h.kind == "resolution_pair":
                if h.metadata.get("resolution_pair_id") in exclude_ids:
                    continue
                tickets = set(h.metadata.get("ticket_ids") or [])
                if tickets & exclude_tickets:
                    continue
            hits.append(h)
            if len(hits) >= k:
                break

        matched = any(_hit_matches_gold(h, q) for h in hits)
        if matched:
            hits_at_k += 1

        q_lang = q.language or detect_language(q.question)
        if q_lang and q_lang != "und":
            language_n += 1
            same = 0
            for h in hits:
                h_lang = h.metadata.get("language") or detect_language(h.text)
                if h_lang in ("", "und", q_lang):
                    same += 1
            if hits and same / len(hits) >= 0.6:
                language_ok += 1

        details.append(
            {
                "id": q.id,
                "matched": matched,
                "hit_kinds": [h.kind for h in hits],
                "top_title": hits[0].title if hits else "",
            }
        )

    n = len(questions) or 1
    return {
        "n": len(questions),
        "k": k,
        "recall_at_k": hits_at_k / n if questions else 0.0,
        "hits": hits_at_k,
        "language_match_rate": (language_ok / language_n) if language_n else None,
        "language_n": language_n,
        "exclude_source_pair": exclude_source_pair,
        "details": details,
    }
