from __future__ import annotations

from typing import Any, TypedDict


class SourceStatus(TypedDict):
    name: str
    status: str
    records: int
    note: str


class AnalysisReport(TypedDict):
    request: dict[str, Any]
    sourceStatus: list[SourceStatus]
    summary: str
    results: list[dict[str, Any]]
    limitations: list[str]
