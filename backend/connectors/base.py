from __future__ import annotations

from typing import Protocol

from backend.models import Listing, PropertyRequest


class PropertyConnector(Protocol):
    id: str
    name: str

    def search(self, request: PropertyRequest) -> list[Listing]:
        ...
