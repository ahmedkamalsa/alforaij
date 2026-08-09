import re
import json
from pathlib import Path
from time import sleep

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / 'data' / 'refined_abdullah_analyze.json'
OUT = ROOT / 'data' / 'refined_abdullah_analyze_with_contacts.json'

phone_re = re.compile(r'(?:\+965[\s-]?\d{7,8}|\b5\d{7}\b|\b6\d{7}\b|\b9\d{7}\b)')
email_re = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')

if not IN.exists():
    print('Input file not found:', IN)
    raise SystemExit(1)

with IN.open(encoding='utf-8') as f:
    report = json.load(f)

results = report.get('results', [])

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    for i, item in enumerate(results, 1):
        url = item.get('originalUrl')
        contacts = {'phones': [], 'emails': [], 'tel_links': [], 'mailto_links': []}
        if not url:
            item['contacts'] = contacts
            continue
        try:
            print(f'[{i}/{len(results)}] Visiting', url)
            page.goto(url, timeout=20000)
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            content = page.content()

            # find tel/mailto links
            for a in page.query_selector_all('a'):
                href = a.get_attribute('href') or ''
                text = a.inner_text() or ''
                if href.startswith('tel:'):
                    tel = href.split(':', 1)[1].strip()
                    if tel not in contacts['tel_links']:
                        contacts['tel_links'].append(tel)
                if href.startswith('mailto:'):
                    m = href.split(':', 1)[1].strip()
                    if m not in contacts['mailto_links']:
                        contacts['mailto_links'].append(m)
                # sometimes phones are in text
                for match in phone_re.findall(text):
                    if match not in contacts['phones']:
                        contacts['phones'].append(match)
                for match in email_re.findall(text):
                    if match not in contacts['emails']:
                        contacts['emails'].append(match)

            # regex over whole content
            for match in phone_re.findall(content):
                if match not in contacts['phones']:
                    contacts['phones'].append(match)
            for match in email_re.findall(content):
                if match not in contacts['emails']:
                    contacts['emails'].append(match)

            # small delay between pages
            sleep(0.5)
        except Exception as e:
            print('Visit failed for', url, 'error:', e)
        item['contacts'] = contacts

    # write output
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    browser.close()

print('Done — contacts written to', OUT)
