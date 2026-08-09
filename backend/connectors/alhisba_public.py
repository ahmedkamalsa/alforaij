from __future__ import annotations

import gzip
import html
import re
import time
import urllib.request
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
HOME_URL = "https://alhisba.com/"
_CACHE: tuple[float, list[dict[str, Any]], dict[str, Any]] | None = None
_TTL = 900


def _clean(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.S)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _number(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = (
        value.replace(",", "")
        .replace("٫", ".")
        .replace("م2", "")
        .replace("م²", "")
        .replace("د.ك", "")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_home(timeout: int = 14) -> tuple[str, int, float, str | None]:
    started = time.perf_counter()
    req = urllib.request.Request(
        HOME_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ar,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            body = raw.decode("utf-8", errors="replace")
            return body, getattr(resp, "status", 200), round((time.perf_counter() - started) * 1000, 1), None
    except Exception as exc:
        return "", 0, round((time.perf_counter() - started) * 1000, 1), str(exc)


def _extract_after(label: str, text: str, pattern: str = r"(.+?)") -> str:
    match = re.search(label + r"\s*" + pattern + r"\s+(?:فئة|وصف|قطعة|المساحة|سعر|نسبة|منطقة|مدقّ|كما ورد|تصفّح|$)", text)
    return match.group(1).strip() if match else ""


def _deal_from_block(block: str, href: str, index: int) -> dict[str, Any] | None:
    text = _clean(block)
    area = _extract_after("منطقة", text, r"(.+?)")
    property_type = _extract_after("وصف", text, r"(.+?)") or "عقارات"
    category = _extract_after("فئة", text, r"(.+?)")
    space_match = re.search(r"المساحة\s*م2\s*([0-9.,]+)", text)
    price_match = re.search(r"سعر\s*د\.ك\s*([0-9.,]+)", text)
    rate_match = re.search(r"سعر\s*المتر\s*المربع\s*([0-9.,]+)", text)
    date_match = re.search(r"(20[0-9]{2}-[0-9]{2}-[0-9]{2})", text)
    space = _number(space_match.group(1) if space_match else None)
    price = _number(price_match.group(1) if price_match else None)
    if not area or not price or not space:
        return None
    url = "https://alhisba.com" + html.unescape(href)
    official_wording = "كما ورد في المصدر الرسمي" if "كما ورد في المصدر الرسمي" in text else "مدقق من الحسبة" if "مدق" in text else "من الصفحة العامة"
    return {
        "reference": f"ALHISBA-{index}-{area}-{space}-{price}",
        "area": area,
        "property_type": property_type,
        "category": category,
        "price": price,
        "space": space,
        "date": date_match.group(1) if date_match else "",
        "price_per_sqm": _number(rate_match.group(1) if rate_match else None),
        "transaction_type": "للبيع",
        "source": "الحسبة - الصفقات المسجلة العامة",
        "source_note": official_wording,
        "original_url": url,
    }


def fetch_public_deals(force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _CACHE
    now = time.time()
    if not force and _CACHE and now - _CACHE[0] < _TTL:
        return _CACHE[1], _CACHE[2]
    body, status, ms, error = _fetch_home()
    rows: list[dict[str, Any]] = []
    if body:
        for index, match in enumerate(re.finditer(r'href="(/ads/for-sale\?area=[^"]+)"', body), start=1):
            block = body[max(0, match.start() - 2600):match.start() + 400]
            row = _deal_from_block(block, match.group(1), index)
            if row:
                rows.append(row)
    meta = {
        "name": "الحسبة - الصفقات المسجلة العامة",
        "status": "success" if rows else ("failed" if error else "no_results"),
        "records": len(rows),
        "responseMs": ms,
        "url": HOME_URL,
        "note": error or "تم استخراج آخر الصفقات الظاهرة في الصفحة العامة للحسبة كمرجع سوقي موثق برابط المصدر.",
    }
    _CACHE = (now, rows, meta)
    return rows, meta
