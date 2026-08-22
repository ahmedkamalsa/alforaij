from __future__ import annotations

import re

from backend.models import PropertyRequest


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# ─────────────────────────────────────────────
# جميع مناطق الكويت (120+ منطقة) مع مراعاة
# الكتابات المختلفة في كلتا اللغتين
# ─────────────────────────────────────────────
KNOWN_AREAS = [
    # محافظة العاصمة
    "الديرة", "القبلة", "الشرق", "مرقاب", "كيفان", "الدسمة",
    "الروضة", "الخالدية", "الفيحاء", "اليرموك", "القادسية",
    "النهضة", "الأندلس", "الاندلس", "الشويخ", "الصليبخات",
    "الريان", "العديلية", "غرناطة", "إشبيلية", "اشبيلية",
    "الشامية", "الصوابر", "دسمة", "ضاحية عبدالله السالم",
    "عبدالله السالم", "قرطبة", "بنيد القار", "مطرف",
    "المنصورية", "السرة", "القيروان", "الدوحة", "ضاحية حصة المبارك",
    # محافظة حولي
    "السالمية", "الجابرية", "حولي", "الرميثية", "بيان",
    "مشرف", "الشعب", "حطين", "سلوى", "الزهراء",
    "البدع", "الفردوس", "صباح السالم", "ميدان حولي",
    "خيطان", "أبو حليفة", "ابو حليفة",
    # محافظة مبارك الكبير
    "صباح السالم", "أبو فطيرة", "ابو فطيرة", "القصور",
    "المسيلة", "صبحان", "العقيلة", "مبارك الكبير",
    "أبو الحصانية", "ابو الحصانية", "فنيطيس", "القرين",
    # محافظة الفروانية
    "الفروانية", "خيطان", "عمان", "الرابية", "أبو فطيرة",
    "الأندلس", "العارضية", "صباح الناصر", "الرحاب",
    "الجهراء الجديدة", "الضجيج", "الرقة", "جليب الشيوخ",
    "الرقعي", "العمرية", "عبدالله المبارك", "جنوب عبدالله المبارك",
    # محافظة الأحمدي
    "الأحمدي", "الفحيحيل", "المهبولة", "أبو حليفة",
    "الرقة", "الصباحية", "الوفرة", "الزور", "ميناء عبدالله",
    "هدية", "الخيران", "صباح الأحمد", "صباح الاحمد",
    "العدان", "المنقف", "البصري", "الجليعة", "ضاحية الفحيحيل",
    "بنيدر", "مزيرعة الوفرة", "نويصيب", "أم قدير",
    "الفنطاس", "الظهر", "ضاحية فهد الأحمد", "غرب عبدالله مبارك", "ام الهيمان",
    "بيت خيران السكنية", "بيت الخيران السكنية", "الخيران السكنية",
    # محافظة الجهراء
    "الجهراء", "المطلاع", "جابر الأحمد", "جابر الاحمد",
    "سعد العبدالله", "الصليبية", "الوهاب", "تيماء",
    "شمال غرب الصليبيخات", "الصليبيخات", "الواحة", "كاظمة",
    "القصر", "الجهراء الجديدة", "الأمغرة",
    "النسيم", "النعيم", "السالمي", "العيون", "كبد",
]

# إزالة المكررات مع الحفاظ على الترتيب
_seen: set[str] = set()
_unique: list[str] = []
for _a in KNOWN_AREAS:
    if _a not in _seen:
        _seen.add(_a)
        _unique.append(_a)
KNOWN_AREAS = _unique

# ─────────────────────────────────────────────
# دمج المناطق الفعلية الموجودة في البيانات المحلية تلقائيًا
# حتى لا يفشل اكتشاف المنطقة (مثل: النهضة) ويبحث النظام في كل المناطق
# ─────────────────────────────────────────────
try:
    from backend.config import SEED_LISTINGS_PATH

    if SEED_LISTINGS_PATH.exists():
        import json as _json

        _records = _json.loads(SEED_LISTINGS_PATH.read_text(encoding="utf-8"))
        for _row in _records:
            _area = str(_row.get("area") or "").strip()
            if _area and _area not in KNOWN_AREAS:
                KNOWN_AREAS.append(_area)
except Exception:
    pass  # في غياب البيانات نكتفي بالقائمة الثابتة

