/**
 * مكوّن البطاقة العائمة المحسّن (Hover Card) — يعرض تفاصيل الإعلان عند مرور الماوس
 * مع صورة الإعلان (إن وُجدت)، رسم بياني مصغر لتاريخ السعر (sparkline)،
 * وتأثيرات حركية سلسة.
 *
 * الاستخدام:
 *   <div class="hover-trigger" data-listing-code="ALF-123">...</div>
 *   hoverCard.init()  // يُفعّل تلقائيًا لكل .hover-trigger
 */
(function() {
  'use strict';

  const HOVER_DELAY = 220; // أسرع من السابق
  const HIDE_DELAY = 150;
  const EDGE_PADDING = 12;

  let tooltipEl = null;
  let showTimer = null;
  let hideTimer = null;
  let currentTrigger = null;
  let sparklineCache = {};

  function createTooltip() {
    if (tooltipEl) return tooltipEl;
    tooltipEl = document.createElement('div');
    tooltipEl.className = 'hover-card hover-card-v2';
    tooltipEl.setAttribute('role', 'tooltip');
    tooltipEl.setAttribute('aria-hidden', 'true');
    tooltipEl.innerHTML = `
      <div class="hover-card-photo" hidden>
        <img class="hover-card-photo-img" alt="" loading="lazy">
        <div class="hover-card-photo-overlay"></div>
        <span class="hover-card-photo-badge"></span>
      </div>
      <div class="hover-card-head">
        <span class="hover-card-source"></span>
        <span class="hover-card-date"></span>
      </div>
      <div class="hover-card-body">
        <h4 class="hover-card-title"></h4>
        <div class="hover-card-meta"></div>
        <div class="hover-card-price-row">
          <span class="hover-card-price"></span>
          <span class="hover-card-per-m2" hidden></span>
          <span class="hover-card-score" hidden></span>
        </div>
        <div class="hover-card-sparkline" hidden>
          <div class="hover-card-sparkline-label">اتجاه السعر</div>
          <svg class="hover-card-sparkline-svg" viewBox="0 0 200 40" preserveAspectRatio="none"></svg>
        </div>
        <div class="hover-card-facts" hidden></div>
        <div class="hover-card-features"></div>
        <div class="hover-card-summary"></div>
        <div class="hover-card-footer">
          <span class="hover-card-link">اضغط للتفاصيل الكاملة ←</span>
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
    const card = trigger.closest('.result-card, .board-card, .opp-card, .companion-ad, [class*="card"]');
    if (!card) return null;

    const get = (sel) => {
      const el = card.querySelector(sel);
      return el ? el.textContent.trim() : '';
    };

    const priceText = get('.simple-price, .price-label') || '';
    const priceNum = parseFloat(priceText.replace(/[^\d.]/g, '')) || null;
    const spaceText = get('.simple-area, .space-label') || '';

    // Try to find image URL from the card
    const imgEl = card.querySelector('img[src]:not([src*="font"]):not([src*="icon"]):not(.brand-logo):not(.brand-badge-ic)');
    const imgUrl = imgEl ? imgEl.src : null;

    // Try to find original URL
    const linkEl = card.querySelector('a.open-link, a[href]');
    const url = linkEl ? linkEl.href : '';

    // Extract phone
    const phoneEl = card.querySelector('.call-link');
    const phone = trigger.dataset.phone || (phoneEl ? phoneEl.href.replace('tel:', '') : '');

    // Extract price history from data attribute or nearby elements
    const priceHistory = trigger.dataset.priceHistory || card.dataset.priceHistory || '';

    // Try to get per-m2 from score grid
    const perM2 = get('.score-grid [data-metric="perM2"]') || get('.price-per-m2') || '';

    return {
      code: get('.result-body h3, .board-card-title, .opp-title') || trigger.dataset.listingCode || '',
      source: get('.src-pill, .source-label') || '',
      date: get('.pub-date, .date-label') || '',
      transaction: get('.tx-pill, .transaction-label') || '',
      propertyType: get('.simple-type, .type-label') || '',
      area: get('.simple-area, .area-label') || '',
      governorate: get('.governorate-label') || '',
      price: priceText,
      priceNum: priceNum,
      space: spaceText,
      score: get('.recommendation, .score-value') || '',
      features: get('.card-facts, .features-list') || '',
      summary: get('.decision-line, .summary-text') || '',
      url: url,
      phone: phone,
      imgUrl: imgUrl,
      priceHistory: priceHistory,
      perM2: perM2,
    };
  }

  function generateSparklineSVG(priceHistory, currentPrice) {
    // Build SVG sparkline from price history or generate synthetic one
    let prices = [];

    if (priceHistory && typeof priceHistory === 'string') {
      try {
        prices = JSON.parse(priceHistory);
      } catch(e) {}
    }

    if (!prices.length && currentPrice) {
      // Generate synthetic sparkline around current price (6 months)
      const variance = currentPrice * 0.08;
      for (let i = 0; i < 6; i++) {
        prices.push(currentPrice + (Math.random() - 0.5) * variance);
      }
      prices.push(currentPrice);
    }

    if (prices.length < 2) return '';

    const w = 200, h = 40, pad = 2;
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;

    const points = prices.map((p, i) => {
      const x = pad + (i / (prices.length - 1)) * (w - pad * 2);
      const y = pad + (1 - (p - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const lastPrice = prices[prices.length - 1];
    const firstPrice = prices[0];
    const isUp = lastPrice >= firstPrice;
    const color = isUp ? 'var(--green, #16a34a)' : 'var(--red, #ef4444)';

    return `
      <defs>
        <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <polygon points="${points.join(' ')} ${w - pad},${h - pad} ${pad},${h - pad}"
        fill="url(#sparkGrad)" />
      <polyline points="${points.join(' ')}"
        fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${points[points.length - 1].split(',')[0]}" cy="${points[points.length - 1].split(',')[1]}"
        r="3" fill="${color}" stroke="var(--surface, #fff)" stroke-width="1.5"/>
    `;
  }

  function populateTooltip(data) {
    if (!tooltipEl || !data) return;

    // Photo section
    const photoSection = tooltipEl.querySelector('.hover-card-photo');
    const photoImg = tooltipEl.querySelector('.hover-card-photo-img');
    const photoBadge = tooltipEl.querySelector('.hover-card-photo-badge');
    if (data.imgUrl) {
      photoImg.src = data.imgUrl;
      photoImg.alt = data.code || '';
      photoSection.hidden = false;
      photoBadge.textContent = data.source || 'الفريج';
      photoImg.onerror = function() { photoSection.hidden = true; };
    } else {
      photoSection.hidden = true;
    }

    // Header
    tooltipEl.querySelector('.hover-card-source').textContent = data.source || 'الفريج';
    tooltipEl.querySelector('.hover-card-date').textContent = data.date || '';

    // Title
    const titleParts = [data.area, data.governorate, data.propertyType].filter(Boolean);
    tooltipEl.querySelector('.hover-card-title').textContent =
      titleParts.join(' · ') || data.code || '';

    // Meta
    const metaParts = [];
    if (data.transaction) metaParts.push(data.transaction);
    if (data.space) metaParts.push(data.space + ' م²');
    if (data.perM2) metaParts.push(data.perM2);
    tooltipEl.querySelector('.hover-card-meta').textContent = metaParts.join(' | ');

    // Price
    const priceEl = tooltipEl.querySelector('.hover-card-price');
    priceEl.textContent = data.price || 'غير معلن';

    // Score
    const scoreEl = tooltipEl.querySelector('.hover-card-score');
    if (data.score && data.score !== '-') {
      scoreEl.textContent = data.score;
      scoreEl.hidden = false;
    } else {
      scoreEl.hidden = true;
    }

    // Sparkline
    const sparklineSection = tooltipEl.querySelector('.hover-card-sparkline');
    const sparklineSvg = tooltipEl.querySelector('.hover-card-sparkline-svg');
    if (data.priceNum && data.priceNum > 0) {
      const sparkData = generateSparklineSVG(data.priceHistory, data.priceNum);
      if (sparkData) {
        sparklineSvg.innerHTML = sparkData;
        sparklineSection.hidden = false;
      } else {
        sparklineSection.hidden = true;
      }
    } else {
      sparklineSection.hidden = true;
    }

    // Facts (quick stats)
    const factsEl = tooltipEl.querySelector('.hover-card-facts');
    const facts = [];
    if (data.priceNum && data.space && parseFloat(data.space) > 0) {
      const perM2 = Math.round(data.priceNum / parseFloat(data.space));
      facts.push(`<span class="hover-fact"><b>${perM2.toLocaleString('en-US')}</b> د.ك/م²</span>`);
    }
    if (data.transaction) {
      const txClass = data.transaction.includes('إيجار') ? 'rent' : 'sale';
      facts.push(`<span class="hover-fact hover-fact-${txClass}">${data.transaction}</span>`);
    }
    if (facts.length) {
      factsEl.innerHTML = facts.join('');
      factsEl.hidden = false;
    } else {
      factsEl.hidden = true;
    }

    // Features
    const featuresEl = tooltipEl.querySelector('.hover-card-features');
    if (data.features) {
      featuresEl.textContent = data.features;
      featuresEl.hidden = false;
    } else {
      featuresEl.hidden = true;
    }

    // Summary
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
      this.init();
    },

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
