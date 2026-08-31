/**
 * Service Worker — منصة الفريج العقارية
 * 
 * استراتيجيات التخزين المؤقت:
 * 1. App Shell (Cache-First): HTML, CSS, JS, صور، خطوط → فوري بدون اتصال
 * 2. API Data (Network-First): البيانات الحية تُجلب أولاً ثم تُخزّن كاحتياط
 * 3. Static Data (Cache-First + Revalidate): JSON الثابت يُحمّل من الكاش ثم يُحدّث في الخلفية
 * 4. Offline Fallback: صفحة بديلة عند غياب الاتصال
 */

const CACHE_VERSION = 'v3';
const CACHE_NAME = `alforaij-${CACHE_VERSION}`;
const STATIC_CACHE = `alforaij-static-${CACHE_VERSION}`;
const API_CACHE = `alforaij-api-${CACHE_VERSION}`;
const OFFLINE_PAGE = '/offline.html';

// ─── الملفات الأساسية (App Shell) ───
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/pricing.html',
  '/styles.css',
  '/config.js',
  '/app.js',
  '/components/lucide-icons.js',
  '/components/modern-design.css',
  '/components/hover-card.js',
  '/components/hover-card-v2.css',
  '/components/a11y-enhancements.js',
  '/components/tier-gate.js',
  '/assets/alforaij-official-symbol.png',
  '/assets/alforaij_logo.png',
  '/assets/apple-touch-icon.png',
  '/assets/favicon.ico',
  '/assets/kuwait_glass_cover.webp',
  OFFLINE_PAGE,
];

// ─── ملفات الخطوط ──
const FONT_CACHE = `alforaij-fonts-${CACHE_VERSION}`;
const FONT_URLS = [
  // Noto Kufi Arabic
  '/assets/fonts/noto-kufi-arabic-arabic-500-normal.woff2',
  '/assets/fonts/noto-kufi-arabic-arabic-700-normal.woff2',
  '/assets/fonts/noto-kufi-arabic-arabic-900-normal.woff2',
  '/assets/fonts/noto-kufi-arabic-latin-700-normal.woff2',
  // Tajawal
  '/assets/fonts/tajawal-arabic-400-normal.woff2',
  '/assets/fonts/tajawal-arabic-700-normal.woff2',
  '/assets/fonts/tajawal-arabic-800-normal.woff2',
  '/assets/fonts/tajawal-latin-400-normal.woff2',
  '/assets/fonts/tajawal-latin-700-normal.woff2',
];

// ─── APIs المخزّنة مؤقتاً (Network-First) ──
const API_NETWORK_FIRST = [
  '/api/health',
  '/api/dashboard/summary',
  '/api/opportunities',
  '/api/market-insights',
  '/api/market-demand',
  '/api/developments',
  '/api/market-analytics',
  '/api/platform-dates',
  '/api/platform-intelligence',
  '/api/metric-registry',
  '/api/update-notifications',
  '/api/market-matching',
  '/api/opportunity-delta',
  '/api/whatsapp-alerts',
  '/api/weekly-digest',
  '/api/price-trends',
];

// ─── APIs المخزّنة مؤقتاً (Cache-First مع Revalidate) ──
const API_CACHE_FIRST = [
  '/api/sources',
  '/api/search-options',
  '/api/live-db',
];

// مدة صلاحية الكاش (بالثواني)
const API_TTL = 300; // 5 دقائق للبيانات الحية
const STATIC_TTL = 86400; // يوم واحد للأصول الثابتة
const FONT_TTL = 604800; // أسبوع للخطوط

// ─── التثبيت ───
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...', CACHE_VERSION);
  
  event.waitUntil(
    Promise.all([
      // تخزين App Shell
      caches.open(STATIC_CACHE).then((cache) => {
        return cache.addAll(SHELL_ASSETS.filter(url => url !== OFFLINE_PAGE)).catch((err) => {
          console.warn('[SW] Some shell assets failed to cache:', err);
        });
      }),
      // تخزين الخطوط
      caches.open(FONT_CACHE).then((cache) => {
        return cache.addAll(FONT_URLS).catch((err) => {
          console.warn('[SW] Some fonts failed to cache:', err);
        });
      }),
      // تخزين صفحة الأوفلاين
      caches.open(STATIC_CACHE).then((cache) => {
        return cache.add(OFFLINE_PAGE).catch(() => {
          // إنشاء صفحة بديلة بسيطة إذا لم تكن موجودة
          return cache.put(OFFLINE_PAGE, new Response(`
            <!DOCTYPE html>
            <html lang="ar" dir="rtl">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <title>غير متصل — الفريج</title>
              <style>
                body { font-family: system-ui; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #0f172a; color: #e8eef7; }
                .container { text-align: center; padding: 2rem; }
                h1 { font-size: 2rem; margin-bottom: 1rem; }
                p { color: #b3c2d5; margin-bottom: 1.5rem; }
                .icon { font-size: 4rem; margin-bottom: 1rem; }
                button { background: #b7a13a; color: #fff; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer; }
                button:hover { background: #d9b850; }
              </style>
            </head>
            <body>
              <div class="container">
                <div class="icon">📡</div>
                <h1>غير متصل بالإنترنت</h1>
                <p>تحقق من اتصالك بالشبكة وحاول مرة أخرى</p>
                <p style="font-size: 14px; color: #64748b;">البيانات المحفوظة سابقاً قد تكون متاحة</p>
                <button onclick="window.location.reload()">إعادة المحاولة</button>
              </div>
            </body>
            </html>
          `, { headers: { 'Content-Type': 'text/html; charset=utf-8' } }));
        });
      }),
    ]).then(() => self.skipWaiting())
  );
});