# ─────────────────────────────────────────────
# أسماء بديلة (Aliases) لكل منطقة
# ─────────────────────────────────────────────
AREA_ALIASES: dict[str, list[str]] = {
    "بنيد القار": ["بنيدالقار", "بنييد القار", "بند القار", "bnaid al-qar", "bnaid al qar", "bneid al-qar"],
    "إشبيلية": ["اشبيلية", "اشبيليه", "إشبيليه", "ishbiliya", "ishbilia", "eshbiliya"],
    "غرناطة": ["غرناطه", "قرناطة", "granada", "gharnata", "ghornata", "ghornata city"],
    "قرطبة": ["قرطبه", "القرطبة", "cordoba", "qurtuba", "qortuba"],
    "الأندلس": ["الاندلس", "اندلس", "andalus"],
    "اليرموك": ["يرموك", "yarmouk"],
    "القادسية": ["قادسية", "القادسيه", "qadisiya", "qadsiya"],
    "العدان": ["عدان", "addan", "adan", "al-adan"],
    "المنقف": ["منقف", "mangaf", "al-mangaf"],
    "الفحيحيل": ["فحيحيل", "fahaheel", "faheel", "al-fahaheel"],
    "صباح الأحمد": ["صباح الاحمد", "صباح احمد", "صباح الاحمد البحرية", "صباح الاحمد البحريه", "البحرية", "البحرية الخامسة", "البحريه الخامسه", "sabah al ahmed", "sabah al-ahmad", "sabah al ahmad", "سكوير الخير", "مول سكوير الخير", "سكوير الخير مول"],
    "جابر الأحمد": ["جابر الاحمد", "جابر احمد", "jaber al ahmed", "jaber al-ahmed"],
    "سعد العبدالله": ["سعد عبدالله", "سعد العبد الله", "سعد العبدالله", "سعدالعبدالله", "سعد الله", "سعدالله", "saad al abdallah", "saad al-abdallah", "saad al abdullah", "saad al-abdullah"],
    "شمال غرب الصليبيخات": ["شمال غرب صليبيخات", "north west sulaibikhat", "nwsk"],
    "الصليبيخات": ["صليبيخات", "الصليبخات", "الصليبيخات", "sulaibikhat", "sulai bikhat"],
    "صباح السالم": ["صباح السالم", "sabah al salem", "sabah al-salem"],
    "السالمية": ["سالمية", "salmiya", "salamiya"],
    "الرميثية": ["رميثية", "rumaithiya", "rumaithia"],
    "المطلاع": ["مطلاع", "mutlaa", "mutla"],
    "أبو فطيرة": ["ابو فطيرة", "ابو فطيره", "ابوفطيرة", "ابوفطيره", "بوفطيره", "بوفطيرة", "بو فطيره", "abu fatira", "abu-fatira", "abu ftaira", "abu fteira", "abu ftayra"],
    "الجابرية": ["جابرية", "jabriya", "jabriyya"],
    "خيطان": ["khaitan", "kheitan"],
    "حولي": ["hawalli", "hawally"],
    "بيان": ["bayan"],
    "سلوى": ["salwa", "salwah"],
    "الأحمدي": ["احمدي", "ahmadi", "al-ahmadi"],
    "الجهراء": ["جهراء", "jahra", "al-jahra"],
    "الفروانية": ["فروانية", "farwaniya", "farwaniyya"],
    "النهضة": ["نزهة", "النزهه", "نزهه", "النهضه", "nuzha", "al-nuzha", "النزهة"],
    # ── مناطق أُضيفت من نص الإعلانات الخارجية (الحصاد اليومي) ──
    "المنصورية": ["المنصوريه", "mansouriya", "al-mansouriya", "mansuriya"],
    "السرة": ["السره", "surra", "al-surra", "sorra"],
    "ضاحية حصة المبارك": ["حصة المبارك", "حصه المبارك", "hessah al mubarak", "hessah"],
    "القيروان": ["qairawan", "kairouan", "qayrawan"],
    "النسيم": ["nasseem", "naseem", "al-naseem", "nassim"],
    "النعيم": ["naeem", "al-naeem", "al naeem"],
    "السالمي": ["salmy", "salmi", "al-salmi"],
    "العيون": ["oyoun", "al-oyoun", "el-oyoun"],
    "كبد": ["الكبد", "kabd", "al-kabd"],
    "غرب عبدالله مبارك": ["غرب عبد الله مبارك", "غرب عبدالله المبارك", "غرب عبد الله المبارك", "west abdullah al mubarak"],
    "جنوب عبدالله المبارك": ["جنوب عبد الله المبارك", "south abdullah al mubarak"],
    "ضاحية فهد الأحمد": ["فهد الاحمد", "فهد الأحمد", "fahad al ahmad", "fahd al ahmad"],
    "عبدالله المبارك": ["عبد الله المبارك", "abdullah al mubarak"],
    "عبدالله السالم": ["عبد الله السالم", "abdullah al salem", "abdulla al salem"],
    "ام الهيمان": ["أم الهيمان", "ام الهيمان", "um al haiman", "um al-haiman", "علي صباح السالم"],
    "مرقاب": ["المرقاب", "mirqab", "al-mirqab"],
    "الشرق": ["sharq", "al-sharq"],
    "القبلة": ["qibla", "al-qibla", "jibla"],
    "الشويخ": ["شويخ", "shuwaikh", "shuaikh", "shuwaikh industrial"],
    "الدسمة": ["dasma", "dasman"],
    "الفيحاء": ["faiha", "al-faiha"],
    "الأمغرة": ["امغرة", "amghara", "amgarah", "amgara"],
    "الواحة": ["الواحه", "waha", "al-waha"],
    "كاظمة": ["kazma", "kathma"],
    "الصليبية": ["sulaibiya", "sulibiya"],
    "تيماء": ["taima", "tayma"],
    "العارضية": ["ardhiya", "al-ardhiya", "العارضيه"],
    "الرابية": ["ربيه", "الربيه", "rabiya", "al-rabiya"],
    "جليب الشيوخ": ["jleeb al shuyoukh", "jleeb"],
    "الرقعي": ["raqai", "al-raqai"],
    "العمرية": ["omariya", "al-omariya", "العمريه"],
    "الفردوس": ["فردوس", "ferdous", "al-firdous"],
    "الفنيطيس": ["funaitees", "al-fnaitees"],
    "الفنطاس": ["fintas", "al-fintas"],
    "القرين": ["qurain", "al qurain"],
    "القصور": ["qusour", "al qusour"],
    "صبحان": ["subhan"],
    "المهبولة": ["mahboula", "mahbula"],
    "الصباحية": ["sabahiya", "al-sabahiya"],
    "الوفرة": ["wafra", "al-wafra"],
    "الزور": ["zour", "al-zour"],
    "هدية": ["hadiya", "hediya"],
    "الخيران": ["khairan", "kheiran"],
    "بيت خيران السكنية": ["بيت الخيران السكنية", "الخيران السكنية", "bayt khiran residential", "bayt al-khiran", "bayt al khiran"],
    "نويصيب": ["nuwaisib", "nuwaiseeb"],
    "أم قدير": ["ام قدير", "um qadeer"],
    "ميدان حولي": ["midan hawally"],
    "المسيلة": ["mesila", "messila"],
    "الشعب": ["shaab", "shuab"],
    "حطين": ["hitteen", "hittin"],
    "الزهراء": ["zahra", "al-zahra"],
    "البدع": ["bidaa", "al-bidaa", "al bida"],
    "مشرف": ["mishref", "mishrif"],
    "أبو حليفة": ["ابو حليفه", "ابوحليفة", "ابوحليفه", "abu hulaifa", "abu hulayfa", "abu halifa"],
    "أبو الحصانية": ["ابو الحصانيه", "ابو الحصانية", "abu al hasaniya", "abu hasaniya"],
}

