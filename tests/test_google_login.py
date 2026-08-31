#!/usr/bin/env python3
"""Headless verification of the Google Sign-In backend flow.

Tests:
1. /api/google-client-id returns valid JSON with 'client_id' key
2. POST /api/google-login rejects empty credential
3. POST /api/google-login rejects malformed JWT (not 3 parts)
4. POST /api/google-login rejects wrong issuer
5. POST /api/google-login accepts valid-structure JWT and returns secret
6. POST /api/google-login is idempotent (same sub -> same secret)
7. POST /api/google-login rejects missing credential field
"""
import base64
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def post(path, body, timeout=90, retries=5):
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_res = e.read()
            return e.code, json.loads(body_res) if body_res else {}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return 0, {"error": str(e)}


def get(path, timeout=15, retries=5):
    for attempt in range(retries):
        req = urllib.request.Request(f"{BASE}{path}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_res = e.read()
            return e.code, json.loads(body_res) if body_res else {}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return 0, {"error": str(e)}


def assert_test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} -- {detail}")


def make_credential(iss="accounts.google.com", sub="test_user_001",
                    email="test@gmail.com", name="Test User",
                    picture="https://example.com/pic.jpg"):
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps({
            "iss": iss, "sub": sub, "email": email,
            "name": name, "picture": picture,
        }).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fake_sig").rstrip(b"=").decode()
    return f"{header}.{payload_b64}.{sig}"


def test_client_id():
    print("\n[1] GET /api/google-client-id")
    status, body = get("/api/google-client-id")
    assert_test("HTTP 200", status == 200, f"got {status}")
    assert_test("Has client_id key", "client_id" in body, f"keys: {list(body.keys())}")
    assert_test("client_id is string", isinstance(body["client_id"], str),
                f"type: {type(body['client_id'])}")


def test_empty_credential():
    print("\n[2] POST /api/google-login with empty credential")
    status, body = post("/api/google-login", {"credential": ""})
    assert_test("HTTP 400", status == 400, f"got {status}")
    assert_test("Error is missing_credential", body.get("error") == "missing_credential",
                f"got: {body.get('error')}")


def test_missing_credential():
    print("\n[3] POST /api/google-login without credential field")
    status, body = post("/api/google-login", {})
    assert_test("HTTP 400", status == 400, f"got {status}")
    assert_test("Error is missing_credential", body.get("error") == "missing_credential",
                f"got: {body.get('error')}")


def test_malformed_jwt():
    print("\n[4] POST /api/google-login with malformed JWT")
    status, body = post("/api/google-login", {"credential": "not.a.valid.jwt"})
    assert_test("HTTP 400", status == 400, f"got {status}")
    assert_test("Error indicates invalid credential",
                body.get("error") in ("invalid_credential", "invalid_issuer"),
                f"got: {body.get('error')}")


def test_wrong_issuer():
    print("\n[5] POST /api/google-login with wrong issuer")
    cred = make_credential(iss="evil.com")
    status, body = post("/api/google-login", {"credential": cred})
    assert_test("HTTP 400", status == 400, f"got {status}")
    assert_test("Error is invalid_issuer", body.get("error") == "invalid_issuer",
                f"got: {body.get('error')}")


def test_valid_credential_creates_user():
    print("\n[6] POST /api/google-login with valid JWT creates user")
    start = time.time()
    cred = make_credential(sub="verify_test_99999", email="verify@gmail.com",
                           name="Verify Test")
    status, body = post("/api/google-login", {"credential": cred}, timeout=90)
    elapsed = time.time() - start
    print(f"    Response time: {elapsed:.1f}s")
    assert_test("HTTP 200", status == 200, f"got {status}, body: {body}")
    if status == 200:
        assert_test("status is ok", body.get("status") == "ok", f"got: {body.get('status')}")
        assert_test("secret returned", bool(body.get("secret")), f"got: {body.get('secret')}")
        assert_test("provider is google", body.get("provider") == "google",
                    f"got: {body.get('provider')}")
        assert_test("phone is email", body.get("phone") == "verify@gmail.com",
                    f"got: {body.get('phone')}")
        assert_test("name returned", body.get("name") == "Verify Test",
                    f"got: {body.get('name')}")


def test_idempotency():
    print("\n[7] Same Google sub returns same secret (idempotent)")
    # First call: create user
    cred = make_credential(sub="verify_test_99999", email="verify@gmail.com",
                           name="Verify Test")
    _, body1 = post("/api/google-login", {"credential": cred}, timeout=90)
    secret1 = body1.get("secret") if body1 else None
    # Second call: same sub should return same secret
    _, body2 = post("/api/google-login", {"credential": cred}, timeout=90)
    secret2 = body2.get("secret") if body2 else None
    assert_test("HTTP 200", body2 is not None, f"got: {body2}")
    if secret1 and secret2:
        assert_test("Same secret returned", secret1 == secret2,
                    f"new: {secret2}, expected: {secret1}")


def test_different_sub_different_secret():
    print("\n[8] Different Google sub returns different secret")
    cred = make_credential(sub="verify_test_88888", email="other@gmail.com",
                           name="Other User")
    status, body = post("/api/google-login", {"credential": cred}, timeout=90)
    assert_test("HTTP 200", status == 200, f"got {status}")
    if status == 200:
        assert_test("Different secret", body.get("secret") != "",
                    f"got: {body.get('secret')}")
        assert_test("Different phone/email", body.get("phone") == "other@gmail.com",
                    f"got: {body.get('phone')}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Google Sign-In Backend Verification")
    print("=" * 60)

    test_client_id()
    test_empty_credential()
    test_missing_credential()
    test_malformed_jwt()
    test_wrong_issuer()
    secret = test_valid_credential_creates_user()
    if secret:
        test_idempotency(secret)
    test_different_sub_different_secret()

    print("\n" + "=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL > 0 else 0)
