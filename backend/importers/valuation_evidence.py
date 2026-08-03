from __future__ import annotations


def normalize_evidence_row(row: dict) -> dict:
    return {
        "code": row.get("code"),
        "source": row.get("source"),
        "area": row.get("area"),
        "price": row.get("price"),
        "space": row.get("space"),
        "url": row.get("url"),
    }
