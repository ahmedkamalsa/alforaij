/**
 * تحسينات إمكانية الوصول (Accessibility Enhancements)
 *
 * - تنقل بلوحة المفاتيح (keyboard navigation)
 * - إدارة التركيز (focus management)
 * - دعم قارئ الشاشة (screen reader support)
 * - تحسين التباين اللوني (color contrast)
 * - تقليل الحركة (reduced motion)
 */
(function() {
  'use strict';

  // ─── تنقل بلوحة المفاتيح للوحة التحكم ───
  function initTabNavigation() {
    const tabs = document.querySelectorAll('.main-tab');
    const tabList = document.querySelector('.main-tabs');
    if (!tabList || !tabs.length) return;

    tabList.setAttribute('role', 'tablist');
    tabs.forEach((tab, index) => {
      tab.setAttribute('role', 'tab');
      tab.setAttribute('tabindex', index === 0 ? '0' : '-1');
      tab.setAttribute('aria-selected', index === 0 ? 'true' : 'false');

      const panel = document.querySelector(`[data-main-panel="${tab.dataset.mainTab}"]`);
      if (panel) {
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', tab.id || `tab-${index}`);
        if (!tab.id) tab.id = `tab-${index}`;
        panel.setAttribute('aria-labelledby', tab.id);
      }
    });

    tabList.addEventListener('keydown', (e) => {
      const current = document.activeElement;
      if (!current || !current.classList.contains('main-tab')) return;

      const tabsArray = Array.from(tabs);
      const currentIndex = tabsArray.indexOf(current);
      let nextIndex;

      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();
        // RTL: ArrowLeft = next, ArrowRight = previous
        nextIndex = e.key === 'ArrowLeft'
          ? (currentIndex + 1) % tabs.length
          : (currentIndex - 1 + tabs.length) % tabs.length;
      } else if (e.key === 'Home') {
        e.preventDefault();
        nextIndex = 0;
      } else if (e.key === 'End') {
        e.preventDefault();
        nextIndex = tabs.length - 1;
      } else {
        return;
      }

      tabsArray.forEach((t, i) => {
        t.setAttribute('tabindex', i === nextIndex ? '0' : '-1');
        t.setAttribute('aria-selected', i === nextIndex ? 'true' : 'false');
      });
      tabsArray[nextIndex].focus();
      tabsArray[nextIndex].click();
    });
  }

  // ─── إدارة التركيز للنوافذ المنبثقة (modals) ───
  function initModalFocusTrap() {
    const modals = document.querySelectorAll('[role="dialog"]');
    modals.forEach((modal) => {
      const focusable = modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;

      const firstFocusable = focusable[0];
      const lastFocusable = focusable[focusable.length - 1];

      modal.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;

        if (e.shiftKey) {
          if (document.activeElement === firstFocusable) {
            e.preventDefault();
            lastFocusable.focus();
          }
        } else {
          if (document.activeElement === lastFocusable) {
            e.preventDefault();
            firstFocusable.focus();
          }
        }
      });
    });
  }

  // ─── تحسين الأرقام العربية/الإنجليزية للقارئات ───
  function initNumberAccessibility() {
    document.querySelectorAll('.count-button, .metric-pill b, .opp-score, .gov-axis-total').forEach((el) => {
      const text = el.textContent.trim();
      if (text) {
        el.setAttribute('aria-label', `${text} نتيجة`);
      }
    });
  }

  // ─── تحسين البطاقات العائمة للوصول ───
  function initHoverCardA11y() {
    document.querySelectorAll('.hover-trigger').forEach((trigger) => {
      trigger.setAttribute('tabindex', '0');
      trigger.addEventListener('focus', () => {
        // Show hover card on focus too
        if (window.hoverCard) {
          const data = JSON.parse(trigger.dataset.listingData || '{}');
          if (Object.keys(data).length) {
            hoverCard.show(trigger, data);
          }
        }
      });
      trigger.addEventListener('blur', () => {
        if (window.hoverCard) hoverCard.hide();
      });
    });
  }

  // ─── تحسين الألوان للتباين ───
  function enhanceColorContrast() {
    // Ensure all text meets WCAG AA contrast ratio
    const style = document.createElement('style');
    style.textContent = `
      @media (prefers-contrast: high) {
        :root {
          --ink: #000;
          --muted: #333;
          --blue-deep: #0000cc;
        }
        .pill, .badge, .opp-score {
          border: 1px solid currentColor;
        }
      }
    `;
    document.head.appendChild(style);
  }

  // ─── تقليل الحركة ───
  function respectReducedMotion() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.documentElement.classList.add('reduce-motion');
      const style = document.createElement('style');
      style.textContent = `
        .reduce-motion *,
        .reduce-motion *::before,
        .reduce-motion *::after {
          animation-duration: 0.01ms !important;
          animation-iteration-count: 1 !important;
          transition-duration: 0.01ms !important;
        }
        .reduce-motion .reveal-card {
          opacity: 1 !important;
          transform: none !important;
        }
      `;
      document.head.appendChild(style);
    }
  }

  // ─── live region للتحديثات ───
  function initLiveRegions() {
    // Add aria-live to key dynamic areas
    const regions = [
      { id: 'results', label: 'نتائج البحث' },
      { id: 'oppList', label: 'قائمة الفرص' },
      { id: 'governorateCards', label: 'بيانات المحافظات' },
      { id: 'boardStats', label: 'إحصائيات اللوحة' },
      { id: 'insightsRoot', label: 'تحليلات السوق' },
    ];

    regions.forEach(({ id, label }) => {
      const el = document.getElementById(id);
      if (el) {
        if (!el.getAttribute('role')) {
          el.setAttribute('role', 'region');
        }
        el.setAttribute('aria-label', label);
        el.setAttribute('aria-live', 'polite');
        el.setAttribute('aria-atomic', 'false');
      }
    });
  }

  // ─── تحسين الأزرار للوصول ───
  function enhanceButtonAccessibility() {
    document.querySelectorAll('button:not([aria-label]):not([title])').forEach((btn) => {
      const text = btn.textContent.trim();
      if (!text && btn.querySelector('svg')) {
        // Icon-only button needs label
        const svg = btn.querySelector('svg');
        const title = svg.querySelector('title');
        if (title) {
          btn.setAttribute('aria-label', title.textContent);
        }
      }
    });
  }

  // ─── تحسين الروابط الخارجية ───
  function enhanceExternalLinks() {
    document.querySelectorAll('a[target="_blank"]').forEach((link) => {
      if (!link.querySelector('.sr-only') && !link.getAttribute('aria-label')) {
        const text = link.textContent.trim();
        if (text) {
          link.setAttribute('aria-label', `${text} (يفتح في نافذة جديدة)`);
        }
      }
    });
  }

  // ───تخطي المحتوى ───
  function addSkipLink() {
    const skip = document.createElement('a');
    skip.href = '#mainTabs';
    skip.className = 'skip-link';
    skip.textContent = 'تخطي إلى المحتوى الرئيسي';
    skip.setAttribute('aria-label', 'تخطي إلى المحتوى الرئيسي');
    document.body.insertBefore(skip, document.body.firstChild);

    const style = document.createElement('style');
    style.textContent = `
      .skip-link {
        position: absolute;
        top: -100%;
        left: 50%;
        transform: translateX(-50%);
        background: var(--blue-deep, #1d4ed8);
        color: #fff;
        padding: 12px 24px;
        border-radius: 0 0 8px 8px;
        z-index: 99999;
        font-weight: 700;
        text-decoration: none;
        transition: top 0.2s;
      }
      .skip-link:focus {
        top: 0;
      }
    `;
    document.head.appendChild(style);
  }

  // ─── التهيئة ───
  function init() {
    addSkipLink();
    initTabNavigation();
    initModalFocusTrap();
    initNumberAccessibility();
    initLiveRegions();
    enhanceColorContrast();
    respectReducedMotion();
    enhanceButtonAccessibility();
    enhanceExternalLinks();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-init after dynamic content loads
  window.a11yEnhancements = { refresh: init };
})();
