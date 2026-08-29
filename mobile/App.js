/**
 * الفريج العقاري - تطبيق الجوال
 *
 * WebView wrapper for the web platform with push notifications.
 * Connects to the backend API for property search and evaluation.
 */
import React, { useRef, useState, useEffect, useCallback } from "react";
import {
  Platform,
  StatusBar,
  StyleSheet,
  View,
  Text,
  ActivityIndicator,
  TouchableOpacity,
  RefreshControl,
  ScrollView,
  Linking,
  Dimensions,
  NativeModules,
  BackHandler,
} from "react-native";
import { WebView } from "react-native-webview";
import * as Notifications from "expo-notifications";
import * as Device from "expo-device";
import Constants from "expo-constants";
import { SafeAreaView } from "react-native-safe-area-context";

// ── Configuration ──
const API_URL =
  Constants.expoConfig?.extra?.apiUrl || "http://127.0.0.1:8000";
const WEB_URL = API_URL; // The web frontend is served by the same backend

// ── Notification handler ──
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

// ── Main App ──
export default function App() {
  const webViewRef = useRef(null);
  const [expoPushToken, setExpoPushToken] = useState("");
  const [isConnected, setIsConnected] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [currentUrl, setCurrentUrl] = useState(WEB_URL);
  const [notification, setNotification] = useState(null);

  // ── Register for push notifications ──
  useEffect(() => {
    registerForPushNotificationsAsync().then((token) => {
      if (token) {
        setExpoPushToken(token);
        // Send token to backend
        sendTokenToBackend(token);
      }
    });

    // Listen for incoming notifications
    const sub1 = Notifications.addNotificationReceivedListener(
      (notification) => {
        setNotification(notification);
      }
    );
    const sub2 = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        // User tapped notification — navigate to relevant screen
        const data = response.notification.request.content.data;
        if (data?.url) {
          webViewRef.current?.postMessage(
            JSON.stringify({ type: "NAVIGATE", url: data.url })
          );
        }
      }
    );

    return () => {
      sub1.remove();
      sub2.remove();
    };
  }, []);

  // ── Back button handling (Android) ──
  useEffect(() => {
    const backHandler = BackHandler.addEventListener(
      "hardwareBackPress",
      () => {
        if (canGoBack && webViewRef.current) {
          webViewRef.current.goBack();
          return true;
        }
        return false;
      }
    );
    return () => backHandler.remove();
  }, [canGoBack]);

  // ── Send push token to backend ──
  const sendTokenToBackend = async (token) => {
    try {
      await fetch(`${API_URL}/api/push/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          platform: Platform.OS,
          deviceName: Device.deviceName || "unknown",
        }),
      });
    } catch (e) {
      console.log("Failed to register push token:", e.message);
    }
  };

  // ── Handle messages from web content ──
  const onMessage = useCallback((event) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      switch (data.type) {
        case "REQUEST_NOTIFICATION":
          // Web page wants to send a local notification
          scheduleLocalNotification(data.title, data.body, data.data);
          break;
        case "CHECK_CONNECTION":
          webViewRef.current?.postMessage(
            JSON.stringify({ type: "CONNECTION_STATUS", online: isConnected })
          );
          break;
        case "SHARE":
          // Could use expo-sharing if needed
          break;
      }
    } catch (e) {
      // Ignore non-JSON messages
    }
  }, [isConnected]);

  // ── Schedule a local notification ──
  const scheduleLocalNotification = async (title, body, data = {}) => {
    try {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: title || "الفريج العقاري",
          body: body || "لديك تحديث جديد",
          data,
          sound: true,
        },
        trigger: null, // Immediate
      });
    } catch (e) {
      console.log("Notification error:", e.message);
    }
  };

  // ── WebView injection: bridge for notifications from web ──
  const INJECTED_JS = `
    (function() {
      // Bridge: allow web page to trigger native notifications
      window.AlforaijNative = {
        sendNotification: function(title, body, data) {
          window.ReactNativeWebView.postMessage(JSON.stringify({
            type: 'REQUEST_NOTIFICATION',
            title: title,
            body: body,
            data: data || {}
          }));
        },
        getPushToken: function() {
          return '${expoPushToken}';
        },
        getPlatform: function() {
          return '${Platform.OS}';
        },
        isNative: true
      };
      // Notify web that native bridge is ready
      window.dispatchEvent(new CustomEvent('alforaij-native-ready', {
        detail: { platform: '${Platform.OS}', token: '${expoPushToken}' }
      }));
    })();
    true;
  `;

  // ── Loading indicator ──
  const renderLoading = () => (
    <View style={styles.loadingContainer}>
      <ActivityIndicator size="large" color="#F59E0B" />
      <Text style={styles.loadingText}>جاري تحميل الفريج العقاري...</Text>
    </View>
  );

  // ── Error screen ──
  const renderError = () => (
    <View style={styles.errorContainer}>
      <Text style={styles.errorIcon}>⚠️</Text>
      <Text style={styles.errorTitle}>تعذر الاتصال</Text>
      <Text style={styles.errorText}>
        تحقق من اتصالك بالإنترنت وأعد المحاولة
      </Text>
      <TouchableOpacity
        style={styles.retryButton}
        onPress={() => {
          setLoadError(null);
          setIsLoading(true);
          webViewRef.current?.reload();
        }}
      >
        <Text style={styles.retryText}>🔄 إعادة المحاولة</Text>
      </TouchableOpacity>
      <Text style={styles.errorUrl}>{currentUrl}</Text>
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0F172A" />

      {/* Connection status bar */}
      {!isConnected && (
        <View style={styles.offlineBar}>
          <Text style={styles.offlineText}>
            ⚡ وضع عدم الاتصال — النتائج المحفوظة متاحة
          </Text>
        </View>
      )}

      {/* WebView */}
      <WebView
        ref={webViewRef}
        source={{ uri: WEB_URL }}
        style={styles.webview}
        injectedJavaScript={INJECTED_JS}
        onMessage={onMessage}
        onLoadStart={() => {
          setIsLoading(true);
          setLoadError(null);
        }}
        onLoadEnd={() => {
          setIsLoading(false);
          setIsConnected(true);
        }}
        onError={(syntheticEvent) => {
          const { nativeEvent } = syntheticEvent;
          console.log("WebView error:", nativeEvent.description);
          setIsConnected(false);
          setLoadError(nativeEvent.description);
          setIsLoading(false);
        }}
        onHttpError={(syntheticEvent) => {
          const { nativeEvent } = syntheticEvent;
          if (nativeEvent.statusCode >= 400) {
            setLoadError(`HTTP ${nativeEvent.statusCode}`);
          }
        }}
        onNavigationStateChange={(navState) => {
          setCanGoBack(navState.canGoBack);
          setCurrentUrl(navState.url);
        }}
        javaScriptEnabled
        domStorageEnabled
        startInLoadingState
        renderLoading={renderLoading}
        allowsBackForwardNavigationGestures
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        mixedContentMode="always"
        allowFileAccess
        cacheEnabled
        cacheMode="LOAD_DEFAULT"
        // Android-specific
        allowFileAccessFromFileURLs
        allowUniversalAccessFromFileURLs
        // iOS-specific
        allowsFullscreenVideo={false}
        dataDetectorTypes="all"
        sharedCookiesEnabled
      />

      {/* Loading overlay */}
      {isLoading && !loadError && (
        <View style={styles.loadingOverlay}>
          <View style={styles.loadingCard}>
            <ActivityIndicator size="large" color="#F59E0B" />
            <Text style={styles.loadingText}>جاري التحميل...</Text>
          </View>
        </View>
      )}

      {/* Error overlay */}
      {loadError && renderError()}
    </SafeAreaView>
  );
}

// ── Push notification registration ──
async function registerForPushNotificationsAsync() {
  let token;

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "الفريج العقاري",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#F59E0B",
    });
  }

  if (Device.isDevice) {
    const { status: existingStatus } =
      await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== "granted") {
      console.log("Push notification permission not granted");
      return null;
    }

    try {
      const projectId = Constants.expoConfig?.extra?.eas?.projectId;
      token = await Notifications.getExpoPushTokenAsync({ projectId });
      console.log("Push token:", token.data);
      return token.data;
    } catch (e) {
      console.log("Failed to get push token:", e.message);
      return null;
    }
  } else {
    console.log("Push notifications require a physical device");
    return null;
  }
}

// ── Styles ──
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0F172A",
  },
  webview: {
    flex: 1,
  },
  offlineBar: {
    backgroundColor: "#DC2626",
    paddingVertical: 6,
    paddingHorizontal: 16,
    alignItems: "center",
  },
  offlineText: {
    color: "#fff",
    fontSize: 12,
    fontWeight: "600",
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(15, 23, 42, 0.85)",
    justifyContent: "center",
    alignItems: "center",
  },
  loadingCard: {
    backgroundColor: "#1E293B",
    borderRadius: 16,
    padding: 32,
    alignItems: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: "#0F172A",
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    color: "#94A3B8",
    fontSize: 16,
    marginTop: 12,
  },
  errorContainer: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#0F172A",
    justifyContent: "center",
    alignItems: "center",
    padding: 32,
  },
  errorIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  errorTitle: {
    color: "#F8FAFC",
    fontSize: 22,
    fontWeight: "bold",
    marginBottom: 8,
  },
  errorText: {
    color: "#94A3B8",
    fontSize: 15,
    textAlign: "center",
    marginBottom: 24,
    lineHeight: 22,
  },
  errorUrl: {
    color: "#475569",
    fontSize: 11,
    marginTop: 16,
  },
  retryButton: {
    backgroundColor: "#F59E0B",
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 12,
  },
  retryText: {
    color: "#0F172A",
    fontSize: 16,
    fontWeight: "bold",
  },
});
