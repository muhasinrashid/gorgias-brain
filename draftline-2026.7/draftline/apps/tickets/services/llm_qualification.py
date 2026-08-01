"""LLM stage for ticket qualification (precision-first).

Used after rules when the ticket would otherwise be UNCLEAR (or when
backend=llm). Low-confidence answers are forced to UNCLEAR.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.conf import settings

from apps.tickets.models import Qualification
from apps.tickets.services.qualification import QualificationResult

logger = logging.getLogger(__name__)

LLM_QUALIFIER_VERSION = "llm-v1"

ALLOWED = {c.value for c in Qualification}

SYSTEM_PROMPT = """You classify helpdesk tickets for a watch brand support inbox.
Return ONLY valid JSON with keys:
  qualification: one of SUPPORT, SPAM_PHISHING, MARKETING_INBOUND, SYSTEM_NOTIFICATION,
                 SOCIAL_NOTIFICATION, VENDOR_PITCH, INTERNAL, UNCLEAR
  confidence: number from 0 to 1
  reason: short English explanation

Rules:
- SUPPORT = a real customer needing help with product, order, shipping, repair, warranty, returns, availability.
- SOCIAL_NOTIFICATION = Instagram/Facebook story mentions, tags, platform noise — not a customer asking for help.
- SYSTEM_NOTIFICATION = out-of-stock alerts, inventory warnings, OOO/auto-replies, payment platform receipts, tracking bots.
- VENDOR_PITCH = agencies, manufacturers, SEO, ambassadors, software sales pitching the brand.
- MARKETING_INBOUND = newsletters / promo blasts into the inbox.
- SPAM_PHISHING = scams, fake ad-account threats, credential phishing.
- INTERNAL = tests or internal-only threads.
- UNCLEAR = not enough signal — prefer UNCLEAR over SUPPORT when unsure.
- Optimise for precision on SUPPORT: false SUPPORT is worse than false UNCLEAR.
"""


def _truncate(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[truncated]"


def _parse_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _client_and_model():
    """Prefer Azure OpenAI (Formex POC keys); fall back to OpenAI."""
    azure_key = getattr(settings, "AZURE_OPENAI_API_KEY", "") or ""
    azure_endpoint = getattr(settings, "AZURE_OPENAI_ENDPOINT", "") or ""
    azure_deployment = getattr(settings, "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "") or ""
    api_version = getattr(settings, "AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    if azure_key and azure_endpoint and azure_deployment:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=azure_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint.rstrip("/") + "/",
        )
        return client, azure_deployment, "azure"

    openai_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if openai_key and "***" not in openai_key:
        from openai import OpenAI

        return OpenAI(api_key=openai_key), "gpt-4o-mini", "openai"

    raise RuntimeError(
        "No LLM credentials configured. Set AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT + "
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME, or OPENAI_API_KEY, in draftline/.env"
    )


def llm_qualify_ticket(
    *,
    subject: str,
    channel: str = "",
    customer_email: str = "",
    first_inbound_text: str = "",
    confidence_min: float | None = None,
) -> QualificationResult:
    confidence_min = (
        confidence_min
        if confidence_min is not None
        else float(getattr(settings, "QUALIFIER_LLM_CONFIDENCE_MIN", 0.8))
    )

    user_prompt = (
        f"channel: {channel or 'unknown'}\n"
        f"customer_email: {customer_email or 'unknown'}\n"
        f"subject: {subject or ''}\n"
        f"first_inbound_message:\n{_truncate(first_inbound_text)}\n"
    )

    client, model, provider = _client_and_model()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = _parse_response(content)
    except json.JSONDecodeError:
        logger.warning("LLM qualifier returned non-JSON: %s", content[:200])
        return QualificationResult(Qualification.UNCLEAR, 0.0, "llm-parse-error", LLM_QUALIFIER_VERSION)

    label = str(data.get("qualification", "UNCLEAR")).upper().strip()
    if label not in ALLOWED:
        label = Qualification.UNCLEAR
    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(data.get("reason", ""))[:300]

    if confidence < confidence_min:
        return QualificationResult(
            Qualification.UNCLEAR,
            confidence,
            f"llm-below-threshold({confidence:.2f}<{confidence_min}):{reason}",
            LLM_QUALIFIER_VERSION,
        )

    # Extra guard: never accept SUPPORT below a slightly higher bar
    support_min = float(getattr(settings, "QUALIFIER_LLM_SUPPORT_CONFIDENCE_MIN", 0.85))
    if label == Qualification.SUPPORT and confidence < support_min:
        return QualificationResult(
            Qualification.UNCLEAR,
            confidence,
            f"llm-support-below-threshold({confidence:.2f}<{support_min}):{reason}",
            LLM_QUALIFIER_VERSION,
        )

    return QualificationResult(label, confidence, f"llm:{provider}:{reason}", LLM_QUALIFIER_VERSION)
