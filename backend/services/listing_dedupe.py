"""كشف ودمج الإعلانات شبه المكررة بحذر (جودة البيانات) — وحدة نقية قابلة للاختبار.

الهدف: الإعلان نفسه يُعاد جلبه برمز مختلف عندما يتغيّر رابط/معرّف المنصة بين
جلسات الحصاد. توقيع التطابق (تام بعد التطبيع):

    (المصدر، المنطقة، نوع العقار، السعر، العنوان المطبع)

بوابات الدقة تمنع دمج الوحدات المتشابهة شرعيًا (مطوّر يعرض وحدات متماثلة):
- هاتف المعلن: إن وُجد لدى أكثر من إعلان في المجموعة فيجب أن يتطابق (معلن واحد).
  اختلاف الهاتف = معلنون مختلفون = وحدات مختلفة مهما تطابق النص.
- المساحة: إن وُجدت لدى أكثر من إعلان فيجب أن تتطابق.
- حد أدنى لطول العنوان المطبع حتى لا تُدمج عناوين عامة («بيت للبيع» بلا تفاصيل).

الدمج لا يحذف شيئًا: يُوسم غير النظير بـ status=duplicate و duplicate_of،
ويبقى كل التاريخ محفوظًا في قاعدة المعرفة.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# حد أدنى لطول العنوان المطبع: عناوين عامة أقصر من هذا لا تُدخَل في الكشف
MIN_TITLE_LEN = 12

_AR_TRANS = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
    }
)


def normalize_arabic(value: Any) -> str:
    """تطبيع نص عربي/لاتيني للمقارنة: توحيد الهمزات والتاء المربوطة والألف المقصورة،
    خفض الحالة، إزالة علامات الترقيم والمسافات الزائدة."""
    text = str(value or "")
    text = text.translate(_AR_TRANS)
    text = text.lower()
    # حروف عربية (ألف-ياء) + أرقام عربية/لاتينية + لاتينية — تُسقط كل علامات الترقيم
    text = re.sub(r"[^\u0621-\u064A\u0660-\u0669a-zA-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_lead(text: Any) -> str:
    """مقدمة نص الإعلان (أول جملة) — «العنوان» الفعلي للمقارنة.

    نصوص المنصات تحمل ذيل علامات إنجليزية مكررة («Abu Halifa Abu Halifa …»)
    قد يتغير بين الجلب؛ الجملة الأولى هي الثابت الذي يميّز الإعلان.
    """
    raw = str(text or "")
    for separator in ("\n", "\r", ". "):
        if separator in raw:
            raw = raw.split(separator, 1)[0]
    return normalize_arabic(raw)


def price_key(value: Any) -> float:
    """مفتاح السعر: عدد عائم مقرّب لمنزلتين (960000.0 = 960000)."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return float("nan")


def phone_key(value: Any) -> str:
    """مفتاح هاتف المعلن: أرقام فقط (96551112233 = +965 5111 2233)."""
    return re.sub(r"\D", "", str(value or ""))


def space_key(value: Any) -> int | None:
    """مفتاح المساحة: عدد صحيح، أو None عند غيابها/عدم صلاحيتها."""
    try:
        num = int(float(value))
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def title_key(row: dict[str, Any]) -> str:
    """عنوان الإعلان المطبع: مقدمة summary أو features (الأطول والأكثر تفصيلًا)."""
    summary = _title_lead(row.get("summary"))
    features = _title_lead(row.get("features"))
    candidate = max(summary, features, key=len)
    return candidate


def signature(row: dict[str, Any]) -> tuple:
    """توقيع التطابق: المصدر + المنطقة + نوع العقار + السعر + العنوان المطبع."""
    return (
        normalize_arabic(row.get("source")),
        normalize_arabic(row.get("area")),
        normalize_arabic(row.get("property_type") or row.get("detail_class")),
        price_key(row.get("price")),
        title_key(row),
    )


