"""
Apply Supabase migrations remotely via Management API (no CLI).
Uses SUPABASE_ACCESS_TOKEN + SUPABASE_URL from .env.

Usage:
    python scripts/apply_migrations_remote.py                  # apply all migrations
    python scripts/apply_migrations_remote.py 005              # apply specific migration
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main() -> None:
    env = _load_env(Path(__file__).resolve().parents[1] / ".env")
    token = env.get("SUPABASE_ACCESS_TOKEN", "")
    url = env.get("SUPABASE_URL", "").rstrip("/")
    ref = urllib.parse.urlparse(url).hostname.split(".")[0] if url else ""

    if not token or not ref:
        print("ERROR: SUPABASE_ACCESS_TOKEN or SUPABASE_URL not found in .env")
        sys.exit(1)

    migrations_dir = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    filenames = sorted(f.name for f in migrations_dir.glob("*.sql"))
    target = sys.argv[1] if len(sys.argv) > 1 else None

    api_url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) alforaij/1.0",
        "Accept": "application/json",
    }

    for fname in filenames:
        if target and target not in fname:
            continue
        sql_path = migrations_dir / fname
        sql = sql_path.read_text(encoding="utf-8")
        statements = [
            "\n".join(
                line for line in chunk.splitlines()
                if line.strip() and not line.strip().startswith("--")
            ).strip()
            for chunk in sql.split(";")
        ]
        statements = [s for s in statements if s]
        if not statements:
            print(f"{fname}: no statements to apply")
            continue

        print(f"{fname}: applying {len(statements)} statements...", end=" ")
        sys.stdout.flush()
        body = json.dumps({"query": sql}).encode()
        req = urllib.request.Request(api_url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = resp.read().decode("utf-8", errors="replace")
            print(f"OK ({result[:60]})")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"FAIL HTTP {exc.code}: {detail[:200]}")
            if target:
                sys.exit(1)
        except Exception as exc:
            print(f"FAIL: {exc}")
            if target:
                sys.exit(1)

    print("\nAll migrations applied.")


if __name__ == "__main__":
    main()