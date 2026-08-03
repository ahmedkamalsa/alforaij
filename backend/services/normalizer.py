from __future__ import annotations

from backend.services.request_parser import normalize_text


def normalize_area_name(value: str) -> str:
    normalized = normalize_text(value)
    return normalized.replace("مدينه ", "").strip()
