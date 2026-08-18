/**
 * مكوّن تثبيت PWA — يعرض شريط "أضف إلى الشاشة الرئيسية"
 * عندما يكون المستخدم على جهاز متوافق ولا يكون قد ثبّت التطبيق بعد.
 *
 * الاستخدام:
 *   <div id="installBanner" class="install-banner" hidden></div>
 *   installPrompt.init()
 */
(function() {
  'use strict';

  let deferredPrompt = null;
  let bannerEl = null;
  let isInstalled = false;
  let isDismissed = false;

  // مفتاح التخزين المحلي لمنع إعادة الظهور بعد الإغلاق
  const DISMISS_KEY = 'alforaij_install_dismissed';
  const DISMISS_TTL = 7 * 24 * 60 * 60 * 1000; // أسبوع

  function isStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches ||
           window.navigator.standalone === true ||
           document.referrer.includes('android-app://');
  }

  function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(window.navigator.userAgent);
  }

  function wasDismissed() {
    try {
      const data = JSON.parse(localStorage.getItem(DISMISS_KEY) || '{}');
      if (data.time && (Date.now() - data.time) < DISMISS_TTL) {
        return true;
      }
    } catch(e) {}
    return false;
  }

  function markDismissed() {
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify({ time: Date.now() }));
    } catch(e) {}
  }

  function createBanner() {
    if (bannerEl) return bannerEl;

    bannerEl = document.createElement('div');
    bannerEl.className = 'install-banner';
    bannerEl.id = 'installBanner';
    bannerEl.setAttribute('role', 'alert');
    bannerEl.setAttribute('aria-label', 'تثبيت تطبيق الفريج');
    bannerEl.innerHTML = `
      <div class="install-banner-inner">
        <div class="install-banner-icon">
          <img src="/assets/alforaij-official-symbol.png" alt="الفريج" width="40" height="40">
        </div>
        <div class="install-banner-text">
          <strong>أضف الفريج إلى شاشتك الرئيسية</strong>
          <span>تطبيق سريع — يعمل بدون إنترنت — إشعارات فورية</span>
        </div>
        <div class="install-banner-actions">
          <button class="install-btn-primary" id="installAcceptBtn" type="button">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            تثبيت
          </button>
          <button class="install-btn-close" id="installDismissBtn" type="button" aria-label="إغلاق">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(bannerEl);

    // أحداث
    document.getElementById('installAcceptBtn').addEventListener('click', handleInstall);
    document.getElementById('installDismissBtn').addEventListener('click', handleDismiss);

    return bannerEl;
  }

  async function handleInstall() {
    if (!deferredPrompt) {
      // للold browsers: إرشاد يدوي
      showManualInstructions();
      return;
    }

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;

    if (outcome === 'accepted') {
      console.log('[Install] User accepted install');
      hideBanner();
    } else {
      console.log('[Install] User dismissed install prompt');
    }

    deferredPrompt = null;
  }

  function handleDismiss() {
    isDismissed = true;
    markDismissed();
    hideBanner();
  }

  function showBanner() {
    if (isInstalled || isDismissed || wasDismissed()) return;

    createBanner();
    // تأخير ظهور الشريط لتجنب الإزعاج
    setTimeout(() => {
      if (bannerEl && !isInstalled && !isDismissed) {
        bannerEl.classList.add('visible');
      }
    }, 3000);
  }

  function hideBanner() {
    if (bannerEl) {
      bannerEl.classList.remove('visible');
      setTimeout(() => {
        if (bannerEl) bannerEl.remove();
        bannerEl = null;
      }, 400);
    }
  }

  function showManualInstructions() {
    const isIOS = /iPad|iPhone|iPod/.test(window.navigator.userAgent);
    const isAndroid = /Android/.test(window.navigator.userAgent);

    let steps = '';
    if (isIOS) {
      steps = `
        <ol>
          <li>اضغط زر <strong>المشاركة</strong> <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> في Safari</li>
          <li>اختر <strong>«إضافة إلى الشاشة الرئيسية»</strong></li>
          <li>اضغط <strong>«إضافة»</strong> في الأعلى</li>
        </ol>
      `;
    } else if (isAndroid) {
      steps = `
        <ol>
          <li>اضغط زر <strong>النقاط الثلاث</strong> <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg> في Chrome</li>
          <li>اختر <strong>«تثبيت التطبيق»</strong> أو <strong>«إضافة إلى الشاشة الرئيسية»</strong></li>
          <li>اضغط <strong>«تثبيت»</strong></li>
        </ol>
      `;
    } else {
      steps = `
        <ol>
          <li>اضغط زر القائمة في المتصفح</li>
          <li>اختر <strong>«تثبيت التطبيق»</strong> أو <strong>«إضافة إلى الشاشة الرئيسية»</strong></li>
        </ol>
      `;
    }

    const modal = document.createElement('div');
    modal.className = 'install-modal-overlay';
    modal.innerHTML = `
      <div class="install-modal">
        <div class="install-modal-head">
          <img src="/assets/alforaij-official-symbol.png" alt="الفريج" width="48" height="48">
          <h3>تثبيت تطبيق الفريج</h3>
          <p>اتبع الخطوات التالية لإضافة التطبيق إلى شاشتك الرئيسية</p>
        </div>
        <div class="install-modal-steps">${steps}</div>
        <button class="install-modal-close" type="button">فهمت ✓</button>
      </div>
    `;

    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => {
      if (e.target === modal || e.target.classList.contains('install-modal-close')) {
        modal.remove();
      }
    });
  }

  // ─── الأحداث ───

  function handleBeforeInstallPrompt(e) {
    e.preventDefault();
    deferredPrompt = e;
    showBanner();
  }

  function handleAppInstalled() {
    isInstalled = true;
    deferredPrompt = null;
    hideBanner();
    console.log('[Install] App installed successfully');
  }

  // ─── الم步行 العامة ───

  window.installPrompt = {
    init: function() {
      // لا نعرض شيئاً على Desktop أو إذا كان مثبّتاً
      if (isStandalone()) {
        isInstalled = true;
        return;
      }

      window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.addEventListener('appinstalled', handleAppInstalled);

      // إظهار زر يدوي بعد 5 ثوانٍ إذا لم يظهر beforeinstallprompt
      // (بعض المتصفحات لا تدعم beforeinstallprompt)
      setTimeout(() => {
        if (!deferredPrompt && !isInstalled && !isDismissed && !wasDismissed() && isMobile()) {
          showManualInstallButton();
        }
      }, 5000);
    },

    // عرض تعليمات التثبيت يدوياً
    showInstructions: showManualInstructions,

    // فحص هل التطبيق مثبّت
    isInstalled: function() {
      return isInstalled || isStandalone();
    },
  };

  function showManualInstallButton() {
    if (bannerEl) return;

    const btn = document.createElement('button');
    btn.className = 'install-fab';
    btn.id = 'installFab';
    btn.type = 'button';
    btn.title = 'تثبيت تطبيق الفريج';
    btn.setAttribute('aria-label', 'تثبيت التطبيق');
    btn.innerHTML = `
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
    `;
    btn.addEventListener('click', showManualInstructions);
    document.body.appendChild(btn);
  }

  // Auto-init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { installPrompt.init(); });
  } else {
    installPrompt.init();
  }
})();
