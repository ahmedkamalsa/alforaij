"""Tests for AI Router — fallback chain, caching, provider detection."""
from __future__ import annotations

import json
import os
import time
import unittest
from unittest.mock import patch, MagicMock

# Patch _PROVIDER_MAP before importing ai_chat so the module-level refs are replaced
import backend.services.ai_router as _mod


class TestCacheLogic(unittest.TestCase):
    """Test the caching layer independently of providers."""

    def setUp(self):
        _mod._cache.clear()

    def test_cache_key_deterministic(self):
        k1 = _mod._cache_key("sys", "user")
        k2 = _mod._cache_key("sys", "user")
        self.assertEqual(k1, k2)

    def test_cache_key_differs_by_input(self):
        k1 = _mod._cache_key("sys", "user1")
        k2 = _mod._cache_key("sys", "user2")
        self.assertNotEqual(k1, k2)

    def test_set_and_get_cache(self):
        result = {"content": "hello", "provider": "test"}
        _mod._set_cache("sys", "user", result)
        cached = _mod._get_cached("sys", "user")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["content"], "hello")

    def test_cache_expired(self):
        result = {"content": "hello", "provider": "test"}
        key = _mod._cache_key("sys", "user")
        _mod._cache[key] = (time.time() - 7200, result)  # 2 hours ago
        cached = _mod._get_cached("sys", "user")
        self.assertIsNone(cached)


class TestProviderFallback(unittest.TestCase):
    """Test that ai_chat falls through providers correctly."""

    def setUp(self):
        _mod._cache.clear()
        # Save original map
        self._orig_map = dict(_mod._PROVIDER_MAP)
        self._orig_providers = list(_mod._DEFAULT_PROVIDERS)

    def tearDown(self):
        # Restore
        _mod._PROVIDER_MAP.clear()
        _mod._PROVIDER_MAP.update(self._orig_map)
        _mod._DEFAULT_PROVIDERS[:] = self._orig_providers

    def _setup_providers(self, order, results):
        """Configure provider order and mock results."""
        _mod._DEFAULT_PROVIDERS[:] = order
        for name in _mod._PROVIDER_MAP:
            if name in results:
                _mod._PROVIDER_MAP[name] = MagicMock(return_value=results[name])
            else:
                _mod._PROVIDER_MAP[name] = MagicMock(return_value=None)

    @patch.dict(os.environ, {"OLLAMA_URL": "", "GEMINI_API_KEY": "", "OPENROUTER_API_KEY": "", "AGENT_ROUTER_API_KEY": ""})
    def test_all_providers_unavailable_returns_none(self):
        self._setup_providers(["ollama", "gemini", "openrouter", "agentrouter"], {})
        result = _mod.ai_chat("system", "user", use_cache=False)
        self.assertIsNone(result)

    def test_first_provider_success(self):
        self._setup_providers(["ollama"], {"ollama": {"content": "from ollama", "provider": "ollama", "model": "test"}})
        result = _mod.ai_chat("system", "user", use_cache=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "ollama")

    def test_fallback_to_second_provider(self):
        self._setup_providers(
            ["ollama", "gemini"],
            {"gemini": {"content": "from gemini", "provider": "gemini", "model": "test"}},
        )
        result = _mod.ai_chat("system", "user", use_cache=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "gemini")
        _mod._PROVIDER_MAP["ollama"].assert_called_once()
        _mod._PROVIDER_MAP["gemini"].assert_called_once()

    def test_fallback_to_third_provider(self):
        self._setup_providers(
            ["ollama", "gemini", "openrouter"],
            {"openrouter": {"content": "from or", "provider": "openrouter", "model": "test"}},
        )
        result = _mod.ai_chat("system", "user", use_cache=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "openrouter")

    def test_fallback_to_fourth_provider(self):
        self._setup_providers(
            ["ollama", "gemini", "openrouter", "agentrouter"],
            {"agentrouter": {"content": "from ar", "provider": "agentrouter", "model": "test"}},
        )
        result = _mod.ai_chat("system", "user", use_cache=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "agentrouter")

    def test_all_fail_returns_none(self):
        self._setup_providers(["ollama", "gemini", "openrouter", "agentrouter"], {})
        result = _mod.ai_chat("system", "user", use_cache=False)
        self.assertIsNone(result)

    def test_caching_works(self):
        self._setup_providers(["ollama"], {"ollama": {"content": "cached", "provider": "ollama", "model": "test"}})
        r1 = _mod.ai_chat("sys", "usr", use_cache=True)
        self.assertFalse(r1.get("from_cache"))
        r2 = _mod.ai_chat("sys", "usr", use_cache=True)
        self.assertTrue(r2.get("from_cache"))
        _mod._PROVIDER_MAP["ollama"].assert_called_once()

    def test_custom_order_respected(self):
        self._setup_providers(
            ["gemini", "ollama"],
            {
                "gemini": {"content": "gemini first", "provider": "gemini", "model": "test"},
                "ollama": {"content": "ollama second", "provider": "ollama", "model": "test"},
            },
        )
        result = _mod.ai_chat("sys", "usr", use_cache=False)
        self.assertEqual(result["provider"], "gemini")
        _mod._PROVIDER_MAP["gemini"].assert_called_once()
        _mod._PROVIDER_MAP["ollama"].assert_not_called()

    @patch.dict(os.environ, {"AI_PROVIDER_ORDER": "gemini,ollama"})
    def test_env_order_overrides_default(self):
        self._setup_providers(
            ["ollama", "gemini"],
            {
                "gemini": {"content": "gemini via env", "provider": "gemini", "model": "test"},
                "ollama": {"content": "ollama", "provider": "ollama", "model": "test"},
            },
        )
        result = _mod.ai_chat("sys", "usr", use_cache=False)
        self.assertEqual(result["provider"], "gemini")


