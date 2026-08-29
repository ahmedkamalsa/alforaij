# الفريج العقاري — تطبيق الجوال

تطبيق React Native (Expo) يلف المنصة العقارية بـ WebView مع دعم الإشعارات الفورية.

## المميزات

- 🔍 **بحث عقاري** عبر WebView (نفس المنصة الويب)
- 🔔 **إشعارات فورية** عند وجود عقارات جديدة أو انخفاض الأسعار
- 🗺️ **خريطة تفاعلية** (OpenStreetMap عبر المنصة الويب)
- 📈 **اتجاهات الأسعار** وحاسبة العائد الاستثماري
- 🌙 **الوضع الداكن/الفاتح** (يتوافق مع الجهاز)
- ⬅️ **زر الرجوع** (Android)
- 📴 **وضع عدم الاتصال** (عرض النتائج المحفوظة)

## المتطلبات

- Node.js >= 18
- Expo CLI: `npm install -g expo-cli`
- للـ iOS: Xcode + CocoaPods
- للـ Android: Android Studio + SDK

## التشغيل المحلي

```bash
cd mobile
npm install
npx expo start
```

- **جهاز Android**: امسح QR كود بتطبيق Expo Go
- **جهاز iOS**: امسح QR كود بكاميرا iPhone
- **مفسر ويب**: `npx expo start --web`

## الاتصال بالخادم

التطبيق يتصل تلقائياً بالخادم المحلي (`http://127.0.0.1:8000`).

للنشر، غيّر `apiUrl` في `app.json`:

```json
{
  "expo": {
    "extra": {
      "apiUrl": "https://your-domain.com"
    }
  }
}
```

## بناء APK / IPA

### Android (APK)
```bash
npx eas build --platform android
```

### iOS (IPA)
```bash
npx eas build --platform ios
```

### محلي (بدون EAS)
```bash
# Android
npx expo run:android

# iOS
npx expo run:ios
```

## هيكل المشروع

```
mobile/
├── App.js                 # التطبيق الرئيسي (WebView + إشعارات)
├── app.json               # إعدادات Expo
├── babel.config.js        # Babel
├── package.json           # الاعتماديات
├── src/
│   └── notifications.js   # جسر الإشعارات (من الويب إلى الجوال)
└── assets/                # أيقونات وصور
```

## نظام الإشعارات

### تسجيل الجهاز
يتم تلقائياً عند تشغيل التطبيق. الرمز يُرسل إلى `/api/push/register`.

### اشتراكات المستخدم
| النوع | الوصف | مثال |
|-------|-------|------|
| `area` | إشعارات منطقة محددة | الفردوس، صباح الناصر |
| `price_drop` | انخفاض الأسعار | أكثر من 5% |
| `new_listing` | إعلانات جديدة | أي منطقة |
| `all` | كل الإشعارات | — |

### API Endpoint
```
POST /api/push/register   → تسجيل الجهاز
POST /api/push/subscribe  → اشتراك في نوع إشعار
POST /api/push/send       → إرسال إشعار (admin)
GET  /api/push/stats      → إحصائيات الأجهزة
```

## للنشر على المتاجر

1. **Google Play Store**:
   - أنشئ حساب مطور ($25)
   - ابنِ APK عبر `eas build`
   - ارفعه على Console

2. **Apple App Store**:
   - اشترك Apple Developer ($99/سنة)
   - ابنِ IPA عبر `eas build`
   - ارفعه عبر Xcode أو Transporter

## ملاحظات تقنية

- Expo SDK 52 (أحدث إصدار مستقر)
- WebView يoload المنصة الويب الكاملة (لا نسخة منفصلة)
- الإشعارات تستخدم Expo Push Notification API
- عند التشغيل في المتصفح العادي، الإشعارات تعمل كأزرار UI فقط
