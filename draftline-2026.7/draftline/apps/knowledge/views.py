from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.knowledge.models import CuratedKnowledge, CuratedStatus, Source, SourceType
from apps.knowledge.services.deidentify import deidentify_text, still_contains_pii
from apps.knowledge.services.embeddings import EMBEDDER_VERSION, embed_texts, embedder_ready
from apps.knowledge.services.ingest import ingest_gorgias_sources
from apps.knowledge.services.language import detect_language
from apps.teams.decorators import login_and_team_required, team_admin_required
from apps.tickets.models import Qualification, Ticket


@login_and_team_required
def sources_home(request, team_slug):
    team = request.team
    counts = {
        "macros": Source.objects.filter(team=team, source_type=SourceType.MACRO, is_active=True).count(),
        "articles": Source.objects.filter(
            team=team, source_type=SourceType.HELP_CENTER_ARTICLE, is_active=True
        ).count(),
        "web_pages": Source.objects.filter(team=team, source_type=SourceType.WEB_PAGE, is_active=True).count(),
        "tickets": Ticket.objects.filter(team=team).count(),
        "support_tickets": Ticket.objects.filter(team=team, qualification=Qualification.SUPPORT).count(),
    }
    return render(
        request,
        "knowledge/sources_home.html",
        {"counts": counts, "active_tab": "sources", "page_title": "Sources"},
    )


@login_and_team_required
def sources_list(request, team_slug, source_type):
    team = request.team
    type_map = {
        "macros": SourceType.MACRO,
        "help-center": SourceType.HELP_CENTER_ARTICLE,
        "web": SourceType.WEB_PAGE,
    }
    st = type_map.get(source_type)
    if not st:
        return redirect(reverse("knowledge:sources_home", args=[team_slug]))
    q = (request.GET.get("q") or "").strip()
    qs = Source.objects.filter(team=team, source_type=st).order_by("-usage_count", "title")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(normalised_content__icontains=q))
    return render(
        request,
        "knowledge/sources_list.html",
        {
            "sources": qs[:200],
            "source_type": source_type,
            "q": q,
            "active_tab": "sources",
            "page_title": source_type.replace("-", " ").title(),
        },
    )


@login_and_team_required
def source_detail(request, team_slug, source_id):
    from apps.knowledge.services.citations import resolve_chunk_citation

    source = get_object_or_404(Source, pk=source_id, team=request.team)
    chunks = list(source.chunks.order_by("ordinal")[:50])
    citations = []
    for chunk in chunks:
        resolved = resolve_chunk_citation(chunk)
        citations.append(
            {
                "chunk": chunk,
                "resolves": resolved.ok,
                "message": resolved.message,
            }
        )
    return render(
        request,
        "knowledge/source_detail.html",
        {
            "source": source,
            "citations": citations,
            "active_tab": "sources",
            "page_title": source.title,
        },
    )


@login_and_team_required
def tickets_browser(request, team_slug):
    team = request.team
    q = (request.GET.get("q") or "").strip()
    qualification = (request.GET.get("qualification") or "").strip()
    qs = Ticket.objects.filter(team=team).order_by("-created_at_external", "-id")
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(external_id__icontains=q) | Q(customer_email__icontains=q))
    if qualification:
        qs = qs.filter(qualification=qualification)
    breakdown = list(
        Ticket.objects.filter(team=team)
        .values("qualification")
        .annotate(c=Count("id"))
        .order_by("-c")
        .values_list("qualification", "c")
    )
    return render(
        request,
        "knowledge/tickets_browser.html",
        {
            "tickets": qs[:100],
            "q": q,
            "qualification": qualification,
            "qualifications": Qualification.choices,
            "breakdown": breakdown,
            "active_tab": "sources",
            "page_title": "Tickets",
        },
    )


