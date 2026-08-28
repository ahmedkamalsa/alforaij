"""
AI Router — محوّل ذكي بين مزوّدات الذكاء الاصطناعي المجانية.

تسلسل الأولوية (Fallback Chain):
  1. Ollama (محلي — مجاني بلا حدود، أسرع رد)
  2. Google AI Studio / Gemini (مجاني 1M توكن/يوم، ممتاز بالعربية)
  3. OpenRouter (مجاني — نماذج متعددة)
  4. AgentRouter (الخادم الحالي — كاحتياطي)

Usage:
    from backend.services.ai_router import ai_chat
    result = ai_chat("ystem prompt", "user message", response_format="json")
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

# ── مهل الاتصال لكل مزوّد ──
_OLLAMA_TIMEOUT = 15
_GEMINI_TIMEOUT = 15
_OPENROUTER_TIMEOUT = 15
_AGENTROUTER_TIMEOUT = 12


# ══════════════════════════════════════════════════════════════════
# 1. Ollama —_local, free, unlimited
# ══════════════════════════════════════════════════════════════════
def _try_ollama(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """Try Ollama local model. Returns {"content": str} or None."""
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    if not ollama_url:
        return None
    model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("message", {}).get("content", "")
            if content:
                return {"content": content, "provider": "ollama", "model": model}
    except Exception as e:
        logger.debug("Ollama unavailable: %s", e)
    return None


# ══════════════════════════════════════════════════════════════════
# 2. Google AI Studio / Gemini — free 1M tokens/day
# ══════════════════════════════════════════════════════════════════
def _try_gemini(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """Try Google Gemini API. Returns {"content": str} or None."""
    api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_AI_STUDIO_KEY", "")
    if not api_key:
        return None
    model = model or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]},
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_GEMINI_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                content = parts[0].get("text", "") if parts else ""
                if content:
                    return {"content": content, "provider": "gemini", "model": model}
    except Exception as e:
        logger.debug("Gemini unavailable: %s", e)
    return None


# ══════════════════════════════════════════════════════════════════
# 3. OpenRouter — free tier models
# ══════════════════════════════════════════════════════════════════
def _try_openrouter(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """Try OpenRouter API. Returns {"content": str} or None."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    model = model or "meta-llama/llama-3.1-8b-instruct:free"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://alforaij.com",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_OPENROUTER_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    return {"content": content, "provider": "openrouter", "model": model}
    except Exception as e:
        logger.debug("OpenRouter unavailable: %s", e)
    return None


# ══════════════════════════════════════════════════════════════════
# 4. AgentRouter — existing fallback (current production)
# ══════════════════════════════════════════════════════════════════
def _try_agentrouter(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """Try existing agentrouter. Returns {"content": str} or None."""
    from backend.config import AGENT_ROUTER_API_KEY, AGENT_ROUTER_API_URL
    if not AGENT_ROUTER_API_KEY:
        return None
    model = model or "gpt-4o-mini"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        AGENT_ROUTER_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AGENT_ROUTER_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_AGENTROUTER_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    return {"content": content, "provider": "agentrouter", "model": model}
    except Exception as e:
        logger.warning("AgentRouter unavailable: %s", e)
    return None


# ══════════════════════════════════════════════════════════════════
# Fallback Cache — تخزين مؤقت ذكي للاستعلامات المتكررة
# ══════════════════════════════════════════════════════════════════
_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 3600  # ساعة واحدة


def _cache_key(system: str, user: str) -> str:
    """مفتاح تخزين مختصر."""
    import hashlib
    return hashlib.md5(f"{system[:200]}:{user[:500]}".encode()).hexdigest()


def _get_cached(system: str, user: str) -> dict | None:
    key = _cache_key(system, user)
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _set_cache(system: str, user: str, result: dict) -> None:
    key = _cache_key(system, user)
    _cache[key] = (time.time(), result)
    # تنظيف الكاش القديم
    if len(_cache) > 500:
        now = time.time()
        expired = [k for k, (ts, _) in _cache.items() if now - ts > _CACHE_TTL]
        for k in expired:
            del _cache[k]


# ══════════════════════════════════════════════════════════════════
# AI Chat — الواجهة الرئيسية
# ══════════════════════════════════════════════════════════════════
# ترتيب المزوّدين (يمكن تعديله عبر متغير البيئة AI_PROVIDER_ORDER)
_DEFAULT_PROVIDERS = ["ollama", "gemini", "openrouter", "agentrouter"]

_PROVIDER_MAP = {
    "ollama": _try_ollama,
    "gemini": _try_gemini,
    "openrouter": _try_openrouter,
    "agentrouter": _try_agentrouter,
}


def ai_chat(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
    response_format: str = "text",
    use_cache: bool = True,
) -> dict | None:
    """
    استدعاء ذكاء اصطناعي مع Fallback تلقائي وتخزين مؤقت.

    Returns:
        {"content": str, "provider": str, "model": str} or None
    """
    # فحص الكاش أولاً
    if use_cache:
        cached = _get_cached(system, user)
        if cached:
            cached["from_cache"] = True
            return cached

    # تحديد ترتيب المزوّدين
    order_env = os.getenv("AI_PROVIDER_ORDER", "")
    if order_env:
        providers = [p.strip() for p in order_env.split(",") if p.strip() in _PROVIDER_MAP]
    else:
        providers = list(_DEFAULT_PROVIDERS)

    for provider_name in providers:
        fn = _PROVIDER_MAP.get(provider_name)
        if not fn:
            continue
        result = fn(system, user, model=model, temperature=temperature)
        if result:
            if use_cache:
                _set_cache(system, user, result)
            return result

    logger.warning("All AI providers failed — no response available")
    return None


def ai_chat_json(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """استدعاء يعيد JSON مُحلّل — يضيف توجيه JSON للنظام."""
    enhanced_system = system + "\n\n IMPORTANT: Always respond with valid JSON only, no extra text."
    result = ai_chat(
        enhanced_system, user,
        model=model, temperature=temperature,
        use_cache=True,
    )
    if not result:
        return None
    content = result.get("content", "")
    try:
        parsed = json.loads(content)
        result["parsed"] = parsed
        return result
    except json.JSONDecodeError:
        # محاولة استخراج JSON من النص
        import re
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                parsed = json.loads(match.group())
                result["parsed"] = parsed
                return result
            except json.JSONDecodeError:
                pass
        result["parsed"] = None
        return result


def get_available_providers() -> list[dict[str, Any]]:
    """قائمة المزوّدين المتاحين مع الحالة."""
    providers = []
    for name in _DEFAULT_PROVIDERS:
        status = "configured"
        # فحص بسيط
        if name == "ollama":
            try:
                req = urllib.request.Request(
                    os.getenv("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/tags",
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    models = [m.get("name", "") for m in data.get("models", [])]
                    status = "available" if models else "running_no_models"
            except Exception:
                status = "offline"
        elif name == "gemini":
            status = "configured" if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_KEY")) else "no_key"
        elif name == "openrouter":
            status = "configured" if os.getenv("OPENROUTER_API_KEY") else "no_key"
        elif name == "agentrouter":
            from backend.config import AGENT_ROUTER_API_KEY
            status = "configured" if AGENT_ROUTER_API_KEY else "no_key"

        providers.append({"name": name, "status": status})
    return providers