GOVERNORATE_AREA_NAMES = {
    "العاصمة",
    "حولي",
    "الفروانية",
    "مبارك الكبير",
    "الأحمدي",
    "الاحمدي",
    "الجهراء",
}

# مناطق كل محافظة — تُستخدم لتوسيع طلب يذكر محافظة بلا منطقة محددة
# (مثل «بالعاصمة» أو «فروانية») حتى لا تُفقد المحافظات غير المدرجة كمنطقة
GOVERNORATE_AREAS: dict[str, list[str]] = {
    "العاصمة": [
        "الديرة", "القبلة", "الشرق", "مرقاب", "كيفان", "الدسمة",
        "الروضة", "الخالدية", "الفيحاء", "اليرموك", "القادسية",
        "النهضة", "الأندلس", "الاندلس", "الشويخ", "الصليبخات",
        "الريان", "العديلية", "غرناطة", "إشبيلية", "اشبيلية",
        "الشامية", "الصوابر", "دسمة", "ضاحية عبدالله السالم",
        "عبدالله السالم", "قرطبة", "بنيد القار", "مطرف",
        "المنصورية", "السرة", "القيروان", "الدوحة", "ضاحية حصة المبارك",
    ],
    "حولي": [
        "السالمية", "الجابرية", "حولي", "الرميثية", "بيان",
        "مشرف", "الشعب", "حطين", "سلوى", "الزهراء",
        "البدع", "الفردوس", "صباح السالم", "ميدان حولي",
        "خيطان", "أبو حليفة", "ابو حليفة",
    ],
    "مبارك الكبير": [
        "صباح السالم", "أبو فطيرة", "ابو فطيرة", "القصور",
        "المسيلة", "صبحان", "العقيلة", "مبارك الكبير",
        "أبو الحصانية", "ابو الحصانية", "فنيطيس", "القرين",
    ],
    "الفروانية": [
        "الفروانية", "خيطان", "عمان", "الرابية", "أبو فطيرة",
        "الأندلس", "العارضية", "صباح الناصر", "الرحاب",
        "الجهراء الجديدة", "الضجيج", "الرقة", "جليب الشيوخ",
        "الرقعي", "العمرية", "عبدالله المبارك", "جنوب عبدالله المبارك",
    ],
    "الأحمدي": [
        "الأحمدي", "الفحيحيل", "المهبولة", "أبو حليفة",
        "الرقة", "الصباحية", "الوفرة", "الزور", "ميناء عبدالله",
        "هدية", "الخيران", "صباح الأحمد", "صباح الاحمد",
        "العدان", "المنقف", "البصري", "الجليعة", "ضاحية الفحيحيل",
        "بنيدر", "مزيرعة الوفرة", "نويصيب", "أم قدير",
        "الفنطاس", "الظهر", "ضاحية فهد الأحمد", "غرب عبدالله مبارك", "ام الهيمان",
        "بيت خيران السكنية", "بيت الخيران السكنية", "الخيران السكنية",
    ],
    "الجهراء": [
        "الجهراء", "المطلاع", "جابر الأحمد", "جابر الاحمد",
        "سعد العبدالله", "الصليبية", "الوهاب", "تيماء",
        "شمال غرب الصليبيخات", "الواحة", "كاظمة",
        "القصر", "الجهراء الجديدة", "الأمغرة",
        "النسيم", "النعيم", "السالمي", "العيون", "كبد",
    ],
}

