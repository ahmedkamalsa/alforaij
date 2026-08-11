"""وكيل اكتشاف تطورات السوق العقاري الكويتي.

يجمع في كل تشغيل (يوميًا عبر الوكيل اليومي):
  1) **تطورات وأخبار** من مصادر إخبارية ومرجعية كويتية (RSS/Atom أو صفحات HTML)
     تُفلتر بكلمات عقارية متخصصة حتى يبقى ما يخص السوق فقط، وتُخصَّم التكرارات
     بالرابط، ثم تُحفظ في جدول market_developments (Supabase) + ملف محلي
     data/market_developments.json (ليُخدم العرض حتى عند غياب القاعدة).
  2) **منصات عقارية إضافية**: فحص وصول قائمة مرشحة من مواقع عقارية كويتية
     (قد تكون مفيدة للربط مستقبلًا) — تُسجَّل حالتها وتظهر في تبويب «التطورات».

التصميم متسامح تمامًا: فشل أي مصدر يُسجَّل في حالته ولا يكسر التشغيل، وكل مصدر
يُحاول بـ fetch_url (إعادة محاولة + gzip + كاش قصير) كبقية موصلات المشروع.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from backend.connectors.live_sources import clean_text, fetch_url

ROOT = Path(__file__).resolve().parents[2]
LOCAL_FILE = ROOT / "data" / "market_developments.json"

# ─── المصادر الإخبارية والمرجعية ──────────────────────────────────────────
# feed: رابط تغذية RSS/Atom إن وُجد، وإلا صفحة تُقرأ منها الروابط مباشرة.
# الآلية تُعلن في حالة المصدر لشفافية التشغيل كما في بقية الموصلات.
NEWS_FEEDS: list[dict[str, str]] = [
    {
        "id": "kuna",
        "name": "وكالة الأنباء الكويتية",
        "feed": "https://www.kuna.net.kw/",
        "kind": "html",
        "category": "مؤشرات رسمية",
    },
    {
        "id": "kuwaittimes",
        "name": "Kuwait Times",
        "feed": "https://kuwaittimes.com/",
        "kind": "html",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "timeskuwait",
        "name": "TimesKuwait",
        "feed": "https://timeskuwait.com/feed",
        "kind": "rss",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "arabtimes",
        "name": "Arab Times",
        "feed": "https://www.arabtimesonline.com/news/feed/",
        "kind": "html",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "alqabas",
        "name": "القبس",
        "feed": "https://alqabas.com/",
        "kind": "html",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "alanba",
        "name": "الأنباء",
        "feed": "https://www.alanba.com.kw/rss/",
        "kind": "html",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "aljarida",
        "name": "الجريدة",
        "feed": "https://www.aljarida.com/",
        "kind": "html",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "alrai",
        "name": "الراي",
        "feed": "https://www.alraimedia.com/",
        "kind": "html",
        "category": "أخبار السوق",
        "kuwait_only": True,
    },
    {
        "id": "kfh_reports",
        "name": "بيت التمويل الكويتي - تقارير عقارية",
        "feed": "https://www.kfh.com/en/home/Investor-Relations/Real-estate-Reports.html",
        "kind": "html",
        "category": "تمويل عقاري",
    },
    {
        "id": "cbk_reports",
        "name": "البنك المركزي الكويتي",
        "feed": "https://www.cbk.gov.kw/en",
        "kind": "html",
        "category": "مؤشرات رسمية",
    },
    {
        "id": "moj_deals",
        "name": "وزارة العدل - التسجيل العقاري",
        "feed": "https://www.moj.gov.kw/EN/Apps/Pages/Realestate.aspx",
        "kind": "html",
        "category": "تنظيم وقانون",
    },
]

# ─── منصات عقارية كويتية إضافية (مرشحة للربط مستقبلًا) ────────────────────
# فحص الوصول فقط: تُسجَّل الحالة وتظهر «المواقع الأخرى المفيدة» في تبويب التطورات.
CANDIDATE_PORTALS: list[dict[str, str]] = [
    {"id": "propertyfinder_kw", "name": "Property Finder Kuwait", "url": "https://www.propertyfinder.kw/", "role": "منصة عقارية كويتية"},
    {"id": "aqarmap_kw", "name": "Aqarmap Kuwait", "url": "https://kuwait.aqarmap.com/", "role": "بوابة بحث عقاري"},
    {"id": "bayut_kw", "name": "Bayut Kuwait", "url": "https://www.bayut.kw/", "role": "بوابة إعلانات عقارية"},
    {"id": "realestate_kw_guides", "name": "بوابة الكويت العقارية (e.gov.kw)", "url": "https://e.gov.kw/sites/kgoArabic/Pages/Services/MOJ/RealEstate.aspx", "role": "مرجع حكومي"},
    {"id": "kuwait_finder", "name": "Kuwait Finder (PACI)", "url": "https://kuwaitfinder.paci.gov.kw/", "role": "مصدر مكاني رسمي"},
]

# كلمات عقارية عربية قوية: كفيلة وحدها بالتصنيف كتطور عقاري.
ARABIC_STRONG = [
    "عقار", "عقاري", "عقارية", "شقة", "شقق", "بيت", "فيلا", "فلل", "أرض", "أراضي",
    "إيجار", "تمليك", "رهن", "تمويل", "قرض", "عمارة", "استثماري", "سعر المتر",
    "متر مربع", "صفقة", "صفقات", "قسيمة", "قطعة", "تسجيل عقاري", "ملكية",
]

# كلمات إنجليزية بحدود كلمة (\b) حتى لا تطابق «land» داخل island/Thailand مثلًا.
_EN_STRONG_RE = re.compile(
    r"\b(real estate|realestate|property|apartment|villa|land|mortgage|rental|housing)\b",
    re.I,
)

# سياق كويتي صريح مطلوب للأخبار الإنجليزية حتى لا تدخل أخبار عقارات عالمية.
KUWAIT_TOKENS = ("الكويت", "كويتي", "كويت", "kuwait")


def _is_relevant(text: str, *, kuwait_only: bool = False) -> bool:
    """هل النص تطور عقاري؟

    عربي: كلمة عقارية قوية كافية (مصدر كويتي يعني سياقًا كويتيًا غالبًا).
    إنجليزي: كلمة عقارية + عند الحاجة سياق كويتي صريح (للمصادر الإخبارية).
    """
    lowered = (text or "").lower()
    arabic_hit = any(term in lowered for term in ARABIC_STRONG)
    english_hit = bool(_EN_STRONG_RE.search(lowered))
    if kuwait_only:
        return arabic_hit or (english_hit and any(token in lowered for token in KUWAIT_TOKENS))
    return arabic_hit or english_hit


def _norm_url(url: str) -> str:
    """تطبيع الرابط للتخلص من التكرار: قطع المعلمات التتبعية وشوارد الربط وحالة الأحرف."""
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/").lower()
    if path.endswith("/index") or path.endswith("/index.html"):
        path = path[: -len("/index")] if path.endswith("/index") else path[: -len("/index.html")]
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def _rss_entries(body: str, source: dict[str, str]) -> list[dict[str, Any]]:
    """استخراج عناصر RSS/Atom (title/link/pubDate/description) من نص التغذية."""
    entries: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return entries
    # RSS: <item> · Atom: <entry>
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        title = ""
        link = ""
        published = ""
        description = ""
        for child in node.iter():
            child_tag = child.tag.rsplit("}", 1)[-1]
            if child_tag == "title" and not title:
                title = clean_text(child.text or "")
            elif child_tag in ("link",):
                href = child.get("href")
                link = href or child.text or ""
            elif child_tag in ("pubDate", "published", "updated") and not published:
                published = clean_text(child.text or "")
            elif child_tag in ("description", "summary", "content") and not description:
                description = clean_text(child.text or "")
        if title and link:
            entries.append({
                "title": title,
                "url": link.strip(),
                "published": published,
                "summary": description,
            })
    return entries


def _html_entries(body: str, source: dict[str, str]) -> list[dict[str, Any]]:
    """استخراج عناوين مرتبطة بالعقار من صفحة HTML (روابط + وسوم og:title)."""
    entries: list[dict[str, Any]] = []
    page_title = ""
    for match in re.finditer(r'<title[^>]*>(.*?)</title>', body, re.I | re.S):
        page_title = clean_text(match.group(1))
        break
    for match in re.finditer(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', body, re.I | re.S):
        href = match.group(1).strip()
        label = clean_text(re.sub(r"<[^>]+>", " ", match.group(2)))
        if not label or len(label) < 8:
            continue
        # الفلترة على نص الرابط نفسه (لا صفحة العنوان) حتى لا تدخل كل روابط
        # صفحة عقارية بمجرد أن عنوانها يحمل كلمة عقارية.
        if not _is_relevant(label):
            continue
        entries.append({
            "title": label[:160],
            "url": urljoin(source["feed"], href),
            "published": "",
            "summary": "",
        })
    if page_title and _is_relevant(page_title):
        entries.append({
            "title": page_title[:160],
            "url": source["feed"],
            "published": "",
            "summary": "",
        })
    return entries


def _discover_news(max_per_source: int, max_total: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    developments: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source in NEWS_FEEDS:
        body, status, ms, error, attempts = fetch_url(source["feed"])
        if not body or error:
            statuses.append({
                "name": source["name"],
                "status": "failed",
                "records": 0,
                "note": (error or "صفحة فارغة")[:160],
                "fetchMethod": "RSS" if source["kind"] == "rss" else "HTML",
                "endpoint": source["feed"],
            })
            continue
        try:
            entries = _rss_entries(body, source) if source["kind"] == "rss" else _html_entries(body, source)
        except Exception as exc:
            entries = []
            statuses.append({
                "name": source["name"],
                "status": "failed",
                "records": 0,
                "note": f"تحليل فشل: {exc}"[:160],
                "fetchMethod": "RSS" if source["kind"] == "rss" else "HTML",
                "endpoint": source["feed"],
            })
            continue
        matched = [
            entry for entry in entries
            if _is_relevant(entry["title"], kuwait_only=source.get("kuwait_only", False))
        ]
        # ترتيب الأحدث أولًا إن وُجد تاريخ، ثم حد أقصى لكل مصدر
        matched.sort(key=lambda entry: entry.get("published") or "", reverse=True)
        kept = 0
        for entry in matched[:max_per_source]:
            key = _norm_url(entry["url"])
            if key in seen or key == _norm_url(source["feed"]):
                continue
            seen.add(key)
            published = str(entry.get("published") or "")
            developments.append({
                "url": entry["url"],
                "title": entry["title"][:220],
                "source": source["id"],
                "source_name": source["name"],
                "category": source["category"],
                "published": published[:10],
                "summary": (entry.get("summary") or "")[:300],
            })
            kept += 1
            if len(developments) >= max_total:
                break
        statuses.append({
            "name": source["name"],
            "status": "success" if kept else "no_matches",
            "records": kept,
            "note": f"{len(entries)} عنوانًا إجمالًا، {kept} عقاريًا" if entries else "لا عناوين",
            "fetchMethod": "RSS" if source["kind"] == "rss" else "HTML",
            "endpoint": source["feed"],
        })
        if len(developments) >= max_total:
            break
    return developments, statuses


def _probe_portals(timeout: int = 10) -> list[dict[str, Any]]:
    """فحص وصول منصات عقارية كويتية إضافية (مرشحة للربط مستقبلًا)."""
    results: list[dict[str, Any]] = []
    for portal in CANDIDATE_PORTALS:
        try:
            body, status, ms, error, attempts = fetch_url(portal["url"])
            reachable = bool(body) and not error
            results.append({
                "id": portal["id"],
                "name": portal["name"],
                "url": portal["url"],
                "role": portal["role"],
                "status": "متاحة" if reachable else "غير متاحة",
                "note": (error or f"HTTP {status}")[:120],
            })
        except Exception as exc:
            results.append({
                "id": portal["id"],
                "name": portal["name"],
                "url": portal["url"],
                "role": portal["role"],
                "status": "غير متاحة",
                "note": str(exc)[:120],
            })
    return results


def save_developments_local(payload: dict[str, Any]) -> dict[str, Any]:
    """حفظ نتيجة الاكتشاف كاملة محليًا (data/market_developments.json).

    تُحفظ التطورات وحالات المصادر والمنصات المرشحة معًا حتى يخدم الملف تبويب
    «التطورات» كاملًا دون قاعدة بيانات — على الخادم الحي والموقع الثابت معًا.
    """
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    count = int(payload.get("count") or len(payload.get("developments") or []))
    stored = {
        "generatedAt": payload.get("fetchedAt", ""),
        "count": count,
        "status": payload.get("status", ""),
        "note": payload.get("note", ""),
        "developments": payload.get("developments", []),
        "sources": payload.get("sources", []),
        "portals": payload.get("portals", []),
    }
    LOCAL_FILE.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "count": count, "error": ""}


def load_developments_local() -> dict[str, Any]:
    if not LOCAL_FILE.exists():
        return {"generatedAt": "", "count": 0, "developments": [], "sources": [], "portals": []}
    try:
        return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"generatedAt": "", "count": 0, "developments": [], "sources": [], "portals": []}


def discover_market_developments(
    *,
    max_per_source: int = 5,
    max_total: int = 60,
    probe_portals: bool = True,
) -> dict[str, Any]:
    """تشغيل وكيل اكتشاف التطورات: أخبار عقارية + فحص منصات إضافية.

    يعيد بنية كاملة (حالة كل مصدر + التطورات + المنصات المرشحة) تُحفظ في
    market_developments وتُعرض في تبويب «التطورات». لا يُرمى استثناء أبدًا —
    أي فشل يُسجَّل في الحالة ويبقى التشغيل ناجحًا ما دام استُخرج شيء أو فُحص.
    """
    fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    developments, news_statuses = _discover_news(max_per_source, max_total)
    portals = _probe_portals() if probe_portals else []

    status = "success" if developments else ("no_data" if not news_statuses else "partial")
    note_parts = [f"جمع {len(developments)} تطورًا"]
    if news_statuses:
        ok = sum(1 for row in news_statuses if row["status"] == "success")
        note_parts.append(f"{ok}/{len(news_statuses)} مصادر عقارية")
    if portals:
        reachable = sum(1 for row in portals if row["status"] == "متاحة")
        note_parts.append(f"{reachable}/{len(portals)} منصات مرشحة متاحة")
    return {
        "status": status,
        "fetchedAt": fetched_at,
        "count": len(developments),
        "developments": developments,
        "sources": news_statuses,
        "portals": portals,
        "note": "، ".join(note_parts),
    }
