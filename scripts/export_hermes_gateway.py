#!/usr/bin/env python3
"""تصدير حالة hermes gateway إلى static-data للواجهات الثابتة."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.hermes_gateway import get_hermes_gateway_status

# 1) frontend/static-data (المستخدم في التصدير اليومي)
out1 = ROOT / "frontend" / "static-data" / "hermes-gateway.json"
# 2) alforaijboard/site/static-data (المنشور على GitHub Pages)
out2 = ROOT.parent / "alforaijboard" / "site" / "static-data" / "hermes-gateway.json"
# 3) alforaijboard/static-data (مرآة)
out3 = ROOT.parent / "alforaijboard" / "static-data" / "hermes-gateway.json"

status = get_hermes_gateway_status()
payload = json.dumps(status, ensure_ascii=False, indent=2)

for out in (out1, out2, out3):
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Wrote {out} — pid={status.get('pid')} running={status.get('running')}")
    except Exception as e:
        print(f"Failed {out}: {e}", file=sys.stderr)

print(json.dumps(status, ensure_ascii=False, indent=2))