# خريطة دقيقة منطقة ← محافظة: كل منطقة في محافظة واحدة فقط (عربي + إنجليزي) — تُستخدم
# لسدّ المحافظة الناقصة في سجلات اللوحة بدل تجميع المناطق المعروفة تحت «غير محددة».
# هذه خريطة إسناد (تخصيص) مختلفة عن GOVERNORATE_AREAS التي هي خريطة توسيع استعلامية
# وقد تحوي المنطقة نفسها في أكثر من محافظة. عند أي تعارض، هذه الخريطة هي المرجع الأدق.
AREA_TO_GOVERNORATE: dict[str, str] = {
    # ── العاصمة ──
    "الديرة": "العاصمة", "القبلة": "العاصمة", "الشرق": "العاصمة", "مرقاب": "العاصمة",
    "كيفان": "العاصمة", "الدسمة": "العاصمة", "الروضة": "العاصمة", "الخالدية": "العاصمة",
    "الفيحاء": "العاصمة", "اليرموك": "العاصمة", "القادسية": "العاصمة", "النهضة": "العاصمة",
    "الأندلس": "الفروانية", "الاندلس": "الفروانية", "الشويخ": "العاصمة", "الصليبخات": "العاصمة",
    "الريان": "العاصمة", "العديلية": "العاصمة", "غرناطة": "العاصمة", "إشبيلية": "الفروانية",
    "اشبيلية": "الفروانية", "الشامية": "العاصمة", "الصوابر": "العاصمة", "دسمة": "العاصمة",
    "ضاحية عبدالله السالم": "العاصمة", "عبدالله السالم": "العاصمة", "قرطبة": "العاصمة",
    "بنيد القار": "العاصمة", "مطرف": "العاصمة", "الدوحة": "العاصمة", "المباركية": "العاصمة",
    "القيروان": "العاصمة", "المنصورية": "العاصمة", "السرة": "العاصمة",
    "ضاحية حصة المبارك": "العاصمة", "حصة المبارك": "العاصمة", "الصليبيخات": "العاصمة",
    "المرقاب": "العاصمة", "الدعية": "العاصمة", "النزهة": "العاصمة", "شرق": "العاصمة",
    "العاصمة - 1": "العاصمة", "العاصمة - 13": "العاصمة", "العاصمة - 77": "العاصمة",
    "Al Asimah - 1": "العاصمة", "Al Asimah - 13": "العاصمة", "Al Asimah - 77": "العاصمة",
    # ── حولي ──
    "السالمية": "حولي", "Salmiya": "حولي", "الجابرية": "حولي", "الرميثية": "حولي",
    "Rumaithiya": "حولي", "بيان": "حولي", "Bayan": "حولي", "مشرف": "حولي", "Hawally": "حولي",
    "الشعب": "حولي", "Shaab": "حولي", "حطين": "حولي", "سلوى": "حولي",
    "الزهراء": "حولي", "البدع": "حولي", "ميدان حولي": "حولي", "الشهداء": "حولي",
    "الصديق": "حولي", "السلام": "حولي", "النقرة": "حولي", "جنوب السرة": "حولي",
    "سلام": "حولي",
    # ── مبارك الكبير ──
    "صباح السالم": "مبارك الكبير", "أبو فطيرة": "مبارك الكبير", "ابو فطيرة": "مبارك الكبير",
    "القصور": "مبارك الكبير", "المسيلة": "مبارك الكبير", "صبحان": "مبارك الكبير",
    "العقيلة": "مبارك الكبير", "أبو الحصانية": "مبارك الكبير", "ابو الحصانية": "مبارك الكبير",
    "فنيطيس": "مبارك الكبير", "الفنيطيس": "مبارك الكبير", "القرين": "مبارك الكبير",
    "المسايل": "مبارك الكبير", "العدان": "مبارك الكبير", "مبارك الكبير - 4": "مبارك الكبير",
    "Mubarak Al-Kabeer - 4": "مبارك الكبير", "فنطاس": "مبارك الكبير",
    # ── الفروانية ──
    "خيطان": "الفروانية", "Khaitan": "الفروانية",
    "عمان": "الفروانية", "الرابية": "الفروانية", "العارضية": "الفروانية",
    "صباح الناصر": "الفروانية", "الرحاب": "الفروانية", "الجهراء الجديدة": "الفروانية",
    "الضجيج": "الفروانية", "الفردوس": "الفروانية", "جليب الشيوخ": "الفروانية",
    "جليب الشيوخ - الحساوي": "الفروانية", "خيطان الجنوبي الجديدة": "الفروانية",
    "الرقعي": "الفروانية", "العمرية": "الفروانية", "الشدادية": "الفروانية",
    "عبدالله المبارك": "الفروانية", "جنوب خيطان": "الفروانية", "جنوب عبدالله المبارك": "الفروانية",
    # ── الأحمدي ──
    "Ahmadi": "الأحمدي", "الفحيحيل": "الأحمدي",
    "المهبولة": "الأحمدي", "أبو حليفة": "الأحمدي", "ابو حليفة": "الأحمدي",
    "الرقة": "الأحمدي", "الصباحية": "الأحمدي", "الوفرة": "الأحمدي", "الزور": "الأحمدي",
    "ميناء عبدالله": "الأحمدي", "هدية": "الأحمدي",    "الخيران": "الأحمدي", "صباح الأحمد": "الأحمدي", "صباح الاحمد": "الأحمدي", "Sabah Al-Ahmad": "الأحمدي",
    "بيت خيران السكنية": "الأحمدي", "بيت الخيران السكنية": "الأحمدي", "الخيران السكنية": "الأحمدي",

    "المنقف": "الأحمدي", "البصري": "الأحمدي", "الجليعة": "الأحمدي",
    "ضاحية الفحيحيل": "الأحمدي", "بنيدر": "الأحمدي", "نويصيب": "الأحمدي",
    "الوفرة الجديدة": "الأحمدي", "صباح الأحمد البحرية": "الأحمدي",
    "صباح الاحمد البحرية": "الأحمدي", "صباح الأحمد البحرية (الخيران)": "الأحمدي",
    "صباح الاحمد البحرية (الخيران)": "الأحمدي",
    "أم قدير": "الأحمدي", "صباح الأحمد السكنية": "الأحمدي", "صباح الاحمد السكنية": "الأحمدي",
    "الخيران السكنية - الجانب البري": "الأحمدي",
    "جابر العلي": "الأحمدي", "الفنطاس": "الأحمدي", "الظهر": "الأحمدي",
    "الوفرة السكنية": "الأحمدي", "علي صباح السالم": "الأحمدي", "ام الهيمان": "الأحمدي",
    "غرب عبدالله مبارك": "الأحمدي", "غرب عبد الله مبارك": "الأحمدي", "غرب عبدالله المبارك": "الأحمدي",
    "ضاحية فهد الأحمد": "الأحمدي", "صباح الاحمد البحرية - الخيران": "الأحمدي",
    "علي صباح السالم - ام الهيمان": "الأحمدي",
    "مزيرعة الوفرة": "الأحمدي", "الخيران السكنية": "الأحمدي", "الخيران السكنية - الجانب البري": "الأحمدي",
    # ── الجهراء ──
    "المطلاع": "الجهراء", "Mutlaa": "الجهراء",
    "جابر الأحمد": "الجهراء", "جابر الاحمد": "الجهراء", "سعد العبدالله": "الجهراء",
    "الصليبية": "الجهراء", "الوهاب": "الجهراء", "تيماء": "الجهراء",
    "شمال غرب الصليبيخات": "العاصمة", "الواحة": "الجهراء", "كاظمة": "الجهراء",
    "القصر": "الجهراء", "الأمغرة": "الجهراء", "أمغرة": "الجهراء", "عبدلي": "الجهراء",
    "جنوب المطلاع": "الجهراء", "الجهراء القديمة": "الجهراء",
    "العيون": "الجهراء", "القيصرية": "الجهراء", "النسيم": "الجهراء",
    "النعيم": "الجهراء", "السالمي": "الجهراء", "كبد": "الجهراء",
}

