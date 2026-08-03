from __future__ import annotations


def normalize_transaction_row(row: dict) -> dict:
    return {
        "source": "official_transactions",
        "area": row.get("area") or row.get("المنطقة"),
        "property_type": row.get("property_type") or row.get("نوع العقار"),
        "price": row.get("price") or row.get("السعر"),
        "space": row.get("space") or row.get("المساحة"),
        "date": row.get("date") or row.get("التاريخ"),
    }