def is_duplicate_group(group: list[dict[str, Any]], min_title_len: int = MIN_TITLE_LEN) -> bool:
    """بوابة الدقة: هل هذه المجموعة تكرار حقيقي أم وحدات متشابهة شرعيًا؟"""
    if len(group) < 2:
        return False
    # عنوان مطبع كافٍ — عناوين عامة قصيرة لا تُدمج
    titles = [title_key(row) for row in group]
    if min(len(t) for t in titles) < min_title_len:
        return False
    # الهاتف: إن وُجد لدى أكثر من إعلان فيجب أن يتطابق — اختلافه = معلنون مختلفون
    phones = {phone_key(row.get("phone")) for row in group if phone_key(row.get("phone"))}
    if len(phones) > 1:
        return False
    # المساحة: إن وُجدت لدى أكثر من إعلان فيجب أن تتطابق
    spaces = {space_key(row.get("space")) for row in group if space_key(row.get("space")) is not None}
    if len(spaces) > 1:
        return False
    # بوابة الإثبات المستقل: تطابق النص وحده لا يكفي — يجب أن يحمل إعلان واحد
    # على الأقل هاتفًا أو مساحة (إشارة فيزيائية/تواصل مستقلة عن الوصف).
    # بلاها، تُدمج وحدات متطابقة شرعيًا من قوالب منصات (مثل «بيت 8 غرفة للإيجار
    # في عبدلي» بقائمة موحّدة) أو أراضٍ متماثلة بلا تفاصيل.
    if not (any(phone_key(row.get("phone")) for row in group)
            or any(space_key(row.get("space")) is not None for row in group)):
        return False
    return True


def _is_official_row(row: dict[str, Any]) -> bool:
    """صفوف رسمية/مرجعية (صفقات الحسبة، المؤشرات) — بيانات منظمة لا تُدمج أبدًا.

    أكوادها OFF-*/OFFIND-*، ومصادرها «الحسبة - الصفقات المسجلة العامة» ونحوها؛
    صفقتان رسميتان بنفس السعر/المساحة صفقتان حقيقيتان (شائع في السجلات).
    """
    code = str(row.get("code") or "")
    source = normalize_arabic(row.get("source"))
    return code.startswith(("OFF-", "OFFIND-")) or any(
        token in source for token in ("الحسبة", "الصفقات", "مؤشرات")
    )


def _created_at(row: dict[str, Any]) -> str:
    value = row.get("created_at") or ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return str(value)


def group_canonical(group: list[dict[str, Any]]) -> dict[str, Any]:
    """النظير المحتفظ به: الأقدم إنشاءً (ثابت عبر التشغيلات)، ثم الأصغر رمزًا."""
    return min(group, key=lambda row: (_created_at(row), str(row.get("code") or "")))


def build_dedupe_groups(
    rows: list[dict[str, Any]],
    min_title_len: int = MIN_TITLE_LEN,
) -> list[list[dict[str, Any]]]:
    """تجميع الإعلانات شبه المكررة التي تجتاز بوابات الدقة.

    يعيد قوائم المجموعات (كل مجموعة ≥ 2 إعلان تكرار). المجموعة الواحدة لها
    توقيع واحد تام التطابق بعد التطبيع.
    """
    buckets: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        if _is_official_row(row):
            continue  # الصفوف الرسمية/المرجعية لا تدخل كشف التكرار أبدًا
        key = signature(row)
        if key[0] and key[1] and key[2] and key[4]:
            buckets.setdefault(key, []).append(row)
    groups = []
    for bucket in buckets.values():
        if is_duplicate_group(bucket, min_title_len=min_title_len):
            groups.append(bucket)
    return groups


def duplicate_marks(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """قرارات الوسم: لكل مجموعة، النظير (الأقدم) يُحتفظ به والبقية duplicate_of.

    يعيد قائمة {code, duplicate_of} للمصاف غير النظير — جاهزة للتطبيق.
    """
    marks: list[dict[str, Any]] = []
    for group in groups:
        canonical = group_canonical(group)
        for row in group:
            if str(row.get("code") or "") != str(canonical.get("code") or ""):
                marks.append(
                    {"code": str(row.get("code") or ""), "duplicate_of": str(canonical.get("code") or "")}
                )
    return marks
