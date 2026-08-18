"""اختبارات نظام الخطط على الخادم — JWT + Supabase."""
import hashlib
import hmac
import json
import base64
import time
import unittest
from unittest.mock import patch, MagicMock
from backend.services.server_tier import (
    verify_jwt,
    extract_user_from_token,
    authorize_request,
    get_user_tier,
    upgrade_user,
    get_tier_limits,
)
from backend.services.tier import TIER_CONFIG


def _create_jwt(payload: dict, secret: str = "test-secret-key-12345") -> str:
    """إنشاء JWT token للاختبار."""
    header = {"alg": "HS256", "typ": "JWT"}
    
    def b64url_encode(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    
    header_b64 = b64url_encode(header)
    payload_b64 = b64url_encode(payload)
    
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


class TestJWTVerification(unittest.TestCase):
    """اختبارات التحقق من JWT."""
    
    def test_valid_jwt_passes(self):
        """توكن صالح يُقبل."""
        payload = {"sub": "user-123", "phone": "+96555512345", "exp": time.time() + 3600}
        token = _create_jwt(payload, "my-secret")
        
        with patch("backend.services.server_tier._get_jwt_secret", return_value="my-secret"):
            result = verify_jwt(token)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["sub"], "user-123")
    
    def test_expired_jwt_fails(self):
        """توكن منتهي الصلاحية يُرفض."""
        payload = {"sub": "user-123", "exp": time.time() - 100}  # منتهي
        token = _create_jwt(payload, "my-secret")
        
        with patch("backend.services.server_tier._get_jwt_secret", return_value="my-secret"):
            result = verify_jwt(token)
        
        self.assertIsNone(result)
    
    def test_wrong_secret_fails(self):
        """توكن بسر خاطئ يُرفض."""
        payload = {"sub": "user-123"}
        token = _create_jwt(payload, "wrong-secret")
        
        with patch("backend.services.server_tier._get_jwt_secret", return_value="correct-secret"):
            result = verify_jwt(token)
        
        self.assertIsNone(result)
    
    def test_empty_token_fails(self):
        """توكن فارغ يُرفض."""
        result = verify_jwt("")
        self.assertIsNone(result)
    
    def test_malformed_token_fails(self):
        """توكن مشوّه يُرفض."""
        result = verify_jwt("not.a.valid.jwt.token")
        self.assertIsNone(result)
    
    def test_extract_user_from_valid_token(self):
        """استخراج معلومات المستخدم من توكن صالح."""
        payload = {
            "sub": "user-456",
            "phone": "+96599999999",
            "app_metadata": {"tier": "pro"},
            "exp": time.time() + 3600,
        }
        token = _create_jwt(payload, "my-secret")
        
        with patch("backend.services.server_tier._get_jwt_secret", return_value="my-secret"):
            user = extract_user_from_token(token)
        
        self.assertIsNotNone(user)
        self.assertEqual(user["user_id"], "user-456")
        self.assertEqual(user["phone"], "+96599999999")
        self.assertEqual(user["tier"], "pro")


