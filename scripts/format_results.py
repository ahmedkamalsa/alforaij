import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
p = r'C:\Users\hello\AppData\Local\Temp\1786022991852-copilot-tool-output-14344-b4e85f04-2150-485b-8b63-fd643c78fe18.txt'
with open(p, encoding='utf-8') as f:
    s = f.read()
j = json.loads(s)
res = j.get('results', [])[:20]
for i, it in enumerate(res, 1):
    print(f"=== إعلان {i}: {it.get('code','-')} — {it.get('area','-')} — {it.get('transaction','-')}")
    print('1) الإعلانات المماثلة:')
    comps = it.get('comparables', [])
    if comps:
        for c in comps:
            print(f" - {c.get('code','?')} | {c.get('area','-')} | {c.get('priceText') or c.get('price')} | تاريخ: {c.get('date') or '-'} | {c.get('url') or '-'}")
    else:
        print(' - لا توجد مقارنات كافية')
    print()
    print('2) رسالة جاهزة للمتعامل / صاحب الإعلان:')
    print('السلام عليكم،')
    print(f"أرغب في الاستفسار عن الإعلان {it.get('code')} في {it.get('area')}. هل السعر {it.get('priceText')} نهائي؟ هل الشقة أرضي وتحتوي 4 غرف؟ هل يوجد رقم للتواصل أو موعد لمعاينة؟")
    print('شكراً.')
    print()
    print('3) التقييم والمصادر:')
    print(f" - حكم السعر: {it.get('valuationLabel')}")
    print(f" - سبب التقييم: {it.get('valuationReason')}")
    ns = it.get('numberSources', {})
    med = ns.get('marketMedian')
    if isinstance(med, dict):
        medv = med.get('value')
    else:
        medv = med
    print(f" - وسيط المقارنات: {medv}")
    print(f" - نسبة السعر للوسيط: {it.get('priceRatio')}")
    print(f" - الثقة: {it.get('confidence')}")
    print(' - أدلة / مصادر:')
    for k, v in ns.items():
        if isinstance(v, dict):
            disp = v.get('display') or v.get('value')
            print(f"   * {k}: {disp} (من: {v.get('source')})")
    print('\n')
