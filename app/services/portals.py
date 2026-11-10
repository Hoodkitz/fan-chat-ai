"""Portal adapters. Only official interfaces: import of exported chats and sending via
an official API where one exists. 'manual' hands the approved text back for copy & paste."""
from __future__ import annotations

from typing import Protocol


class PortalAdapter(Protocol):
    name: str

    def send(self, portal_user_id: str, text: str) -> dict: ...


class ManualAdapter:
    name = "manual"

    def send(self, portal_user_id: str, text: str) -> dict:
        return {"delivered": False, "mode": "manual", "copy_text": text}


class RecordingAdapter:
    """Test double that records sent messages."""
    name = "recording"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, portal_user_id: str, text: str) -> dict:
        self.sent.append((portal_user_id, text))
        return {"delivered": True, "mode": "api"}


ADAPTERS: dict[str, PortalAdapter] = {"manual": ManualAdapter()}


def adapter_for(portal: str) -> PortalAdapter:
    return ADAPTERS.get(portal, ADAPTERS["manual"])
