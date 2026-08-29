/**
 * Alforaij Notification Bridge
 *
 * Call from web pages running inside the React Native WebView.
 * Falls back gracefully when running in a regular browser.
 */

export const AlforaijNotifications = {
  /**
   * Subscribe to push notifications for a specific area.
   * @param {string} area - Area name like "الفردوس"
   */
  async subscribeToArea(area) {
    if (window.AlforaijNative?.isNative) {
      // Running inside React Native WebView
      window.AlforaijNative.sendNotification(
        "تم التفعيل ✅",
        `ستتلقى إشعارات عند وجود عقارات جديدة في ${area}`,
        { type: "subscribe", area }
      );
    }
    // Also register with backend
    try {
      const token = window.AlforaijNative?.getPushToken();
      if (token) {
        await fetch("/api/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, type: "area", value: area }),
        });
      }
    } catch (e) {
      console.log("Subscribe failed:", e);
    }
  },

  /**
   * Subscribe to price drop notifications for an area.
   * @param {string} area - Area name
   * @param {number} [minDropPct=5] - Minimum price drop percentage to notify
   */
  async subscribeToPriceDrop(area, minDropPct = 5) {
    if (window.AlforaijNative?.isNative) {
      window.AlforaijNative.sendNotification(
        "تنبيه انخفاض الأسعار 🔔",
        `ستتلقى إشعاراً عند انخفاض الأسعار أكثر من ${minDropPct}% في ${area}`,
        { type: "price_drop", area, minDropPct }
      );
    }
    try {
      const token = window.AlforaijNative?.getPushToken();
      if (token) {
        await fetch("/api/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, type: "price_drop", value: area }),
        });
      }
    } catch (e) {
      console.log("Subscribe failed:", e);
    }
  },

  /**
   * Subscribe to all notifications (new listings, price drops, updates).
   */
  async subscribeToAll() {
    if (window.AlforaijNative?.isNative) {
      window.AlforaijNative.sendNotification(
        "إشعارات مفعّلة 🔔",
        "ستتلقى جميع الإشعارات العقارية",
        { type: "subscribe", area: "all" }
      );
    }
    try {
      const token = window.AlforaijNative?.getPushToken();
      if (token) {
        await fetch("/api/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, type: "all", value: "" }),
        });
      }
    } catch (e) {
      console.log("Subscribe failed:", e);
    }
  },

  /**
   * Check if running inside a native app.
   */
  isNative() {
    return !!window.AlforaijNative?.isNative;
  },

  /**
   * Get the push token (only available in native app).
   */
  getPushToken() {
    return window.AlforaijNative?.getPushToken() || null;
  },

  /**
   * Get the platform (ios/android/web).
   */
  getPlatform() {
    return window.AlforaijNative?.getPlatform() || "web";
  },
};

// Auto-detect native environment and log
if (typeof window !== "undefined") {
  window.addEventListener("alforaij-native-ready", (e) => {
    console.log(
      `[Alforaij] Native bridge ready — platform: ${e.detail.platform}`
    );
  });
}
