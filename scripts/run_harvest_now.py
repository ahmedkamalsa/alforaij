"""تشغيل حصاد المواقع فورًا: الوكيل اليومي الكامل مع المصادر الخارجية.

الاستخدام:
    PYTHONIOENCODING=utf-8 python scripts/run_harvest_now.py

يكتب الحالة النهائية إلى data/daily_agent_status.json (نفس ملف الوكيل)
ويطبع ملخصًا موجزًا على الطرفية.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.daily_update_agent import run_daily_update_agent

if __name__ == "__main__":
    status = run_daily_update_agent(include_external=True)
    summary = status.get("summary") or {}
    print(f"status: {status.get('status')}")
    print(f"error: {status.get('error', '')}")
    print(f"localListings: {summary.get('localListings')}")
    print(f"opportunitiesScored: {summary.get('opportunitiesScored')}")
    print(f"marketListingsHarvested: {summary.get('marketListingsHarvested')}")
    for step in status.get("steps", []):
        print(f"  step {step['name']}: {step['status']} {json.dumps(step.get('result') or {}, ensure_ascii=False)[:200]}")
    sys.exit(0 if status.get("status") == "success" else 1)
