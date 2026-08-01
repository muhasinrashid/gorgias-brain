"""Gorgias helpdesk adapter — ported from POC with documented API quirks.

See docs/EXTERNAL_API_NOTES.md.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime
from typing import Any

import httpx
from dateutil import parser as date_parser

from apps.integrations.adapters.helpdesk import (
    CapabilitySet,
    NoteResult,
    TicketPage,
    TicketPayload,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0
MAX_RETRY_DELAY = 60.0


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After") or response.headers.get("X-Gorgias-Account-Api-Call-Limit-Reset")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return date_parser.isoparse(str(value))
    except (ValueError, TypeError):
        return None


class GorgiasAdapter:
    """Read tickets + create internal notes / tags only. No customer send path."""

    def __init__(self, *, base_url: str, username: str, api_key: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.api_key = api_key
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GorgiasAdapter:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.username}:{self.api_key}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Send a request, backing off on 429/5xx (Gorgias throttles aggressively)."""
        kwargs.setdefault("headers", self._headers())
        delay = RETRY_BASE_DELAY
        for attempt in range(MAX_RETRIES + 1):
            response = self._client.request(method, path, **kwargs)
            if response.status_code not in RETRYABLE_STATUSES or attempt == MAX_RETRIES:
                return response
            wait = _retry_after_seconds(response) or delay
            logger.warning(
                "Gorgias %s %s returned %s; retrying in %.1fs (attempt %s/%s)",
                method,
                path,
                response.status_code,
                wait,
                attempt + 1,
                MAX_RETRIES,
            )
            time.sleep(min(wait, MAX_RETRY_DELAY))
            delay *= 2
        return response

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def _ticket_from_raw(self, raw: dict[str, Any]) -> TicketPayload:
        customer = raw.get("customer") or {}
        return TicketPayload(
            external_id=str(raw.get("id", "")),
            subject=raw.get("subject") or "",
            status=raw.get("status") or "",
            channel=raw.get("channel") or "",
            customer_email=(customer.get("email") or ""),
            customer_external_id=str(customer.get("id") or ""),
            created_at=_parse_dt(raw.get("created_datetime")),
            closed_at=_parse_dt(raw.get("closed_datetime") or raw.get("updated_datetime")),
            raw=raw,
        )

    def health_check(self) -> tuple[bool, str]:
        """Validate credentials with a cheap authenticated call.

        Note: ``GET /api/users/me`` returns 400 ("pk is not a valid integer") on
        current Gorgias API — do not use it. Prefer ``/api/tickets?limit=1``.
        """
        try:
            response = self._get("/api/tickets", params={"limit": 1})
            if response.status_code == 200:
                return True, ""
            return False, f"Gorgias returned HTTP {response.status_code}: {response.text[:200]}"
        except httpx.HTTPError as exc:
            return False, f"Could not reach Gorgias: {exc}"

    def fetch_ticket(self, external_id: str) -> TicketPayload | None:
        try:
            response = self._get(f"/api/tickets/{external_id}")
            if response.status_code != 200:
                return None
            return self._ticket_from_raw(response.json())
        except httpx.HTTPError:
            logger.exception("fetch_ticket failed", extra={"ticket_id": external_id})
            return None

    def list_tickets(self, since: datetime | None, cursor: str | None) -> TicketPage:
        # Gorgias often ignores status filters — over-fetch and filter client-side for closed.
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        response = self._get("/api/tickets", params=params)
        response.raise_for_status()
        body = response.json()
        data = body.get("data", body if isinstance(body, list) else [])
        tickets = [self._ticket_from_raw(item) for item in data]
        if since:
            tickets = [t for t in tickets if t.created_at and t.created_at >= since]
        meta = body.get("meta") or {}
        return TicketPage(tickets=tickets, next_cursor=meta.get("next_cursor"))

    def list_closed_tickets_page(self, cursor: str | None = None, page_limit: int = 100) -> TicketPage:
        """Fetch a page and keep only closed tickets (POC pattern)."""
        params: dict[str, Any] = {"limit": min(page_limit * 3, 100)}
        if cursor:
            params["cursor"] = cursor
        response = self._get("/api/tickets", params=params)
        response.raise_for_status()
        body = response.json()
        data = body.get("data", [])
        closed = [self._ticket_from_raw(item) for item in data if (item.get("status") or "").lower() == "closed"]
        meta = body.get("meta") or {}
        return TicketPage(tickets=closed[:page_limit], next_cursor=meta.get("next_cursor"))

    def fetch_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        response = self._get(f"/api/tickets/{ticket_id}/messages")
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body
        return body.get("data", [])

    def create_internal_note(self, ticket_id: str, body: str) -> NoteResult:
        """Create an internal note only. channel is hard-coded — do not parameterise."""
        payload = {
            "channel": "internal-note",
            "via": "api",
            "from_agent": True,
            "body_text": body,
            "sender": {"email": self.username},
        }
        response = self._client.post(
            f"/api/tickets/{ticket_id}/messages",
            json=payload,
            headers=self._headers(),
        )
        if response.status_code not in (200, 201):
            logger.error(
                "Gorgias rejected internal note status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return NoteResult(external_id="", ok=False, raw={"status": response.status_code, "body": response.text})
        data = response.json()
        return NoteResult(external_id=str(data.get("id", "")), ok=True, raw=data)

    def add_tag(self, ticket_id: str, tag: str) -> bool:
        # Minimal tag add via ticket update — verify against live API before production use.
        try:
            ticket = self.fetch_ticket(ticket_id)
            if not ticket:
                return False
            existing = list(ticket.raw.get("tags") or [])
            names = {t.get("name") if isinstance(t, dict) else str(t) for t in existing}
            if tag in names:
                return True
            response = self._client.put(
                f"/api/tickets/{ticket_id}",
                json={"tags": [{"name": tag}]},
                headers=self._headers(),
            )
            return response.status_code in (200, 201, 202)
        except httpx.HTTPError:
            logger.exception("add_tag failed", extra={"ticket_id": ticket_id})
            return False

    def probe_capabilities(self) -> CapabilitySet:
        details: dict[str, Any] = {}
        ok, err = self.health_check()
        details["auth_ok"] = ok
        if err:
            details["auth_error"] = err
        can_list = False
        can_messages = False
        if ok:
            try:
                page = self.list_tickets(since=None, cursor=None)
                can_list = True
                details["list_count"] = len(page.tickets)
                if page.tickets:
                    msgs = self.fetch_messages(page.tickets[0].external_id)
                    can_messages = True
                    details["sample_message_count"] = len(msgs)
            except httpx.HTTPError as exc:
                details["list_error"] = str(exc)
        return CapabilitySet(
            can_list_tickets=can_list,
            can_fetch_messages=can_messages,
            can_create_internal_note=ok,
            can_add_tag=ok,
            details=details,
        )

    def _paginated_list(self, path: str, *, cursor: str | None = None, limit: int = 100, **extra) -> tuple[list[dict], str | None]:
        params: dict[str, Any] = {"limit": limit, **extra}
        if cursor:
            params["cursor"] = cursor
        response = self._get(path, params=params)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body, None
        return body.get("data", []), (body.get("meta") or {}).get("next_cursor")

    def list_macros_page(self, cursor: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        return self._paginated_list("/api/macros", cursor=cursor, limit=100, order_by="usage:desc")

    def iter_macros(self, max_pages: int = 50):
        cursor = None
        for _ in range(max_pages):
            items, cursor = self.list_macros_page(cursor=cursor)
            yield from items
            if not cursor:
                break

    def _ensure_help_center_ids(self) -> list[Any]:
        """List help centers once; empty if API unavailable or none configured."""
        cached = getattr(self, "_help_center_ids", None)
        if cached is not None:
            return cached
        ids: list[Any] = []
        cursor: str | None = None
        for _ in range(50):
            try:
                items, cursor = self._paginated_list("/api/help-centers", cursor=cursor, limit=100)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (404, 405):
                    logger.warning(
                        "Help centers unavailable (GET /api/help-centers: %s)",
                        exc.response.status_code,
                    )
                    break
                raise
            except httpx.HTTPError as exc:
                logger.warning("Help centers request failed: %s", exc)
                break
            for item in items:
                hid = item.get("id")
                if hid is not None:
                    ids.append(hid)
            if not cursor:
                break
        self._help_center_ids = ids
        return ids

    @staticmethod
    def _decode_help_center_cursor(cursor: str | None) -> tuple[int, str | None]:
        if not cursor:
            return 0, None
        if ":" in cursor:
            idx_s, article_cursor = cursor.split(":", 1)
            return int(idx_s), (article_cursor or None)
        return int(cursor), None

    @staticmethod
    def _encode_help_center_cursor(center_idx: int, article_cursor: str | None) -> str:
        return f"{center_idx}:{article_cursor or ''}"

    def list_help_center_page(self, cursor: str | None = None) -> tuple[list[dict[str, Any]], str | None, str]:
        """List one page of articles across help centers (see build_prompt.md)."""
        centers = self._ensure_help_center_ids()
        if not centers:
            return [], None, ""

        center_idx, article_cursor = self._decode_help_center_cursor(cursor)
        last_path = ""

        while center_idx < len(centers):
            hc_id = centers[center_idx]
            path = f"/api/help-centers/{hc_id}/articles"
            last_path = path
            try:
                items, next_article_cursor = self._paginated_list(path, cursor=article_cursor, limit=100)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (404, 405):
                    logger.debug("Skipping help center %s (%s)", hc_id, exc.response.status_code)
                    center_idx += 1
                    article_cursor = None
                    continue
                raise
            except httpx.HTTPError as exc:
                logger.warning("Help center articles failed for %s: %s", hc_id, exc)
                center_idx += 1
                article_cursor = None
                continue

            if next_article_cursor:
                return items, self._encode_help_center_cursor(center_idx, next_article_cursor), path

            if items:
                center_idx += 1
                article_cursor = None
                if center_idx < len(centers):
                    return items, self._encode_help_center_cursor(center_idx, None), path
                return items, None, path

            center_idx += 1
            article_cursor = None

        return [], None, last_path

    def iter_help_center_articles(self, max_pages: int = 50):
        cursor = None
        pages = 0
        while pages < max_pages:
            items, cursor, path_used = self.list_help_center_page(cursor=cursor)
            pages += 1
            if not path_used and not items:
                break
            yield from items
            if not cursor:
                break


def adapter_from_connection(connection) -> GorgiasAdapter:
    creds = connection.get_credentials()
    config = connection.config or {}
    base_url = config.get("base_url") or creds.get("base_url") or ""
    username = creds.get("username") or creds.get("email") or ""
    api_key = creds.get("api_key") or ""
    if not base_url or not username or not api_key:
        raise ValueError("Gorgias connection missing base_url, username, or api_key")
    return GorgiasAdapter(base_url=base_url, username=username, api_key=api_key)


# ---------------------------------------------------------------------------
# Hard prohibition helpers — used by tests/no_customer_send
# ---------------------------------------------------------------------------

ALLOWED_MESSAGE_CHANNELS = frozenset({"internal-note"})


def build_internal_note_payload(username: str, body: str) -> dict[str, Any]:
    """Single code path for note payloads. Tests assert channel cannot be customer-facing."""
    return {
        "channel": "internal-note",
        "via": "api",
        "from_agent": True,
        "body_text": body,
        "sender": {"email": username},
    }