PROPERTY_TYPES = {
    "بيت":   ["بيت", "منزل", "فيلا", "قسيمة", "هدام", "دور", "house", "villa"],
    "شقة":   ["شقة", "شقه", "دوبلكس", "apartment", "flat"],
    "أرض":   ["ارض", "أرض", "قسيمة", "قسيمه", "land", "plot"],
    "عمارة": ["عمارة", "عماره", "عقار استثماري", "استثماري", "بناية", "building"],
    "تجاري": ["تجاري", "محل", "مكتب", "مجمع تجاري", "commercial"],
}

# ميزات الموقع المهمة في التقييم
SITE_FEATURES = {
    "زاوية":        ["زاوية", "زاويه", "corner", "زاوي"],
    "شارعين":       ["شارعين", "على شارعين", "واجهتين", "two streets"],
    "شارع رئيسي":   ["شارع رئيسي", "شارع عام", "main street", "طريق رئيسي"],
    "قرب خدمات":    ["قرب الخدمات", "قريب الخدمات", "بالقرب من", "قريب من"],
    "مصعد":         ["مصعد", "elevator", "اسانسير"],
    "موقف سيارات":  ["موقف", "مواقف", "garage", "كراج"],
}

# أنواع البائع
SELLER_TYPES = {
    "مباشر": [
        "المالك مباشرة", "مالك مباشر", "بدون سمسرة", "بدون سمسار",
        "بدون عمولة", "مباشرة من المالك", "مالك", "مباشر",
        "owner direct", "no commission", "بدون وسيط",
    ],
    "مكتب": [
        "مكتب عقاري", "شركة عقارية", "مكتب", "شركة", "office",
        "company", "للتواصل مع الشركة", "agency",
        "بوشملان", "الكويتية للعقار", "دار الوسم",
    ],
}


def normalize_text(text: str) -> str:
    text = (text or "").translate(AR_DIGITS)
    text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", text)
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def area_terms(area: str) -> list[str]:
    return [area, *AREA_ALIASES.get(area, [])]


def text_has_area(area: str, text: str) -> bool:
    normalized = normalize_text(text)
    lower_text = (text or "").lower()
    for term in area_terms(area):
        if normalize_text(term) in normalized or term.lower() in lower_text:
            return True
    return False


_GOVERNORATE_NAMES = {"حولي", "الفروانية", "الأحمدي", "الجهراء", "العاصمة", "مبارك الكبير"}


def detect_area_in_text(text: str) -> str:
    """يكتشف منطقة كويتية واحدة في نص إعلان (عنوان/وصف/خبز فتات الموقع).

    يُفضّل المنطقة الحقيقية ثم الأطول حتى لا يلتقط اسمًا قصيرًا داخل اسم أطول
    («ميدان حولي» قبل «حولي»، «الجهراء الجديدة» قبل «الجهراء»، «غرب عبدالله
    مبارك» قبل «عبدالله المبارك») ولا اسم محافظة مكررًا في خبز الفتات («النعيم»
    قبل «الجهراء» في "Al Naeem Al Jahra"). المطابقة عبر الأسماء المرادفة (عربي
    + إنجليزي) مع تطبيع الهمزات، ولمتعددة الكلمات تُقارن بلا مسافات أيضًا
    («سعدالعبدالله» = «سعد العبدالله»، «ابوفطيره» = «ابو فطيره»).
    """
    if not text:
        return ""
    normalized = normalize_text(text)
    lower_text = (text or "").lower()
    tight_text = re.sub(r"\s+", "", normalized)
    best = ""
    # أصغر مفتاح = أفضل: (منطقة حقيقية 0 قبل اسم محافظة 1) ثم الأطول (−الطول).
    best_key = (2, 0)
    for area in KNOWN_AREAS:
        for term in area_terms(area):
            term_n = normalize_text(term)
            matched = bool(
                (term_n and term_n in normalized)
                or (term and term.lower() in lower_text)
                or (
                    " " in term.strip()
                    and term_n
                    and term_n.replace(" ", "") in tight_text
                )
            )
            if matched:
                # المنطقة الحقيقية («النعيم») تسبق اسم المحافظة («الجهراء») عند
                # التعادل، لأن خبز فتات الموقع يكرر المحافظة في آخر السطر — ثم الأطول.
                key = (1 if area in _GOVERNORATE_NAMES else 0, -len(area))
                if key < best_key:
                    best_key = key
                    best = area
                break
    return best


# ── تطبيع المكان المشترك: نفس خريطة اللوحة المعتمدة لكل المسارات ────────────
# اللوحة (main.py) وتحليلات السوق (supabase_store + market_analysis) تبنيان
# دلاءهما من هذه الدوال نفسها: أي منطقة تُحل لمحافظة واحدة فقط بنفس الصيغة
# الكنسية — حتى لا تظهر «محافظة الاحمدي» بلا همزة بجانب «محافظة الأحمدي»
# في تحليلات تختلف عن اللوحة، ولا تنقسم دلو المحافظة نفسها بين صيغة قصيرة
# وأخرى كاملة (كما كان يحدث في market-insights).

# مفتاح تطبيع للمنطقة: همزات موحّدة + أحرف إنجليزية صغيرة — حتى تطابق
# «صباح الأحمد» و«Sabah Al-Ahmad» و«صباح الاحمد» نفس المفتاح في خريطة المناطق.
ARABIC_AREA_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def dashboard_area_key(area: str) -> str:
    return str(area or "").strip().lower().translate(ARABIC_AREA_NORM)


