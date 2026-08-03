from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FRONTEND_DIR = ROOT / "frontend"

HOST = os.getenv("ALFORAIJ_ASSISTANT_HOST", "127.0.0.1")
PORT = int(os.getenv("ALFORAIJ_ASSISTANT_PORT", "8000"))

SEED_LISTINGS_PATH = Path(os.getenv("ALFORAIJ_SEED_LISTINGS", DATA_DIR / "seed_listings.json"))
BOARD_HTML_PATH = Path(
    os.getenv(
        "ALFORAIJ_BOARD_HTML",
        ROOT.parent / "vs" / "site" / "index.html",
    )
)

