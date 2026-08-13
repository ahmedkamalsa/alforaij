"""فحص تباين ألوان تلقائي (WCAG AA) لكل عناصر الواجهة في الوضعين الفاتح والداكن.

النطاق: كل النصوص المرئية في الصفحة (التبويبات، الشريط العلوي، الجداول، الأزرار،
الشرائح، بطاقات النتائج، الرسائل…) + حقول الإدخال (نص مكتوب + placeholder)،
مع فتح درج تفاصيل لوحة السوق لفحص محتواه أيضًا.

يقيس نسبة التباين الفعلية بين لون النص وخلفيته الفعالة:
- دمج الألوان الشفافة (rgba) مع الطبقات تحتها حتى الخلفية الأساسية للصفحة.
- أخذ التدرجات الخطية بعين الاعتبار بفحص أسوأ نقطة توقف (يدعم rgba وhex).
- تصنيف النص: عادي ≥ 4.5:1 ، كبير (≥24px أو ≥18.66px عريض) ≥ 3:1.
- العناصر فوق صورة خلفية (url) تُفحص على الطبقة الأساسية وتُبلّغ كتحذير
  «غير قابل للقياس الكامل» دون أن تُسقط الفحص.

الاستخدام:
    python tests/playwright/contrast_audit.py [base_url]
الخروج: 0 عند النجاح، 1 عند وجود مخالفات تباين.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/")

# نصوص الفاحص داخل الصفحة (تعمل في سياق المتصفح)
AUDIT_JS = r"""
() => {
  const toRgb = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lin = (v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const blend = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
  });
  const hexToRgb = (h) => {
    const m = h.match(/^#([0-9a-f]{6}|[0-9a-f]{3})$/i);
    if (!m) return null;
    let s = m[1];
    if (s.length === 3) s = s.split('').map((x) => x + x).join('');
    return { r: parseInt(s.slice(0, 2), 16), g: parseInt(s.slice(2, 4), 16), b: parseInt(s.slice(4, 6), 16), a: 1 };
  };
  // أول طبقة كاملة: من البداية حتى إغلاق أول دالة (gradient/url) بتتبع الأقواس
  const firstLayer = (bgImage) => {
    let depth = 0;
    for (let i = 0; i < bgImage.length; i++) {
      const ch = bgImage[i];
      if (ch === '(') depth++;
      else if (ch === ')') { depth--; if (depth === 0) return bgImage.slice(0, i + 1); }
    }
    return bgImage;
  };
  const layerHasImage = (bgImage) => /url\(/.test(firstLayer(bgImage || ''));
  // كل ألوان التوقف في تدرج خطي (أول طبقة خلفية مرسومة) — يدعم rgba() و hex
  const gradStops = (bgImage) => {
    const out = [];
    if (!bgImage || bgImage === 'none') return out;
    const layer = firstLayer(bgImage);
    for (const c of layer.match(/rgba?\([^)]+\)|#[0-9a-f]{3,8}/gi) || []) {
      const p = toRgb(c) || hexToRgb(c);
      if (p) out.push(p);
    }
    return out;
  };
  // خلفيات محتملة (قد تكون أكثر من واحدة عند وجود تدرجات):
  // تُطوى سلسلة الآباء من الخارج إلى الداخل (html → body → … → العنصر)
  const resolveBgs = (el, base) => {
    let chain = [];
    let node = el;
    while (node && node !== document.documentElement.parentNode) {
      chain.push(node);
      node = node.parentElement;
    }
    chain.reverse(); // من html نزولاً إلى العنصر
    let cands = [base];
    for (const n of chain) {
      const cs = getComputedStyle(n);
      const c = toRgb(cs.backgroundColor);
      const stops = gradStops(cs.backgroundImage);
      if (stops.length) {
        const next = [];
        for (const cand of cands) for (const s of stops) next.push(blend(s, cand));
        cands = next.slice(0, 16);
      }
      if (c && c.a > 0) cands = cands.map((cand) => blend(c, cand));
    }
    return cands.length ? cands : [base];
  };
  const ratio = (fg, bg) => {
    const L1 = lum(fg), L2 = lum(bg);
    const hi = Math.max(L1, L2), lo = Math.min(L1, L2);
    return (hi + 0.05) / (lo + 0.05);
  };
  const isVisible = (el) => {
    if (el.closest('[hidden]')) return false;
    if (el.getClientRects().length > 0) {
      const cs = getComputedStyle(el);
      return cs.display !== 'none' && cs.visibility !== 'hidden';
    }
    // محتوى <details> مغلق قابل للفتح — يُفحص أيضًا لأنه سيظهر عند الفتح
    return !!el.closest('details') && getComputedStyle(el).display !== 'none';
  };
  const hasOwnText = (el) =>
    [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 0);
  // هل أي طبقة خلفية (أو ::before/::after) في سلسلة الآباء تحتوي صورة url()؟
  const hasImageLayer = (el) => {
    let node = el;
    while (node && node !== document.documentElement.parentNode) {
      for (const pseudo of ['', '::before', '::after']) {
        if (layerHasImage(getComputedStyle(node, pseudo).backgroundImage)) return true;
      }
      node = node.parentElement;
    }
    return false;
  };
  const SKIP_TAGS = new Set(['script', 'style', 'canvas', 'svg', 'path', 'circle', 'line', 'polyline', 'polygon', 'rect', 'defs', 'title', 'meta', 'link', 'br', 'hr', 'img', 'option', 'template']);
  const targets = [];
  // 1) كل النصوص المرئية (أعمق عنصر يحمل نصًا مباشرًا)
  document.querySelectorAll('body *').forEach((el) => {
    if (SKIP_TAGS.has(el.tagName.toLowerCase())) return;
    if (el.closest('.source-trust-tip')) return;
    if (!isVisible(el)) return;
    if (!hasOwnText(el)) return;
    targets.push({ el, kind: 'نص' });
  });
  // 2) حقول الإدخال: لون النص المكتوب + placeholder
  document.querySelectorAll('body input, body textarea, body select').forEach((el) => {
    if (!isVisible(el)) return;
    targets.push({ el, kind: 'حقل', hasPlaceholder: !!(el.getAttribute && el.getAttribute('placeholder')) });
  });
  const base = toRgb(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()) ||
               { r: 11, g: 18, b: 32, a: 1 };
  const seen = new Set();
  const results = [];
  const emit = (el, kind, fgColor, bgCands, extra = {}) => {
    const fg = toRgb(fgColor) || { r: 255, g: 255, b: 255, a: 1 };
    let r = Infinity, worstBg = bgCands[0];
    for (const bg of bgCands) {
      const rr = ratio(blend(fg, bg), bg);
      if (rr < r) { r = rr; worstBg = bg; }
    }
    const cs = getComputedStyle(el);
    const size = parseFloat(cs.fontSize) || 16;
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const isLarge = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = isLarge ? 3 : 4.5;
    const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 3).join('.') : el.tagName;
    const text = (el.getAttribute && el.getAttribute('placeholder')) ||
                 (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    const key = kind + '|' + cls + '|' + fgColor + '|' + text.slice(0, 18);
    if (seen.has(key)) return;
    seen.add(key);
    const img = hasImageLayer(el);
    results.push({
      ok: r >= need,
      img: img,
      kind: kind,
      cls: cls,
      text: text,
      ratio: Math.round(r * 100) / 100,
      need: need,
      fg: fgColor,
      bg: `rgb(${Math.round(worstBg.r)},${Math.round(worstBg.g)},${Math.round(worstBg.b)})`,
      size: size,
      weight: weight,
      ...extra,
    });
  };
  for (const t of targets) {
    const cs = getComputedStyle(t.el);
    const bgs = resolveBgs(t.el, base);
    if (t.kind === 'حقل') {
      emit(t.el, 'حقل', cs.color, bgs, { hasPlaceholder: t.hasPlaceholder });
      if (t.hasPlaceholder) {
        const ph = getComputedStyle(t.el, '::placeholder').color;
        if (ph && ph !== 'rgba(0, 0, 0, 0)') emit(t.el, 'placeholder', ph, bgs);
      }
    } else {
      emit(t.el, 'نص', cs.color, bgs);
    }
  }
  return results;
}
"""


def main() -> int:
    TABS = [
        ("search", "البحث", 1.2),
        ("opportunities", "أفضل الفرص", 3.0),
        ("board", "لوحة السوق", 3.0),
        ("insights", "تحليلات السوق", 5.0),
        ("developments", "التطورات", 4.0),
        ("sources", "المصادر", 3.0),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1200)

        # نتائج حقيقية لتوليد بطاقات وشرائح ورسائل
        page.click("[data-main-tab='search']")
        page.wait_for_timeout(500)
        chat = page.locator("#chatInput")
        chat.fill("بيت للبيع في الفردوس 300 متر")
        page.keyboard.press("Enter")
        page.wait_for_timeout(35000)

        all_failures: list[dict] = []
        all_warnings: list[dict] = []
        audits = {"داكن": "dark", "فاتح": "light"}

        for theme_name, theme in audits.items():
            page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            page.wait_for_timeout(800)
            total_checked = 0
            theme_fails = 0
            for tab, tab_name, wait_s in TABS:
                page.click(f"[data-main-tab='{tab}']")
                page.wait_for_timeout(int(wait_s * 1000))
                results = page.evaluate(AUDIT_JS)
                total_checked += len(results)
                for r in results:
                    if not r["ok"]:
                        r["theme"] = theme_name
                        r["tab"] = tab_name
                        all_failures.append(r)
                        theme_fails += 1
                    elif r["img"]:
                        r["theme"] = theme_name
                        r["tab"] = tab_name
                        all_warnings.append(r)
                # درج تفاصيل لوحة السوق: نفتحه لفحص محتواه ثم نغلقه
                if tab == "board":
                    stat = page.locator("button.board-stat, .board-stat").first
                    if stat.count() > 0:
                        stat.click()
                        page.wait_for_timeout(1200)
                        results = page.evaluate(AUDIT_JS)
                        total_checked += len(results)
                        for r in results:
                            if not r["ok"]:
                                r["theme"] = theme_name
                                r["tab"] = "درج التفاصيل"
                                all_failures.append(r)
                                theme_fails += 1
                            elif r["img"]:
                                r["theme"] = theme_name
                                r["tab"] = "درج التفاصيل"
                                all_warnings.append(r)
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(700)
            print(f"\n===== الوضع {theme_name} — {total_checked} عنصر مفحوص عبر كل التبويبات =====")
            print(f"  مخالفات: {theme_fails}  |  تحذيرات فوق صور: {sum(1 for w in all_warnings if w['theme'] == theme_name)}")
            bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            print(f"  (خلفية الصفحة: {bg})")

        browser.close()

    # طباعة المخالفات مكررة فقط
    unique_fails: list[dict] = []
    seen_fails: set = set()
    for f in all_failures:
        key = (f["theme"], f["kind"], f["cls"], f["fg"], f["bg"], f["text"][:18])
        if key not in seen_fails:
            seen_fails.add(key)
            unique_fails.append(f)

    print("\n" + "=" * 70)
    if unique_fails:
        print(f"النتيجة: فشل — {len(unique_fails)} مخالفة تباين WCAG AA (من {len(all_failures)} تكرارًا)")
        for f in unique_fails:
            tag = f["tab"]
            print(f"  ❌ [{f['theme']}|{tag}] {f['kind']} [{f['cls']}] «{f['text']}» — {f['ratio']}:1 (مطلوب {f['need']}:1) — {f['fg']} على {f['bg']} ({f['size']}px/{f['weight']})")
        print("=" * 70)
        return 1

    print(f"النتيجة: نجاح — كل الألوان مطابقة WCAG AA في الوضعين (تحذيرات فوق صور: {len(all_warnings)})")
    for w in all_warnings:
        print(f"  ⚠️ [{w['theme']}|{w['tab']}] {w['kind']} [{w['cls']}] «{w['text']}» — {w['ratio']}:1 فوق صورة خلفية (تحقق بصريًا)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
