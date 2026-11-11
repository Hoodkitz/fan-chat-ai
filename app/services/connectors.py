"""Portal connectors: pull new fan messages from a portal's OFFICIAL API (or an export feed)
and hand them to the idempotent inbox. No scraping, no credential replay against portal UIs.

A connector returns normalised events; the inbox (UNIQUE event_id) makes repeated polls harmless.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.services.guardrails import input_violations
from app.services.pii import redact


@dataclass
class PortalEvent:
    portal: str
    event_id: str
    portal_user_id: str
    text: str
    nickname: str | None = None
    sent_at: datetime | None = None


class PortalConnector(Protocol):
    kind: str

    def poll(self, config: dict, cursor: str | None) -> tuple[list[PortalEvent], str | None]:
        """Return (new events, next cursor). Must only use documented portal APIs."""
        ...


@dataclass
class FakeConnector:
    """Test/dev double: serves queued events in order, cursor = index."""
    kind = "fake"
    queue: list[PortalEvent] = field(default_factory=list)

    def poll(self, config: dict, cursor: str | None) -> tuple[list[PortalEvent], str | None]:
        start = int(cursor or 0)
        events = self.queue[start:]
        return events, str(start + len(events))


class ExportFileConnector:
    """Reads a JSON export the creator downloaded from a portal (official data export). The file path
    is configured per tenant; every line/entry needs an id so re-reads are idempotent."""
    kind = "export_file"

    def poll(self, config: dict, cursor: str | None) -> tuple[list[PortalEvent], str | None]:
        path = config.get("path")
        if not path:
            return [], cursor
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        events = []
        for i, item in enumerate(data if isinstance(data, list) else data.get("messages", [])):
            eid = str(item.get("id") or f"{path}:{i}")
            if cursor and eid <= cursor and item.get("id") is None:
                continue
            events.append(PortalEvent(portal=config.get("portal", "export"), event_id=eid,
                                      portal_user_id=str(item.get("user_id") or item.get("from") or "unknown"),
                                      nickname=item.get("nickname"), text=str(item.get("text") or ""),
                                      sent_at=datetime.fromisoformat(item["sent_at"]) if item.get("sent_at") else None))
        return [e for e in events if e.text.strip()], cursor


CONNECTORS: dict[str, PortalConnector] = {"export_file": ExportFileConnector()}


def register_connector(c: PortalConnector) -> None:
    CONNECTORS[c.kind] = c


def connector_for(kind: str) -> PortalConnector | None:
    return CONNECTORS.get(kind)


def sanitize_event(ev: PortalEvent) -> PortalEvent:
    """Keep raw text for the creator, but never let an instruction-like nickname through unmarked."""
    nick = (ev.nickname or "")[:120]
    if input_violations(nick):
        nick = redact(nick)[0][:40] + " ⚠"
    return PortalEvent(ev.portal, ev.event_id[:200], ev.portal_user_id[:200], ev.text[:5000], nick or None, ev.sent_at)