class TestJsonParsing(unittest.TestCase):
    """Test ai_chat_json parsing logic."""

    def setUp(self):
        _mod._cache.clear()
        self._orig_map = dict(_mod._PROVIDER_MAP)
        self._orig_providers = list(_mod._DEFAULT_PROVIDERS)

    def tearDown(self):
        _mod._PROVIDER_MAP.clear()
        _mod._PROVIDER_MAP.update(self._orig_map)
        _mod._DEFAULT_PROVIDERS[:] = self._orig_providers

    def _mock_provider(self, content):
        _mod._DEFAULT_PROVIDERS[:] = ["ollama"]
        _mod._PROVIDER_MAP["ollama"] = MagicMock(return_value={"content": content, "provider": "ollama", "model": "test"})

    def test_valid_json_extraction(self):
        self._mock_provider('{"executive_summary": "test", "suggestions": []}')
        result = _mod.ai_chat_json("sys", "user")
        self.assertIsNotNone(result)
        self.assertEqual(result["parsed"]["executive_summary"], "test")

    def test_json_in_text_extraction(self):
        self._mock_provider('Here is the analysis:\n{"executive_summary": "wrapped"}\nDone.')
        result = _mod.ai_chat_json("sys", "user")
        self.assertIsNotNone(result)
        self.assertEqual(result["parsed"]["executive_summary"], "wrapped")

    def test_no_json_returns_none_parsed(self):
        self._mock_provider("No JSON here at all")
        result = _mod.ai_chat_json("sys", "user")
        self.assertIsNotNone(result)
        self.assertIsNone(result["parsed"])


class TestProviderStatus(unittest.TestCase):
    """Test get_available_providers returns correct structure."""

    def test_returns_list(self):
        providers = _mod.get_available_providers()
        self.assertIsInstance(providers, list)
        self.assertGreater(len(providers), 0)

    def test_each_has_name_and_status(self):
        providers = _mod.get_available_providers()
        for p in providers:
            self.assertIn("name", p)
            self.assertIn("status", p)
            self.assertIn(p["name"], ["freellmapi", "ollama", "gemini", "openrouter", "agentrouter"])


if __name__ == "__main__":
    unittest.main()