@login_and_team_required
def ticket_detail(request, team_slug, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id, team=request.team)
    messages = ticket.messages.order_by("sequence", "sent_at", "id")
    return render(
        request,
        "knowledge/ticket_detail.html",
        {"ticket": ticket, "messages": messages, "active_tab": "sources", "page_title": ticket.subject},
    )


@team_admin_required
@require_POST
def sync_sources(request, team_slug, connection_id):
    from apps.integrations.models import Connection

    connection = get_object_or_404(Connection, pk=connection_id, team=request.team)
    ingest_gorgias_sources.delay(request.team.id, connection.id)
    return redirect(reverse("integrations:detail", args=[team_slug, connection.id]))


@login_and_team_required
def corpus_report(request, team_slug):
    from apps.tickets.services.corpus_report import build_corpus_report

    report = build_corpus_report(request.team)
    return render(
        request,
        "knowledge/corpus_report.html",
        {"report": report, "active_tab": "corpus_report", "page_title": "Corpus Report"},
    )


@login_and_team_required
def curated_list(request, team_slug):
    status = (request.GET.get("status") or "").strip()
    qs = CuratedKnowledge.objects.filter(team=request.team).order_by("-updated_at")
    if status in {c.value for c in CuratedStatus}:
        qs = qs.filter(status=status)
    return render(
        request,
        "knowledge/curated_list.html",
        {
            "items": qs[:200],
            "status": status,
            "statuses": CuratedStatus.choices,
            "active_tab": "curated",
            "page_title": "Curated knowledge",
        },
    )


@team_admin_required
def curated_create(request, team_slug):
    context = {
        "active_tab": "curated",
        "page_title": "Add curated knowledge",
        "question": "",
        "answer": "",
        "intent": "",
        "language": "en",
        "item": None,
        "form_action": reverse("knowledge:curated_create", args=[team_slug]),
    }
    if request.method == "POST":
        question = (request.POST.get("question") or "").strip()
        answer = (request.POST.get("answer") or "").strip()
        intent = (request.POST.get("intent") or "").strip()
        language = (request.POST.get("language") or "en").strip()[:16]
        context.update({"question": question, "answer": answer, "intent": intent, "language": language})
        if not question or not answer:
            messages.error(request, "Question and answer are required.")
            return render(request, "knowledge/curated_form.html", context)
        scrubbed = deidentify_text(answer)
        item = CuratedKnowledge.objects.create(
            team=request.team,
            question=question,
            answer=scrubbed,
            intent=intent[:128],
            language=language or detect_language(question),
            status=CuratedStatus.DRAFT,
            is_deidentified=not still_contains_pii(scrubbed),
        )
        messages.success(request, "Draft curated knowledge saved.")
        return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))
    return render(request, "knowledge/curated_form.html", context)


@team_admin_required
def curated_edit(request, team_slug, curated_id):
    item = get_object_or_404(CuratedKnowledge, pk=curated_id, team=request.team)
    if item.status == CuratedStatus.RETIRED:
        messages.error(request, "Retired items cannot be edited.")
        return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))
    context = {
        "active_tab": "curated",
        "page_title": "Edit curated knowledge",
        "question": item.question,
        "answer": item.answer,
        "intent": item.intent,
        "language": item.language or "en",
        "item": item,
        "form_action": reverse("knowledge:curated_edit", args=[team_slug, item.id]),
    }
    if request.method == "POST":
        question = (request.POST.get("question") or "").strip()
        answer = (request.POST.get("answer") or "").strip()
        intent = (request.POST.get("intent") or "").strip()
        language = (request.POST.get("language") or "en").strip()[:16]
        context.update({"question": question, "answer": answer, "intent": intent, "language": language})
        if not question or not answer:
            messages.error(request, "Question and answer are required.")
            return render(request, "knowledge/curated_form.html", context)
        scrubbed_q = deidentify_text(question)
        scrubbed_a = deidentify_text(answer)
        item.question = scrubbed_q
        item.answer = scrubbed_a
        item.intent = intent[:128]
        item.language = language or detect_language(question)
        item.is_deidentified = not still_contains_pii(scrubbed_a + "\n" + scrubbed_q)
        if item.status == CuratedStatus.APPROVED:
            # Edits drop back to draft so de-id / re-approve is explicit
            item.status = CuratedStatus.DRAFT
            item.approved_by = None
            item.approved_at = None
            item.embedding = None
            item.embedder_version = ""
        item.save()
        messages.success(request, "Curated knowledge updated.")
        return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))
    return render(request, "knowledge/curated_form.html", context)


