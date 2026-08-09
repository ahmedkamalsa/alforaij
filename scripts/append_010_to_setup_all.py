"""إلحاق supabase/migrations/010_market_listings.sql إلى supabase/setup_all.sql بأمان.

يحافظ على ترميز الملف الأصلي: BOM UTF-8 + أسطر CRLF (نمط مستودع Windows).
التكرار آمن: إذا وُجدت علامة 010 في الملف لا يُضاف شيء.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "010_market_listings.sql"
TARGET = ROOT / "supabase" / "setup_all.sql"

target_bytes = TARGET.read_bytes()
if b"-- 010_market_listings" in target_bytes:
    print("already-appended")
    raise SystemExit(0)

body_bytes = MIGRATION.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n").strip(b"\r\n")

separator = b"\r\n\r\n-- =====================================================================\r\n"
new_bytes = target_bytes.rstrip(b"\r\n") + separator + body_bytes + b"\r\n"
TARGET.write_bytes(new_bytes)
print("appended-ok")