GOVERNORATE_ALIASES = {
    "الأحمدي": "محافظة الأحمدي",
    "احمدي": "محافظة الأحمدي",
    "الاحمدي": "محافظة الأحمدي",
    "محافظة الاحمدي": "محافظة الأحمدي",
    "حولي": "محافظة حولي",
    "الجهراء": "محافظة الجهراء",
    "العاصمة": "محافظة العاصمة",
    "الفروانية": "محافظة الفروانية",
    "مبارك الكبير": "محافظة مبارك الكبير",
}

# يوحّد همزات/تاء مربوطة في أسماء المحافظات حتى لا يتكرر
# «محافظة الأحمدي» و«الاحمدي» كصفين
_ARABIC_GOV_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def _governorate_key(value: str) -> str:
    clean = str(value or "").strip()
    if clean.startswith("محافظة "):
        clean = clean[len("محافظة "):]
    return clean.translate(_ARABIC_GOV_NORM).strip()


_GOVERNORATE_CANONICAL = {
    "الاحمدي": "محافظة الأحمدي",
    "حولي": "محافظة حولي",
    "الجهراء": "محافظة الجهراء",
    "العاصمة": "محافظة العاصمة",
    "الفروانية": "محافظة الفروانية",
    "مبارك الكبير": "محافظة مبارك الكبير",
}


def normalize_governorate_name(value: str) -> str:
    """الصيغة الكنسية لاسم المحافظة («محافظة الأحمدي») — نفسها في اللوحة والتحليلات."""
    clean = str(value or "").strip()
    if not clean:
        return ""
    canonical = _GOVERNORATE_CANONICAL.get(_governorate_key(clean))
    if canonical:
        return canonical
    if clean in GOVERNORATE_ALIASES:
        return GOVERNORATE_ALIASES[clean]
    if clean.startswith("محافظة "):
        return clean
    return clean


def area_governorate_map(listings) -> dict[str, str]:
    """خريطة منطقة ← محافظة بقيم كنسية — المرجع الأعلى للوحة والتحليلات معًا.

    تبدأ من الخريطة الدقيقة المعتمدة (AREA_TO_GOVERNORATE — كل منطقة في محافظة
    واحدة صحيحة) ثم تتعلم من السجلات المحلية سدّ الفجوات فقط (لا تغيّر إسنادًا
    معتمدًا). البناء نفسه في كل المسارات حتى لا تنحرف دلاء التحليلات عن اللوحة.
    """
    mapping: dict[str, str] = {}

    def _put(area: str, gov: str) -> None:
        normalized = normalize_governorate_name(gov)
        mapping[area] = normalized
        mapping[dashboard_area_key(area)] = normalized

    for area, gov in AREA_TO_GOVERNORATE.items():
        _put(area, gov)
    for row in listings:
        if row.area and row.governorate:
            gov = normalize_governorate_name(row.governorate)
            if row.area not in mapping and dashboard_area_key(row.area) not in mapping:
                _put(row.area, gov)
    return mapping


def normalize_dashboard_place(
    record: dict,
    area_map: dict[str, str],
    *,
    keep_governorate_area: bool = False,
) -> None:
    """تطبيع مكان سجل اللوحة/التحليلات: سدّ المنطقة من النص ثم المحافظة من الخريطة.

    نفس المسار الذي تبنى به اللوحة دلاءها — تحليلات السوق تستدعيه أيضًا لتبني
    دلاءها من نفس الخريطة المعتمدة بنفس الصيغ الكنسية: سدّ المنطقة الناقصة أو
    المُلتقطة خطأً كاسم محافظة من نص الإعلان (الملخص/الوصف)، ثم المحافظة من
    الخريطة، وتصفية منطقة تحمل اسم محافظة.

    keep_governorate_area: اللوحة تُصفّي المنطقة التي تحمل اسم محافظة («حولي»
    كمنطقة) لأن دلاءها محافظات؛ تحليلات السوق تحتاج المنطقة للبقاء (إحصائيات
    لكل منطقة) فتمرر True لملء المحافظة مع الإبقاء على اسم المنطقة.
    """
    area = str(record.get("area") or "").strip()
    governorate = str(record.get("governorate") or "").strip()
    # سدّ المنطقة من النص: عندما تكون المنطقة فارغة أو اسم محافظة فقط
    # (مثل "الجهراء" أو "الفروانية")، نحاول استخراج منطقة أدق من النص
    if not area or area in GOVERNORATE_ALIASES or area in _GOVERNORATE_CANONICAL or area in GOVERNORATE_AREA_NAMES:
        hint = " ".join(
            x for x in (record.get("summary") or "", record.get("features") or "") if x
        )
        if hint:
            detected = detect_area_in_text(hint)
            if detected and detected != area:
                area = detected
                record["area"] = area
    if governorate:
        record["governorate"] = normalize_governorate_name(governorate)
    if not record.get("governorate") and area:
        if area in area_map:
            record["governorate"] = area_map[area]
        else:
            key = dashboard_area_key(area)
            if key in area_map:
                record["governorate"] = area_map[key]
    if not record.get("governorate") and area in GOVERNORATE_ALIASES:
        record["governorate"] = normalize_governorate_name(area)
        if not keep_governorate_area:
            record["area"] = ""


def detect_site_features(text: str) -> list[str]:
    """استخراج مميزات الموقع من النص (زاوية، شارعين، إلخ)."""
    normalized = normalize_text(text)
    found = []
    for feature, keywords in SITE_FEATURES.items():
        if any(normalize_text(kw) in normalized for kw in keywords):
            found.append(feature)
    return found


def detect_seller_type(text: str) -> str:
    """تحديد نوع البائع: مباشر أو مكتب أو غير محدد."""
    normalized = normalize_text(text)
    for seller_type, keywords in SELLER_TYPES.items():
        if any(normalize_text(kw) in normalized for kw in keywords):
            return seller_type
    return "غير محدد"