@login_and_team_required
def curated_detail(request, team_slug, curated_id):
    item = get_object_or_404(CuratedKnowledge, pk=curated_id, team=request.team)
    pii = still_contains_pii(item.answer)
    return render(
        request,
        "knowledge/curated_detail.html",
        {
            "item": item,
            "pii_issues": pii,
            "active_tab": "curated",
            "page_title": (item.question or "")[:60],
        },
    )


@team_admin_required
@require_POST
def curated_deidentify(request, team_slug, curated_id):
    item = get_object_or_404(CuratedKnowledge, pk=curated_id, team=request.team)
    item.answer = deidentify_text(item.answer)
    item.question = deidentify_text(item.question)
    item.is_deidentified = not still_contains_pii(item.answer + "\n" + item.question)
    item.save(update_fields=["answer", "question", "is_deidentified", "updated_at"])
    if item.is_deidentified:
        messages.success(request, "De-identified. Ready to approve.")
    else:
        messages.warning(request, "Still looks like it may contain personal data — review before approving.")
    return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))


def _embed_curated_item(item: CuratedKnowledge) -> None:
    if not embedder_ready():
        return
    try:
        vectors = embed_texts([f"{item.question}\n\n{item.answer}"])
    except Exception:
        return
    if not vectors:
        return
    item.embedding = vectors[0]
    item.embedder_version = EMBEDDER_VERSION
    item.save(update_fields=["embedding", "embedder_version", "updated_at"])


@team_admin_required
@require_POST
def curated_approve(request, team_slug, curated_id):
    item = get_object_or_404(CuratedKnowledge, pk=curated_id, team=request.team)
    if item.status == CuratedStatus.RETIRED:
        messages.error(request, "Retired items cannot be approved.")
        return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))
    issues = still_contains_pii(item.answer + "\n" + item.question)
    if issues or not item.is_deidentified:
        messages.error(request, "De-identify and clear personal data before approving.")
        return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))
    item.status = CuratedStatus.APPROVED
    item.approved_by = request.user
    item.approved_at = timezone.now()
    item.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _embed_curated_item(item)
    messages.success(request, "Approved — available to retrieval.")
    return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))


@team_admin_required
@require_POST
def curated_retire(request, team_slug, curated_id):
    item = get_object_or_404(CuratedKnowledge, pk=curated_id, team=request.team)
    item.status = CuratedStatus.RETIRED
    item.save(update_fields=["status", "updated_at"])
    messages.info(request, "Retired.")
    return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))


@team_admin_required
@require_POST
def curated_from_pair(request, team_slug, pair_id):
    from apps.knowledge.models import ResolutionPair

    pair = get_object_or_404(ResolutionPair, pk=pair_id, team=request.team)
    answer = deidentify_text(pair.resolution_text)
    question = deidentify_text(pair.question_text)
    item = CuratedKnowledge.objects.create(
        team=request.team,
        question=question,
        answer=answer,
        intent=pair.intent,
        language=pair.language or detect_language(pair.question_text) or "en",
        status=CuratedStatus.DRAFT,
        source_ticket_ids=list(pair.source_ticket_ids or []),
        is_deidentified=not still_contains_pii(answer + "\n" + question),
        created_from_delta=f"resolution_pair:{pair.id}",
    )
    messages.success(request, "Created curated draft from past resolution.")
    return redirect(reverse("knowledge:curated_detail", args=[team_slug, item.id]))
