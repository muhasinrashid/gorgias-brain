from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class TicketPayload:
    external_id: str
    subject: str
    status: str
    channel: str
    customer_email: str
    customer_external_id: str
    created_at: datetime | None
    closed_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TicketPage:
    tickets: list[TicketPayload]
    next_cursor: str | None


@dataclass
class NoteResult:
    external_id: str
    ok: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilitySet:
    can_list_tickets: bool = False
    can_fetch_messages: bool = False
    can_create_internal_note: bool = False
    can_add_tag: bool = False
    details: dict[str, Any] = field(default_factory=dict)


class HelpdeskAdapter(Protocol):
    def fetch_ticket(self, external_id: str) -> TicketPayload | None: ...

    def list_tickets(self, since: datetime | None, cursor: str | None) -> TicketPage: ...

    def create_internal_note(self, ticket_id: str, body: str) -> NoteResult: ...

    def add_tag(self, ticket_id: str, tag: str) -> bool: ...

    def probe_capabilities(self) -> CapabilitySet: ...