def parse_money(text: str) -> float | None:
    text = normalize_text(text)
    million_match = re.search(r"(?:مليون)\s*(?:و\s*)?([0-9]+)?", text)
    if million_match:
        extra = float(million_match.group(1) or 0) * 1000
        return 1_000_000 + extra
    matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(الف|ألف|دينار|د\.ك|دك)?", text)
    candidates: list[float] = []
    for raw, unit in matches:
        value = float(raw)
        if unit in {"الف", "ألف"}:
            value *= 1000
        candidates.append(value)
    if not candidates:
        return None
    money_words = ("ميزانيه", "حدود", "سعر", "مطلوب", "بياع", "ايجار", "دينار", "د.ك", "دك", "مراجعه", "سوم", "سومها", "بسوم")
    if any(word in text for word in money_words):
        return max(candidates)
    return None


def _first_pos(area: str, normalized_text: str) -> int:
    """أول موضع تظهر فيه المنطقة (أو أحد أسمائها البديلة) داخل نص مُطبَّع."""
    for term in area_terms(area):
        index = normalized_text.find(normalize_text(term))
        if index >= 0:
            return index
    return -1


def excluded_numbers(text: str) -> dict[str, float]:
    """استخراج أرقام المستثناة من المساحة (ارتداد، واجهة، عرض شارع)."""
    text = normalize_text(text)
    excluded: dict[str, float] = {}
    for label in ("ارتداد", "واجهه", "واجهة", "شارع عرض", "عرض الشارع"):
        match = re.search(rf"{label}\s*([0-9]+(?:\.[0-9]+)?)\s*(?:متر|م)", text)
        if match:
            excluded[label] = float(match.group(1))
    return excluded


def _follows_exclusion(text: str, pos: int, spans: list[tuple[int, int]]) -> bool:
    """هل يقع موضع الرقم داخل نطاق واجهة/ارتداد/عرض شارع أو ملاصق له مباشرة؟"""
    for start, end in spans:
        if start <= pos <= end:
            return True
        if pos > end and not text[end:pos].strip():
            return True
    return False


def _is_governorate_mention(area: str, normalized_text: str) -> bool:
    if area not in GOVERNORATE_AREA_NAMES:
        return False
    area_norm = normalize_text(area)
    gov_norm = normalize_text("محافظة")
    return bool(re.search(rf"{gov_norm}\s+{re.escape(area_norm)}", normalized_text))


def extract_area_range(text: str) -> tuple[float | None, float | None, dict[str, float]]:
    text = normalize_text(text)
    excluded: dict[str, float] = {}
    exclusion_spans: list[tuple[int, int]] = []
    for label in ("ارتداد", "واجهه", "واجهة", "شارع عرض", "عرض الشارع"):
        for match in re.finditer(rf"{label}\s*([0-9]+(?:\.[0-9]+)?)\s*(?:متر|م)", text):
            if label not in excluded:
                excluded[label] = float(match.group(1))
            exclusion_spans.append(match.span())

    range_match = re.search(r"(?:مساحه|المساحه)\s*(?:من)?\s*([0-9]+)\s*(?:الى|إلى|-)\s*([0-9]+)", text)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2)), excluded

    # دعم كسور عشرية مثل 487.5م² (مع استبعاد أرقام الواجهة/الارتداد/عرض الشارع)
    exact_pattern = re.compile(
        r"(?:مساحه|المساحه|مساحتها|مساحته|المساحة|مساحة)?\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:متر|م2|م²|م\s*²|متر مربع|م(?:\s|$))"
    )
    for match in exact_pattern.finditer(text):
        if not _follows_exclusion(text, match.start(), exclusion_spans):
            value = float(match.group(1))
            return value, value, excluded

    return None, None, excluded


def extract_rental_income(text: str) -> tuple[float | None, str]:
    """استخراج الدخل الإيجاري من نص عربي/إعلان.

    يلتقط الصيغ الشائعة: «مؤجر ب 1200 شهرياً»، «مؤجره بـ 350»، «دخلها 20 الف»،
    «دخله 25000 سنوياً»، «ايجارها 400 بالشهر»، «قيمه ايجارها 30 الف» …

    يعيد (المبلغ بالدينار، الفترة) حيث الفترة "monthly" أو "annual":
      - ورود «شهرياً/بالشهر/للشهر» → شهري، «سنوياً/بالسنه» → سنوي
      - بدون فترة: صيغ «مؤجر» تُفسَّر شهرية (الإيجارات الكويتية تُسعّر شهريًا)
        وصيغ «دخل/ايجارها» تُفسَّر سنوية (الدخل السنوي للعقار).
    يعيد (None, "") عند عدم وجود دخل إيجاري في النص.
    """
    normalized = normalize_text(str(text or "")).replace("ـ", "")
    patterns = [
        # «مؤجر/مؤجره (بـ) X (فترة)» — الافتراضي شهري
        (r"مؤجره?\s+(?:ب)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:دينار|د\.ك|ك\s*د)?\s*(شهريا?|سنويا?|بالشهر|بالسنه|في الشهر|فى الشهر|للشهر|كل شهر)?", "monthly"),
        # «دخلها/دخله/الدخل/مدخولها/ايجارها/قيمه ايجارها (بـ) X (فترة)» — الافتراضي سنوي
        (r"(?:دخل(?:ها|ه)?|الدخل|مدخولها|ايجارها|قيمه ايجارها|قيمه ايجاره)\s*(?:ب)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:دينار|د\.ك|ك\s*د)?\s*(?:الف|ألف)?\s*(شهريا?|سنويا?|بالشهر|بالسنه|في الشهر|فى الشهر|للشهر|كل شهر)?", "annual"),
    ]
    for pattern, default_period in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        amount = float(match.group(1))
        # كلمة «ألف» بعد المبلغ → ×1000
        if any(word in match.group(0) for word in ("الف", "ألف")):
            amount *= 1000
        elif amount < 100:
            # مبلغ مختصر («دخلها 20» = 20 ألف سنويًا)
            amount *= 1000
        period_raw = (match.group(2) or "").strip()
        if "شهري" in period_raw or "الشهر" in period_raw or "كل شهر" in period_raw:
            period = "monthly"
        elif "سنوي" in period_raw or "السنه" in period_raw:
            period = "annual"
        else:
            period = default_period
        return round(amount, 2), period
    return None, ""