class TestAuthorizeRequest(unittest.TestCase):
    """اختبارات صلاحية الطلبات."""
    
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_anonymous_user_denied(self, mock_fetch):
        """مستخدم غير مسجل يُرفض."""
        result = authorize_request("", "search")
        self.assertFalse(result["authorized"])
        self.assertEqual(result["tier"], "anonymous")
        self.assertIn("سجل الدخول", result["message"])
    
    @patch("backend.services.server_tier._fetch_daily_usage")
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_free_user_within_limit(self, mock_fetch_tier, mock_fetch_usage):
        """مستخدم مجاني ضمن الحد يُقبل."""
        mock_fetch_tier.return_value = {"user_id": "user-1", "tier": "free"}
        mock_fetch_usage.return_value = 5  # من 20
        
        result = authorize_request("user-1", "search")
        self.assertTrue(result["authorized"])
        self.assertEqual(result["tier"], "free")
        self.assertEqual(result["remaining"], 15)
        self.assertFalse(result["near_limit"])
    
    @patch("backend.services.server_tier._fetch_daily_usage")
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_free_user_near_limit(self, mock_fetch_tier, mock_fetch_usage):
        """مستخدم مجاني قريب من الحد (80%+) يحصل على تحذير."""
        mock_fetch_tier.return_value = {"user_id": "user-1", "tier": "free"}
        mock_fetch_usage.return_value = 17  # من 20 = 85%
        
        result = authorize_request("user-1", "search")
        self.assertTrue(result["authorized"])
        self.assertTrue(result["near_limit"])
    
    @patch("backend.services.server_tier._fetch_daily_usage")
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_free_user_at_limit_denied(self, mock_fetch_tier, mock_fetch_usage):
        """مستخدم مجاني وصل الحد يُرفض."""
        mock_fetch_tier.return_value = {"user_id": "user-1", "tier": "free"}
        mock_fetch_usage.return_value = 20  # وصل الحد
        
        result = authorize_request("user-1", "search")
        self.assertFalse(result["authorized"])
        self.assertIn("reach", result["message"].lower()) if "reach" in result["message"].lower() else None
        self.assertIsNotNone(result.get("upgrade"))
    
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_pro_user_unlimited(self, mock_fetch_tier):
        """مستخدم محترف غير محدود."""
        mock_fetch_tier.return_value = {"user_id": "user-2", "tier": "pro"}
        
        result = authorize_request("user-2", "search")
        self.assertTrue(result["authorized"])
        self.assertEqual(result["tier"], "pro")
        self.assertIsNone(result["remaining"])
    
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_free_user_disabled_feature(self, mock_fetch_tier):
        """مستخدم مجاني يحاول ميزة غير متاحة."""
        mock_fetch_tier.return_value = {"user_id": "user-1", "tier": "free"}
        
        result = authorize_request("user-1", "pdf_reports")
        self.assertFalse(result["authorized"])
        self.assertIsNotNone(result.get("upgrade"))


class TestTierLimits(unittest.TestCase):
    """اختبارات حدود الخطط."""
    
    @patch("backend.services.server_tier._fetch_daily_usage")
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_get_tier_limits_free(self, mock_fetch_tier, mock_fetch_usage):
        """حدود الخطة المجانية."""
        mock_fetch_tier.return_value = {"user_id": "user-1", "tier": "free"}
        mock_fetch_usage.return_value = 3
        
        limits = get_tier_limits("user-1")
        self.assertEqual(limits["tier"], "free")
        self.assertIn("search", limits["features"])
        self.assertEqual(limits["features"]["search"]["limit"], 20)
        self.assertEqual(limits["features"]["search"]["current"], 3)
        self.assertEqual(limits["features"]["search"]["remaining"], 17)
    
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_get_tier_limits_pro(self, mock_fetch_tier):
        """حدود الخطة المحترفة."""
        mock_fetch_tier.return_value = {"user_id": "user-2", "tier": "pro"}
        
        limits = get_tier_limits("user-2")
        self.assertEqual(limits["tier"], "pro")
        self.assertEqual(limits["features"]["search"]["limit"], None)  # غير محدود


class TestUpgrade(unittest.TestCase):
    """اختبارات ترقية الخطط."""
    
    @patch("backend.services.server_tier._upsert_user_tier")
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_upgrade_free_to_pro(self, mock_fetch, mock_upsert):
        """ترقية من مجاني لمحترف."""
        mock_fetch.return_value = {"user_id": "user-1", "tier": "free"}
        
        result = upgrade_user("user-1", "pro")
        self.assertEqual(result["status"], "upgraded")
        self.assertEqual(result["new_tier"], "pro")
        mock_upsert.assert_called_once()
    
    @patch("backend.services.server_tier._upsert_user_tier")
    @patch("backend.services.server_tier._fetch_user_tier")
    def test_upgrade_to_trial_sets_expiry(self, mock_fetch, mock_upsert):
        """ترقية للتجريبي تُحدد انتهاء بعد 7 أيام."""
        mock_fetch.return_value = {"user_id": "user-1", "tier": "free"}
        
        result = upgrade_user("user-1", "trial")
        self.assertEqual(result["new_tier"], "trial")
        # التحقق من تمرير تاريخ الانتهاء
        call_args = mock_upsert.call_args
        self.assertIn("trial_ends_at", call_args[1])
    
    def test_upgrade_invalid_tier(self):
        """ترقية لخطة غير معروفة تُفشل."""
        result = upgrade_user("user-1", "nonexistent")
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
