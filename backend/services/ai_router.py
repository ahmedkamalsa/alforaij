"""
AI Router — محوّل ذكي بين مزوّدات الذكاء الاصطناعي المجانية.

تسلسل الأولوية (Fallback Chain):
  1. FreeLLMAPI (مجاني — 34 مزوّد، 635 نموذج، 7.4B توكن/شهر، Fallback تلقائي)
  2. Ollama (محلي — مجاني بلا حدود، أسرع رد)
  3. Google AI Studio / Gemini (مجاني 1M توكن/يوم، ممتاز بالعربية)
  4. OpenRouter (مجاني — نماذج متعددة)
  5. AgentRouter (الخادم الحالي — كاحتياطي)

Usage:
    from backend.services.ai_router import ai_chat
    result = ai_chat("system prompt", "user message", response_format="json")
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
_FREELLMAPI_TIMEOUT = 5
_NVIDIA_TIMEOUT = 8
_OLLAMA_TIMEOUT = 5
_GEMINI_TIMEOUT = 5
_OPENROUTER_TIMEOUT = 5
_AGENTROUTER_TIMEOUT = 5


# ══════════════════════════════════════════════════════════════════
# 1. FreeLLMAPI — 34 providers, 635 models, 7.4B tokens/month
# ══════════════════════════════════════════════════════════════════
def _openai_compatible_chat(
    api_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    timeout: float,
    provider: str,
) -> dict | None:
    if not api_key:
        return None
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
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    return {"content": content, "provider": provider, "model": model}
    except Exception as e:
        logger.debug("%s unavailable: %s", provider, e)
    return None


def _try_nvidia_nim(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """Try NVIDIA NIM OpenAI-compatible endpoint for MiniMax M3."""
    api_key = os.getenv("NVIDIA_API_KEY", "")
    api_base = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
    model = model or os.getenv("NVIDIA_MODEL", "minimaxai/minimax-m3")
    return _openai_compatible_chat(
        f"{api_base}/chat/completions",
        api_key,
        model,
        system,
        user,
        temperature,
        _NVIDIA_TIMEOUT,
        "nvidia_nim",
    )


def _try_freellmapi(
    system: str,
    user: str,
    model: str = "",
    temperature: float = 0.4,
) -> dict | None:
    """Try FreeLLMAPI — unified gateway for 34 free providers.

    Requires:
      - FREELLMAPI_URL (default: http://127.0.0.1:5050/v1)
      - FREELLMAPI_KEY (from FreeLLMAPI dashboard tray popover)
    """
    api_url = os.getenv("FREELLMAPI_URL", "http://127.0.0.1:5050/v1").rstrip("/") + "/chat/completions"
    api_key = os.getenv("FREELLMAPI_KEY", "")
    model = model or os.getenv("FREELLMAPI_MODEL", "minimaxai/minimax-m3")
    return _openai_compatible_chat(
        api_url,
        api_key,
        model,
        system,
        user,
        temperature,
        _FREELLMAPI_TIMEOUT,
        "freellmapi",
    )


# ══════════════════════════════════════════════════════════════════
# 2. Ollama — local, free, unlimited
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
_DEFAULT_PROVIDERS = ["nvidia_nim", "freellmapi", "gemini", "openrouter", "ollama", "agentrouter"]

_PROVIDER_MAP = {
    "nvidia_nim": _try_nvidia_nim,
    "freellmapi": _try_freellmapi,
    "ollama": _try_ollama,
    "gemini": _try_gemini,
    "openrouter": _try_openrouter,
    "agentrouter": _try_agentrouter,
}

_last_attempts: list[dict[str, Any]] = []


def get_last_ai_attempts() -> list[dict[str, Any]]:
    return [dict(item) for item in _last_attempts]


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

    import time as _time
    attempts: list[dict[str, Any]] = []
    global _last_attempts
    _total_start = _time.time()
    _TOTAL_TIMEOUT = 10  # حد أقصى 10 ثوانٍ لكل المزوّدين مجتمعين
    for provider_name in providers:
        if _time.time() - _total_start > _TOTAL_TIMEOUT:
            logger.warning("AI total timeout reached (%.0fs) — stopping after %d providers", _TOTAL_TIMEOUT, providers.index(provider_name))
            break
        fn = _PROVIDER_MAP.get(provider_name)
        if not fn:
            continue
        started = _time.time()
        result = fn(system, user, model=model, temperature=temperature)
        elapsed_ms = round((_time.time() - started) * 1000, 1)
        attempts.append({
            "provider": provider_name,
            "status": "success" if result else "unavailable",
            "model": (result or {}).get("model") or model or "",
            "responseMs": elapsed_ms,
        })
        if result:
            result["attempts"] = [dict(item) for item in attempts]
            _last_attempts = [dict(item) for item in attempts]
            if use_cache:
                _set_cache(system, user, result)
            return result

    _last_attempts = [dict(item) for item in attempts]
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
        elif name == "nvidia_nim":
            status = "configured" if os.getenv("NVIDIA_API_KEY") else "no_key"
        elif name == "gemini":
            status = "configured" if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_KEY")) else "no_key"
        elif name == "openrouter":
            status = "configured" if os.getenv("OPENROUTER_API_KEY") else "no_key"
        elif name == "freellmapi":
            status = "configured" if os.getenv("FREELLMAPI_KEY") else "no_key"
        elif name == "agentrouter":
            from backend.config import AGENT_ROUTER_API_KEY
            status = "configured" if AGENT_ROUTER_API_KEY else "no_key"

        providers.append({"name": name, "status": status})
    return providers
