from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.config import BOARD_HTML_PATH, SEED_LISTINGS_PATH
from backend.models import Listing
from backend.services.request_parser import extract_area_range, normalize_text

# كل الأرقام المعروضة في المنصة بالإنجليزية: تحويل الأرقام العربية الهندية (٠-٩)
# وفواصلها في نصوص الإعلانات المحلية عند التحميل — قبل الحفظ والقاعدة والتقارير.
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def _latin_text(value: Any) -> str:
    return str(value or "").translate(_AR_DIGITS)


def _payload_from_html(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'<script id="payload" type="application/json">(.*?)</script>', text, re.S)
    if not match:
        raise ValueError(f"Dashboard payload not found in {path}")
    return json.loads(match.group(1))


def load_payload() -> dict:
    if SEED_LISTINGS_PATH.exists():
        return {"records": json.loads(SEED_LISTINGS_PATH.read_text(encoding="utf-8"))}
    if BOARD_HTML_PATH.exists():
        return _payload_from_html(BOARD_HTML_PATH)
    return {"records": []}


def _safe_space(row: dict) -> float | None:
    raw_space = row.get("space")
    if raw_space in (None, ""):
        return None
    source = normalize_text(str(row.get("spaceSource") or ""))
    if "غير مذكوره" in source:
        return None
    try:
        value = float(raw_space)
    except (TypeError, ValueError):
        return None
    if "حقل المساحه" in source:
        return value

    text = "\n".join(
        str(row.get(key) or "")
        for key in ("detailText", "detailTitle", "summary", "features")
    )
    min_area, max_area, excluded = extract_area_range(text)
    # لا نقبل رقمًا ظهر كواجهة/ارتداد/عرض شارع كمساحة للعقار
    if value in excluded.values():
        return None
    if min_area == value or max_area == value:
        return value
    return None


def load_listings() -> list[Listing]:
    payload = load_payload()
    listings: list[Listing] = []
    for row in payload.get("records", []):
        listings.append(
            Listing(
                code=str(row.get("code") or ""),
                transaction=str(row.get("transaction") or ""),
                governorate=str(row.get("governorate") or ""),
                area=str(row.get("area") or ""),
                property_type=str(row.get("property_type") or ""),
                detail_class=str(row.get("detail_class") or ""),
                price=float(row["price"]) if row.get("price") not in (None, "") else None,
                price_text=_latin_text(row.get("priceText")),
                space=_safe_space(row),
                listing_mode=str(row.get("listingMode") or ""),
                summary=_latin_text(row.get("summary")),
                features=_latin_text(row.get("features")),
                published_date=str(row.get("publishedDate") or ""),
                original_url=str(row.get("originalUrl") or ""),
                raw=row,
            )
        )
    return listings
