from __future__ import annotations

import logging
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FRONTEND_DIR = ROOT / "frontend"

def resolve_log_level(name: str | None = None) -> int:
    """تحويل اسم مستوى (DEBUG/INFO/...) إلى ثابت logging، مع سقوط آمن لـ INFO."""
    return getattr(logging, (name or "").upper() or "INFO", logging.INFO)


def setup_logging(level: int | None = None) -> None:
    """تهيئة logging مركزي: مستوى قابل للضبط عبر ALFORAIJ_LOG_LEVEL.

    القيم المقبولة: DEBUG / INFO / WARNING / ERROR / CRITICAL (أي قيمة خاطئة
    تُهمل ويُستخدم INFO). تُستدعى عند استيراد config فيكون كل مسجل (logger)
    في التطبيق متصلًا بنفس الإعداد.
    """
    effective = level if level is not None else resolve_log_level(os.getenv("ALFORAIJ_LOG_LEVEL"))
    logging.basicConfig(
        level=effective,
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # ضمان تطبيق المستوى حتى عند وجود معالجات سابقة (basicConfig قد يتجاهل المستوى)
    logging.getLogger().setLevel(effective)


setup_logging()


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
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

AGENT_ROUTER_API_KEY = os.getenv("AGENT_ROUTER_API_KEY", "")
AGENT_ROUTER_API_URL = os.getenv("AGENT_ROUTER_API_URL", "https://api.agentrouter.org/v1/chat/completions")

# إرسال تنبيهات واتساب المجدولة (Meta Cloud API) — اختياري: غيابها يعطّل الإرسال
# التلقائي دون كسر الوكيل اليومي (تبقى أزرار wa.me اليدوية كما هي).
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_SENDER_NAME = os.getenv("WHATSAPP_SENDER_NAME", "فريق الفريج العقاري")

# AI Router — مزوّدات الذكاء الاصطناعي المجانية
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_AI_STUDIO_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
AI_PROVIDER_ORDER = os.getenv("AI_PROVIDER_ORDER", "freellmapi,ollama,gemini,openrouter,agentrouter")
FREELLMAPI_URL = os.getenv("FREELLMAPI_URL", "http://127.0.0.1:5050/v1")
FREELLMAPI_KEY = os.getenv("FREELLMAPI_KEY", "")
FREELLMAPI_MODEL = os.getenv("FREELLMAPI_MODEL", "google/gemini-2.0-flash")
SEED_LISTINGS_PATH = Path(os.getenv("ALFORAIJ_SEED_LISTINGS", DATA_DIR / "seed_listings.json"))
BOARD_HTML_PATH = Path(
    os.getenv(
        "ALFORAIJ_BOARD_HTML",
        ROOT.parent / "vs" / "site" / "index.html",
    )
)
