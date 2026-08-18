/**
 * مكوّن البطاقة العائمة (Hover Card) — يعرض تفاصيل الإعلان عند مرور الماوس
 * بدون الحاجة للنقر. يعمل على جميع بطاقات الإعلانات في اللوحة والنتائج.
 *
 * الاستخدام:
 *   <div class="hover-trigger" data-listing-code="ALF-123">...</div>
 *   hoverCard.init()  // يُفعّل تلقائيًا لكل .hover-trigger
 */
(function() {
  'use strict';

  const HOVER_DELAY = 300; // مللي ثانية قبل الظهور
  const HIDE_DELAY = 200;
  const EDGE_PADDING = 12;

  let tooltipEl = null;
  let showTimer = null;
  let hideTimer = null;
  let currentTrigger = null;

  function createTooltip() {
    if (tooltipEl) return tooltipEl;
    tooltipEl = document.createElement('div');
    tooltipEl.className = 'hover-card';
    tooltipEl.setAttribute('role', 'tooltip');
    tooltipEl.setAttribute('aria-hidden', 'true');
    tooltipEl.innerHTML = `
      <div class="hover-card-head">
        <span class="hover-card-source"></span>
        <span class="hover-card-date"></span>
      </div>
      <div class="hover-card-body">
        <h4 class="hover-card-title"></h4>
        <div class="hover-card-meta"></div>
        <div class="hover-card-price-row">
          <span class="hover-card-price"></span>
          <span class="hover-card-score" hidden></span>
        </div>
        <div class="hover-card-features"></div>
        <div class="hover-card-summary"></div>
        <div class="hover-card-footer">
          <span class="hover-card-link">اضغط للتفاصيل الكاملة</span>
        </div>
      </div>
    `;
    document.body.appendChild(tooltipEl);

    tooltipEl.addEventListener('mouseenter', function() {
      clearTimeout(hideTimer);
    });

    tooltipEl.addEventListener('mouseleave', function() {
      hideTooltip();
    });

    return tooltipEl;
  }

  function getListingData(trigger) {
    // Try data attributes first
    if (trigger.dataset.listingData) {
      try { return JSON.parse(trigger.dataset.listingData); } catch(e) {}
    }

    // Try to extract from card's existing data
    const card = trigger.closest('.result-card, .board-card, .opp-card, [class*="card"]');
    if (!card) return null;

    const get = (sel) => {
      const el = card.querySelector(sel);
      return el ? el.textContent.trim() : '';
    };

    return {
      code: get('.result-body h3, .board-card-title, .opp-title') || trigger.dataset.listingCode || '',
      source: get('.src-pill, .source-label') || '',
      date: get('.pub-date, .date-label') || '',
      transaction: get('.tx-pill, .transaction-label') || '',
      propertyType: get('.simple-type, .type-label') || '',
      area: get('.simple-area, .area-label') || '',
      governorate: get('.governorate-label') || '',
      price: get('.simple-price, .price-label') || '',
      priceNum: parseFloat(get('.simple-price, .price-label').replace(/[^\d.]/g, '')) || null,
      space: get('.space-label') || '',
      score: get('.recommendation, .score-value') || '',
      features: get('.card-facts, .features-list') || '',
      summary: get('.decision-line, .summary-text') || '',
      url: (card.querySelector('a.open-link, a[href]') || {}).href || '',
      phone: trigger.dataset.phone || card.querySelector('.call-link')?.href?.replace('tel:', '') || '',
    };
  }

  function populateTooltip(data) {
    if (!tooltipEl || !data) return;

    tooltipEl.querySelector('.hover-card-source').textContent = data.source || 'الفريج';
    tooltipEl.querySelector('.hover-card-date').textContent = data.date || '';
    tooltipEl.querySelector('.hover-card-title').textContent =
      [data.area, data.governorate, data.propertyType].filter(Boolean).join(' · ') || data.code || '';

    const metaParts = [];
    if (data.transaction) metaParts.push(data.transaction);
    if (data.space) metaParts.push(data.space + ' م²');
    tooltipEl.querySelector('.hover-card-meta').textContent = metaParts.join(' | ');

    const priceEl = tooltipEl.querySelector('.hover-card-price');
    priceEl.textContent = data.price || '';

    const scoreEl = tooltipEl.querySelector('.hover-card-score');
    if (data.score && data.score !== '-') {
      scoreEl.textContent = '⭐ ' + data.score;
      scoreEl.hidden = false;
    } else {
      scoreEl.hidden = true;
    }

    const featuresEl = tooltipEl.querySelector('.hover-card-features');
    if (data.features) {
      featuresEl.textContent = data.features;
      featuresEl.hidden = false;
    } else {
      featuresEl.hidden = true;
    }

    const summaryEl = tooltipEl.querySelector('.hover-card-summary');
    if (data.summary) {
      summaryEl.textContent = data.summary.length > 120
        ? data.summary.substring(0, 120) + '…'
        : data.summary;
      summaryEl.hidden = false;
    } else {
      summaryEl.hidden = true;
    }
  }

  function positionTooltip(trigger) {
    if (!tooltipEl) return;

    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = tooltipEl.getBoundingClientRect();
    const viewW = window.innerWidth;
    const viewH = window.innerHeight;

    // RTL: prefer left side (above trigger)
    let top = triggerRect.top - tooltipRect.height - 8;
    let left = triggerRect.left + (triggerRect.width / 2) - (tooltipRect.width / 2);

    // If tooltip goes above viewport, show below
    if (top < EDGE_PADDING) {
      top = triggerRect.bottom + 8;
    }

    // Clamp horizontal
    if (left < EDGE_PADDING) left = EDGE_PADDING;
    if (left + tooltipRect.width > viewW - EDGE_PADDING) {
      left = viewW - tooltipRect.width - EDGE_PADDING;
    }

    // Clamp vertical
    if (top + tooltipRect.height > viewH - EDGE_PADDING) {
      top = viewH - tooltipRect.height - EDGE_PADDING;
    }

    tooltipEl.style.top = top + 'px';
    tooltipEl.style.left = left + 'px';
  }

  function showTooltip(trigger, data) {
    createTooltip();
    populateTooltip(data);
    tooltipEl.classList.add('visible');
    tooltipEl.setAttribute('aria-hidden', 'false');
    currentTrigger = trigger;
    positionTooltip(trigger);
  }

  function hideTooltip() {
    if (tooltipEl) {
      tooltipEl.classList.remove('visible');
      tooltipEl.setAttribute('aria-hidden', 'true');
    }
    currentTrigger = null;
  }

  function handleMouseEnter(e) {
    const trigger = e.currentTarget;
    clearTimeout(hideTimer);

    if (currentTrigger === trigger) return;

    showTimer = setTimeout(function() {
      const data = getListingData(trigger);
      if (data) {
        showTooltip(trigger, data);
      }
    }, HOVER_DELAY);
  }

  function handleMouseLeave() {
    clearTimeout(showTimer);
    hideTimer = setTimeout(hideTooltip, HIDE_DELAY);
  }

  function handleClick(e) {
    // Don't interfere with actual link clicks
    if (e.target.closest('a, button')) return;
    hideTooltip();
  }

  function handleScroll() {
    if (currentTrigger) {
      positionTooltip(currentTrigger);
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      hideTooltip();
    }
  }

  // Public API
  window.hoverCard = {
    init: function() {
      document.querySelectorAll('.hover-trigger').forEach(function(el) {
        el.removeEventListener('mouseenter', handleMouseEnter);
        el.removeEventListener('mouseleave', handleMouseLeave);
        el.addEventListener('mouseenter', handleMouseEnter);
        el.addEventListener('mouseleave', handleMouseLeave);
        el.addEventListener('click', handleClick);
      });

      document.addEventListener('scroll', handleScroll, true);
      document.addEventListener('keydown', handleKeydown);
    },

    refresh: function() {
      // Re-init after DOM changes (new cards loaded)
      this.init();
    },

    // Manual show/hide for programmatic use
    show: function(trigger, data) {
      createTooltip();
      showTooltip(trigger, data);
    },

    hide: hideTooltip,
  };

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { hoverCard.init(); });
  } else {
    hoverCard.init();
  }
})();