// ─── التفعيل ───
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...', CACHE_VERSION);
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => {
            // حذف الكاش القديم
            return name.startsWith('alforaij-') && 
                   name !== STATIC_CACHE && 
                   name !== FONT_CACHE &&
                   name !== `alforaij-api-${CACHE_VERSION}`;
          })
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// ─── الاستراتيجية: Cache-First للثوابت ──
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // إرجاع صفحة الأوفلاين للصفحات
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match(OFFLINE_PAGE);
    }
    throw err;
  }
}

// ─── الاستراتيجية: Network-First للبيانات الحية ──
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(`alforaij-api-${CACHE_VERSION}`);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ 
      error: 'offline', 
      message: ' غير متصل بالإنترنت — البيانات المحفوظة قد تكون قديمة' 
    }), {
      headers: { 'Content-Type': 'application/json' },
      status: 503,
    });
  }
}

// ─── الاستراتيجية: Cache-First مع Revalidate ──
async function cacheFirstRevalidate(request) {
  const cached = await caches.match(request);
  
  // إعادة التحميل في الخلفية
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) {
      const cache = caches.open(`alforaij-api-${CACHE_VERSION}`).then((c) => {
        c.put(request, response.clone());
      });
    }
    return response;
  }).catch(() => cached);
  
  return cached || fetchPromise;
}

// ─── الاستراتيجية: Stale-While-Revalidate للصور ──
async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);
  
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) {
      const cache = caches.open(STATIC_CACHE).then((c) => {
        c.put(request, response.clone());
      });
    }
    return response;
  }).catch(() => cached);
  
  return cached || fetchPromise;
}

// ─── التعامل مع الطلبات ──
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // تخطي الطلبات غير HTTP
  if (!url.protocol.startsWith('http')) return;
  
  // تخطي طلبات HEAD
  if (request.method === 'HEAD') return;
  
  // تخطي طلبات Chrome Extension
  if (url.origin !== self.location.origin && !url.origin.includes('supabase')) return;

  // 1. Static Assets → Cache-First
  if (SHELL_ASSETS.some(asset => url.pathname.endsWith(asset)) || 
      url.pathname.endsWith('.css') ||
      url.pathname.endsWith('.js') ||
      url.pathname.endsWith('.png') ||
      url.pathname.endsWith('.webp') ||
      url.pathname.endsWith('.ico') ||
      url.pathname.endsWith('.woff2')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // 2. Fonts → Cache-First (طويل الأمد)
  if (url.pathname.includes('/assets/fonts/') || url.pathname.endsWith('.woff2')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response.ok) {
            const cache = caches.open(FONT_CACHE).then(c => c.put(request, response.clone()));
          }
          return response;
        });
      })
    );
    return;
  }

  // 3. API: Network-First (البيانات الحية)
  if (url.pathname.startsWith('/api/') && 
      API_NETWORK_FIRST.some(api => url.pathname.startsWith(api))) {
    event.respondWith(networkFirst(request));
    return;
  }

  // 4. API: Cache-First مع Revalidate (البيانات الأساسية)
  if (url.pathname.startsWith('/api/') && 
      API_CACHE_FIRST.some(api => url.pathname.startsWith(api))) {
    event.respondWith(cacheFirstRevalidate(request));
    return;
  }

  // 5. Static Data (JSON) → Cache-First + Revalidate
  if (url.pathname.startsWith('/static-data/') && url.pathname.endsWith('.json')) {
    event.respondWith(cacheFirstRevalidate(request));
    return;
  }

  // 6. External CDN (Lucide, etc) → Cache-First
  if (url.origin !== self.location.origin) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // 7. Default → Network-First مع Offline Fallback
  event.respondWith(
    fetch(request).catch(() => {
      if (request.headers.get('accept')?.includes('text/html')) {
        return caches.match(OFFLINE_PAGE);
      }
      return caches.match(request);
    })
  );
});

// ─── تحديث الخلفي (Background Sync) ──
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-searches') {
    console.log('[SW] Background sync: searches');
    event.waitUntil(syncPendingSearches());
  }
});

async function syncPendingSearches() {
  // مزامنة أي بحثات محفوظة محلياً عند عودة الاتصال
  try {
    const clients = await self.clients.matchAll();
    clients.forEach(client => {
      client.postMessage({ type: 'SYNC_COMPLETE' });
    });
  } catch (err) {
    console.warn('[SW] Sync failed:', err);
  }
}

// ─── Push Notifications ──
self.addEventListener('push', (event) => {
  if (!event.data) return;
  
  const data = event.data.json();
  const options = {
    body: data.body || 'فرصة جديدة متاحة',
    icon: '/assets/alforaij-official-symbol.png',
    badge: '/assets/alforaij-official-symbol.png',
    vibrate: [100, 50, 100],
    data: { url: data.url || '/' },
    actions: [
      { action: 'open', title: 'عرض الفرصة', icon: '/assets/alforaij-official-symbol.png' },
      { action: 'dismiss', title: 'تجاهل' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'الفريج العقارية', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  if (event.action === 'dismiss') return;
  
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    self.clients.openWindow(url)
  );
});

// ─── رسائل من الواجهة ──
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data?.type === 'CACHE_URLS') {
    const urls = event.data.urls || [];
    caches.open(STATIC_CACHE).then(cache => {
      return Promise.all(urls.map(url => cache.add(url).catch(() => {})));
    });
  }
  
  if (event.data?.type === 'CLEAR_API_CACHE') {
    caches.delete(`alforaij-api-${CACHE_VERSION}`);
  }
});
