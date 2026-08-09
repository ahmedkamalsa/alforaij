import json
from pathlib import Path
import sys

# ensure project root is in path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.models import PropertyRequest
from backend.services.supabase_store import persist_analysis, is_configured

p = ROOT / 'data' / 'refined_abdullah_analyze.json'
if not p.exists():
    print('ERROR: analyze JSON not found at', p)
    raise SystemExit(1)

with open(p, encoding='utf-8') as f:
    j = json.load(f)

req_dict = j.get('request') or {}
# construct PropertyRequest — only include keys that match dataclass
req = PropertyRequest(**{k: v for k, v in req_dict.items() if k in PropertyRequest.__dataclass_fields__})
report = j
statuses = j.get('sourceStatus', [])

print('Supabase configured:', is_configured())
if not is_configured():
    print('Supabase not configured — aborting persist.')
    raise SystemExit(2)

try:
    result = persist_analysis(req, report, statuses)
    print('Persist result:', result)
except Exception as e:
    print('Persist failed:', repr(e))
    raise
