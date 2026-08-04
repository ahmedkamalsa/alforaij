from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FRONTEND_DIR = ROOT / "frontend"


def load_local_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

HOST = os.getenv("ALFORAIJ_ASSISTANT_HOST", "127.0.0.1")
PORT = int(os.getenv("ALFORAIJ_ASSISTANT_PORT", "8000"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

SEED_LISTINGS_PATH = Path(os.getenv("ALFORAIJ_SEED_LISTINGS", DATA_DIR / "seed_listings.json"))
BOARD_HTML_PATH = Path(
    os.getenv(
        "ALFORAIJ_BOARD_HTML",
        ROOT.parent / "vs" / "site" / "index.html",
    )
)
