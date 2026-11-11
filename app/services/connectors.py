"""Portal connectors: pull new fan messages from a portal's OFFICIAL API (or an export feed)
and hand them to the idempotent inbox. No scraping, no credential replay against portal UIs.

A connector returns normalised events; the inbox (UNIQUE event_id) makes repeated polls harmless.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.services.guardrails import input_violations
from app.services.pii import redact

log = logging.getLogger("fanchat.connectors")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def export_path(tenant_id, name: str) -> Path:
    """Path of a tenant's uploaded export. Only a plain file name is accepted; the result must stay
    inside the tenant's own directory (no '..', no absolute paths, no symlinks)."""
    if not SAFE_NAME.match(name or ""):
        raise ValueError("invalid export name")
    base = (Path(settings.EXPORT_DIR) / str(tenant_id)).resolve()
    target = (base / f"{name}.json").resolve()
    if target.parent != base or target.is_symlink():
        raise ValueError("invalid export path")
    return target


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
    """Reads a JSON export the creator uploaded (official portal data export, see PUT /connectors/{name}/export).
    The file is addressed by the connector name inside the tenant's export directory; entries need an id so
    re-reads are idempotent."""
    kind = "export_file"

    def poll(self, config: dict, cursor: str | None) -> tuple[list[PortalEvent], str | None]:
        path = export_path(config.get("_tenant_id"), config.get("_name", ""))
        if not path.exists():
            return [], cursor
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        events = []
        for i, item in enumerate(data if isinstance(data, list) else data.get("messages", [])):
            eid = str(item.get("id") or f"{path}:{i}")
            events.append(PortalEvent(portal=config.get("_portal", "export"), event_id=eid,
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
