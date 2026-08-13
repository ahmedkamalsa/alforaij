"""فحص تباين ألوان تلقائي (WCAG AA) لبطاقات النتائج والشرائح في الوضعين الفاتح والداكن.

يقيس نسبة التباين الفعلية بين لون النص وخلفيته الفعالة:
- دمج الألوان الشفافة (rgba) مع الطبقات تحتها حتى الخلفية الأساسية للصفحة.
- أخذ التدرجات الخطية (linear-gradient) بعين الاعتبار بفحص أسوأ نقطة توقف.
- تصنيف النص: عادي ≥ 4.5:1 ، كبير (≥24px أو ≥18.66px عريض) ≥ 3:1.

النطاق: بطاقات النتائج (.result-card بكافة أنواعها) والشرائح
(.results-source-chip, .opp-platform-chip, .filter-chip, .area-chip, .pill).

الاستخدام:
    python tests/playwright/contrast_audit.py [base_url]
الخروج: 0 عند النجاح، 1 عند وجود مخالفات تباين.
"""
from __future__ import annotations

import json
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
  // كل ألوان التوقف في تدرج خطي (أول طبقة خلفية مرسومة)
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
  const hasDirectText = (el) =>
    [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 0);
  const cardSel = '.result-card';
  const chipSel = '.results-source-chip, .opp-platform-chip, .filter-chip, .area-chip, .pill';
  const targets = [];
  document.querySelectorAll(cardSel).forEach((card) => {
    if (card.textContent.trim().length === 0) return;
    targets.push({ el: card, label: 'بطاقة نتيجة' });
    card.querySelectorAll('*').forEach((el) => {
      if (hasDirectText(el)) targets.push({ el, label: 'نص بطاقة' });
    });
  });
  document.querySelectorAll(chipSel).forEach((chip) => {
    if (chip.textContent.trim().length === 0) return;
    targets.push({ el: chip, label: 'شريحة' });
    chip.querySelectorAll('b, strong, span').forEach((el) => {
      if (hasDirectText(el)) targets.push({ el, label: 'نص شريحة' });
    });
  });
  const base = toRgb(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()) ||
               { r: 11, g: 18, b: 32, a: 1 };
  const seen = new Set();
  const results = [];
  for (const t of targets) {
    const cs = getComputedStyle(t.el);
    const key = t.label + '|' + (t.el.className ? String(t.el.className).split(' ').slice(0, 2).join('.') : t.el.tagName) + '|' + cs.color + '|' + (t.el.textContent || '').trim().slice(0, 18);
    if (seen.has(key)) continue;
    seen.add(key);
    const fg = toRgb(cs.color) || { r: 255, g: 255, b: 255, a: 1 };
    const bgs = resolveBgs(t.el, base);
    // أسوأ حالة: أقل نسبة تباين بين كل الخلفيات المحتملة
    let r = Infinity, worstBg = bgs[0];
    for (const bg of bgs) {
      const rr = ratio(blend(fg, bg), bg);
      if (rr < r) { r = rr; worstBg = bg; }
    }
    const size = parseFloat(cs.fontSize) || 16;
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const isLarge = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = isLarge ? 3 : 4.5;
    const cls = (t.el.className && typeof t.el.className === 'string') ? t.el.className.split(' ').slice(0, 3).join('.') : t.el.tagName;
    results.push({
      ok: r >= need,
      label: t.label,
      cls: cls,
      text: (t.el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
      ratio: Math.round(r * 100) / 100,
      need: need,
      fg: cs.color,
      bg: `rgb(${Math.round(worstBg.r)},${Math.round(worstBg.g)},${Math.round(worstBg.b)})`,
      size: size,
      weight: weight,
    });
  }
  return results;
}
"""


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1200)

        # نتائج حقيقية لتوليد بطاقات وشرائح
        page.click("[data-main-tab='search']")
        page.wait_for_timeout(500)
        chat = page.locator("#chatInput")
        chat.fill("بيت للبيع في الفردوس 300 متر")
        page.keyboard.press("Enter")
        page.wait_for_timeout(35000)

        audits = {"داكن": "dark", "فاتح": "light"}
        all_failures: list[dict] = []

        for theme_name, theme in audits.items():
            page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            page.wait_for_timeout(800)
            results = page.evaluate(AUDIT_JS)
            fails = [r for r in results if not r["ok"]]
            print(f"\n===== الوضع {theme_name} — {len(results)} عنصر مفحوص =====")
            if fails:
                for f in fails:
                    print(f"  ❌ [{theme_name}] {f['label']} [{f['cls']}] «{f['text']}» — {f['ratio']}:1 (مطلوب {f['need']}:1) — نص {f['fg']} على {f['bg']} ({f['size']}px/{f['weight']})")
                    f["theme"] = theme_name
                    all_failures.append(f)
            else:
                print("  ✅ لا مخالفات تباين")
            # تأكيد أن الوضع فعلاً تغيّر
            bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            print(f"  (خلفية الصفحة: {bg})")

        browser.close()

    print("\n" + "=" * 60)
    if all_failures:
        print(f"النتيجة: فشل — {len(all_failures)} مخالفة تباين WCAG AA")
        print("=" * 60)
        return 1
    print("النتيجة: نجاح — كل الألوان مطابقة WCAG AA في الوضعين")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
