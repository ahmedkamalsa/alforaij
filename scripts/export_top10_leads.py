import json
import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
INPUT = DATA_DIR / 'refined_abdullah_analyze_with_contacts.json'
OUT_CSV = DATA_DIR / 'top10_similar_leads.csv'
OUT_JSON = DATA_DIR / 'top10_similar_leads.json'

with INPUT.open('r', encoding='utf-8') as f:
    data = json.load(f)

results = data.get('results', [])[:10]

rows = []
for r in results:
    code = r.get('code')
    area = r.get('area')
    ptype = r.get('propertyType')
    transaction = r.get('transaction')
    price = r.get('price')
    priceText = r.get('priceText')
    space = r.get('space')
    date = r.get('publishedDate')
    url = r.get('originalUrl')
    phones = []
    emails = []
    contacts = r.get('contacts') or {}
    if contacts:
        phones = contacts.get('phones') or []
        emails = contacts.get('emails') or []
    # fallback: try to extract phones from summary text
    if not phones:
        summary = r.get('summary','') or ''
        import re
        phones = re.findall(r"(?:\+965)?\s?\d{7,8}", summary)[:3]
    message = f"السلام عليكم، معك [اسمك]. لدي عقار {transaction or ''} في {area or ''} — المساحة {space or ''}م — السعر المرجعي {priceText or price or ''}. هل لديكم مشترين مهتمين؟"
    rows.append({
        'code': code,
        'area': area,
        'propertyType': ptype,
        'transaction': transaction,
        'price': price,
        'priceText': priceText,
        'space': space,
        'publishedDate': date,
        'url': url,
        'thumbnail': '',
        'phones': '|'.join(map(str,phones)) if phones else '',
        'emails': '|'.join(emails) if emails else '',
        'message': message
    })

# write CSV
with OUT_CSV.open('w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['code','area','propertyType','transaction','price','priceText','space','publishedDate','url','thumbnail','phones','emails','message'])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

# write JSON
with OUT_JSON.open('w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(rows)} leads to {OUT_CSV} and {OUT_JSON}")