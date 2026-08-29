"""
Push notification service for Alforaij mobile app.

Handles:
- Device token registration
- Sending push notifications (property alerts, price drops, new listings)
- Subscription management (area, price range, property type)
"""
import json
import time
import logging
from typing import Optional

log = logging.getLogger("alforaij.push")

# In-memory store for push tokens (replace with Supabase table in production)
_PUSH_TOKENS: dict[str, dict] = {}  # token -> {platform, deviceName, subscriptions, registeredAt}
_PUSH_LOG: list[dict] = []  # Recent notification log


def register_token(token: str, platform: str = "unknown", device_name: str = "unknown") -> dict:
    """Register a device push token."""
    _PUSH_TOKENS[token] = {
        "platform": platform,
        "deviceName": device_name,
        "subscriptions": [],  # list of {type, value} e.g. {"type": "area", "value": "الفردوس"}
        "registeredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lastSeen": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    log.info(f"Registered push token: {token[:20]}... ({platform})")
    return {"status": "ok", "total_devices": len(_PUSH_TOKENS)}


def unregister_token(token: str) -> dict:
    """Remove a device push token."""
    if token in _PUSH_TOKENS:
        del _PUSH_TOKENS[token]
        log.info(f"Unregistered push token: {token[:20]}...")
    return {"status": "ok", "total_devices": len(_PUSH_TOKENS)}


def subscribe(token: str, subscription_type: str, value: str) -> dict:
    """
    Subscribe a device to notifications.
    subscription_type: "area", "price_drop", "new_listing", "all"
    """
    if token not in _PUSH_TOKENS:
        return {"error": "Token not registered"}
    subs = _PUSH_TOKENS[token]["subscriptions"]
    # Avoid duplicates
    sub = {"type": subscription_type, "value": value}
    if sub not in subs:
        subs.append(sub)
    log.info(f"Subscribed {token[:20]}... to {subscription_type}:{value}")
    return {"status": "ok", "subscriptions": subs}


def unsubscribe(token: str, subscription_type: str, value: str) -> dict:
    """Remove a subscription."""
    if token not in _PUSH_TOKENS:
        return {"error": "Token not registered"}
    subs = _PUSH_TOKENS[token]["subscriptions"]
    sub = {"type": subscription_type, "value": value}
    _PUSH_TOKENS[token]["subscriptions"] = [s for s in subs if s != sub]
    return {"status": "ok", "subscriptions": _PUSH_TOKENS[token]["subscriptions"]}


def send_push_notification(
    title: str,
    body: str,
    data: Optional[dict] = None,
    target_token: Optional[str] = None,
    subscription_filter: Optional[dict] = None,
) -> dict:
    """
    Send a push notification via Expo Push Notification API.

    target_token: Send to a specific device only.
    subscription_filter: Send to devices matching this subscription {type, value}.
    """
    data = data or {}

    # Determine target tokens
    if target_token:
        tokens = [target_token] if target_token in _PUSH_TOKENS else []
    else:
        tokens = list(_PUSH_TOKENS.keys())

    # Apply subscription filter
    if subscription_filter and tokens:
        filtered = []
        sf_type = subscription_filter.get("type", "all")
        sf_value = subscription_filter.get("value", "")
        for t in tokens:
            subs = _PUSH_TOKENS[t].get("subscriptions", [])
            # "all" subscriptions match everything
            if any(s["type"] == "all" for s in subs):
                filtered.append(t)
            elif any(s["type"] == sf_type and s["value"] == sf_value for s in subs):
                filtered.append(t)
        tokens = filtered

    if not tokens:
        return {"status": "no_targets", "sent": 0}

    # Build Expo push messages
    messages = []
    for token in tokens:
        messages.append({
            "to": token,
            "title": title,
            "body": body,
            "data": data,
            "sound": "default",
            "channelId": "default",
        })

    # Send via Expo API (batch)
    sent = 0
    errors = []
    if messages:
        try:
            import urllib.request
            payload = json.dumps(messages).encode("utf-8")
            req = urllib.request.Request(
                "https://exp.host/--/api/v2/push/send",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            sent = len(messages)
            log.info(f"Sent {sent} push notifications")
        except Exception as e:
            errors.append(str(e))
            log.error(f"Push send error: {e}")

    # Log the notification
    _PUSH_LOG.append({
        "title": title,
        "body": body,
        "data": data,
        "targets": len(tokens),
        "sent": sent,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    # Keep only last 100 logs
    if len(_PUSH_LOG) > 100:
        _PUSH_LOG.pop(0)

    return {
        "status": "ok" if sent > 0 else "failed",
        "sent": sent,
        "targets": len(tokens),
        "errors": errors,
    }


def get_stats() -> dict:
    """Get push notification statistics."""
    area_subs = {}
    for token, info in _PUSH_TOKENS.items():
        for sub in info.get("subscriptions", []):
            key = f"{sub['type']}:{sub['value']}"
            area_subs[key] = area_subs.get(key, 0) + 1

    return {
        "total_devices": len(_PUSH_TOKENS),
        "devices": {
            "ios": sum(1 for t in _PUSH_TOKENS.values() if t["platform"] == "ios"),
            "android": sum(1 for t in _PUSH_TOKENS.values() if t["platform"] == "android"),
        },
        "subscriptions": area_subs,
        "recent_notifications": _PUSH_LOG[-10:],
    }


# ── Auto-notify helpers (called after search/alert events) ──

def notify_new_listing(area: str, price: float, title: str, url: str):
    """Notify all devices subscribed to an area about a new listing."""
    return send_push_notification(
        title=f"🏢 عقار جديد في {area}",
        body=f"{title} — {price:,.0f} د.ك",
        data={"type": "new_listing", "area": area, "price": price, "url": url},
        subscription_filter={"type": "area", "value": area},
    )


def notify_price_drop(area: str, old_price: float, new_price: float, title: str):
    """Notify subscribers about a price drop."""
    drop_pct = round(((old_price - new_price) / old_price) * 100)
    return send_push_notification(
        title=f"📉 انخفاض سعر في {area}",
        body=f"{title} — انخفض {drop_pct}% إلى {new_price:,.0f} د.ك",
        data={"type": "price_drop", "area": area, "drop_pct": drop_pct},
        subscription_filter={"type": "price_drop", "value": area},
    )
