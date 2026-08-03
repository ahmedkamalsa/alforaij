from __future__ import annotations

from backend.models import RankedListing


def evidence_summary(item: RankedListing) -> str:
    count = len(item.comparables)
    if count == 0:
        return "لا توجد مقارنات كافية، الحكم استرشادي ضعيف."
    return f"تمت المقارنة مع {count} عروض مشابهة متاحة."