def parse_request(raw_text: str) -> PropertyRequest:
    normalized = normalize_text(raw_text)

    # نوع العملية — الأولوية للعلامة القاطعة: «للبيع» إعلان بيع يسبق أي ذكر عابر للإيجار
    # في النص المختلط (مثل بقايا رسالة سابقة «ايجار شقة في السالمية» قبل إعلان البيع)
    transaction = ""
    if "بدل" in normalized:
        transaction = "بدل"
    elif "للبيع" in normalized:
        transaction = "للبيع"
    elif any(word in normalized for word in ("عندي", "اعرض")) and any(word in normalized for word in ("ايجار", "استأجر", "استاجر")):
        transaction = "للإيجار"
    elif any(word in normalized for word in ("ايجار", "استأجر", "استاجر")):
        transaction = "مطلوب للإيجار"
    elif any(word in normalized for word in ("ابي", "ابغى", "مطلوب", "نشتري", "شراء")):
        transaction = "مطلوب للشراء"
    elif any(word in normalized for word in ("بيع", "عندي", "اعرض")):
        transaction = "للبيع"

    # نوع العقار
    property_type = ""
    for canonical, aliases in PROPERTY_TYPES.items():
        if any(normalize_text(alias) in normalized for alias in aliases):
            property_type = canonical
            break

    # المناطق
    areas = []
    for area in KNOWN_AREAS:
        if _is_governorate_mention(area, normalized):
            continue
        if text_has_area(area, raw_text) and area not in areas:
            areas.append(area)
    # منطقة مضمّنة داخل منطقة أطول مطابقة (مثل «الصليبيخات» داخل «شمال غرب الصليبيخات»)
    # لا تُحتسب كمنطقة مستقلة حتى لا يتسع البحث عن غير قصد
    areas = [
        a for a in areas
        if not any(b != a and a in b and text_has_area(b, raw_text) for b in areas)
    ]
    # المحافظات (بـ «محافظة» صراحة)
    governorates = [area for area in GOVERNORATE_AREA_NAMES if _is_governorate_mention(area, normalized)]
    # ذكر محافظة بلا «محافظة» قبلها (مثل «بالعاصمة» أو «فروانية»): تُوسَّع لمناطقها حتى
    # لا تُفقد المحافظات غير المدرجة كمنطقة (العاصمة أبرزها) ولا يبقى البحث ناقصًا.
    for gov in GOVERNORATE_AREA_NAMES:
        gov_norm = normalize_text(gov)
        if gov_norm in normalized and gov not in governorates:
            governorates.append(gov)
            for gov_area in GOVERNORATE_AREAS.get(gov, []):
                if gov_area not in areas:
                    areas.append(gov_area)
    # في النص المختلط (بقايا رسالة سابقة + إعلان) تُعطى الأولوية لمنطقة الإعلان:
    # المنطقة الواردة بعد علامة العملية القاطعة («للبيع»/«للإيجار») تُفضَّل وتُحصر النتائج فيها
    marker = "للبيع" if transaction == "للبيع" else ("للايجار" if transaction == "للإيجار" else "")
    if marker and len(areas) > 1:
        pos = normalized.find(marker)
        if pos >= 0:
            positioned = [(area, _first_pos(area, normalized)) for area in areas]
            after = [area for area, p in positioned if p >= 0 and p >= pos]
            if after:
                # حصر المناطق في منطقة الإعلان نفسها فقط (خلف العلامة القاطعة) —
                # لا تُطابق النتائج مناطق بقايا رسالة سابقة في نص مختلط
                areas = after

    # المساحة
    min_area, max_area, excluded = extract_area_range(raw_text)
    budget = parse_money(raw_text)
    rent_budget = budget if transaction == "مطلوب للإيجار" else None
    if rent_budget is not None and rent_budget > 10_000:
        rent_budget = None

    # الغرف
    bedrooms_match = re.search(r"([0-9]+)\s*(?:غرف|غرفه|غرفة)", normalized)

    # الدخل الإيجاري: «مؤجر ب 1200 شهرياً»، «دخله 20 الف»، «ايجارها 350» …
    income, income_period = extract_rental_income(raw_text)

    # الحالة ومميزات الموقع
    condition = [word for word in ("هدام", "صالح للسكن", "سكن المالك", "جديد") if normalize_text(word) in normalized]

    # ميزات الموقع (زاوية، شارعين، إلخ)
    site_features = detect_site_features(raw_text)

    # المميزات العامة
    features = [word for word in ("زاويه", "زاوية", "شارعين", "شارع واحد", "مصعد", "موقف", "مواقف", "قرب الخدمات") if normalize_text(word) in normalized]

    # القصد
    intent = "valuation" if any(word in normalized for word in ("قيم", "تقييم", "سعرها المناسب", "تسوى")) else "search"
    if intent == "valuation" and any(word in normalized for word in ("ابي", "مطلوب", "ابغى", "بحث")):
        intent = "search_and_value"

    return PropertyRequest(
        raw_text=raw_text,
        intent=intent,
        transaction=transaction,
        property_type=property_type,
        areas=areas,
        governorates=governorates,
        min_area=min_area,
        max_area=max_area,
        budget=budget if transaction != "مطلوب للإيجار" else None,
        rent_budget=rent_budget,
        bedrooms=int(bedrooms_match.group(1)) if bedrooms_match else None,
        income=income,
        income_period=income_period,
        condition=condition,
        features=list(set(features + site_features)),
        excluded_area_numbers=excluded,
    )
