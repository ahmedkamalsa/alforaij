const state = {
  mode: "search_and_value",
  report: null,
  chatMessages: [],
  chatSubmitting: false,
};

const boardState = {
  allRecords: [],
  records: [],
  metrics: [],
  opportunities: { count: 0, items: [], calculation: "" },
  matching: null,
  expandedGovernorates: new Set(),
  activeMetric: "movement",
};

const boardMetricLabels = {
  movement: "حركة الدلال",
  opportunities: "فرص محسوبة",
  saleOffers: "عروض للبيع",
  buyRequests: "طلبات شراء",
  rentOffers: "عروض الإيجار",
  rentRequests: "طلبات الإيجار",
};

const recentAreasKey = "alforaij_recent_areas_v2";

const $ = (id) => document.getElementById(id);
const API_BASE = String(window.ALFORAIJ_API_BASE || localStorage.getItem("ALFORAIJ_API_BASE") || "").replace(/\/$/, "");
const STATIC_SNAPSHOT_MODE = !API_BASE;
const STATIC_DATA_MAP = {
  "/api/health": "health.json",
  "/api/sources": "sources.json",
  "/api/dashboard/summary": "dashboard-summary.json",
  "/api/opportunities": "opportunities.json",
  "/api/opportunities/history": "opportunities-history.json",
  "/api/market-matching": "market-matching.json",
  "/api/opportunity-delta": "opportunity-delta.json",
  "/api/weekly-digest": "weekly-digest.json",
  "/api/whatsapp-alerts": "whatsapp-alerts.json",
  "/api/outreach/stats": "outreach-stats.json",
  "/api/clients": "clients.json",
  "/api/update-notifications": "update-notifications.json",
  "/api/daily-agent/status": "daily-agent-status.json",
  "/api/official-reference-sources": "official-reference-sources.json",
};

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function staticDataUrl(path) {
  const clean = String(path || "").split("?")[0];
  const file = STATIC_DATA_MAP[clean];
  return file ? `static-data/${file}` : "";
}

async function fetchStaticJson(path) {
  const url = staticDataUrl(path);
  if (!url) throw new Error("No static snapshot for " + path);
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function getJson(path) {
  if (STATIC_SNAPSHOT_MODE) return fetchStaticJson(path);
  try {
    const response = await fetch(apiUrl(path));
    if (!response.ok) throw new Error(await response.text());
    return await response.json();
  } catch (err) {
    const fallback = staticDataUrl(path);
    if (!fallback) throw err;
    return fetchStaticJson(path);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeArabic(value) {
  return String(value || "")
    .replace(/[إأآا]/g, "ا")
    .replace(/[ىي]/g, "ي")
    .replace(/[ة]/g, "ه")
    .replace(/[^\u0600-\u06FFa-zA-Z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function uniqueValues(values) {
  return [...new Set((values || []).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "ar"));
}

function setOptions(id, values) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = "";
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    el.appendChild(option);
  }
}

function rememberRecentArea(area) {
  const clean = String(area || "").trim();
  if (!clean) return;
  const current = readRecentAreas().filter((item) => normalizeArabic(item) !== normalizeArabic(clean));
  current.unshift(clean);
  localStorage.setItem(recentAreasKey, JSON.stringify(current.slice(0, 8)));
}

function readRecentAreas() {
  try {
    const parsed = JSON.parse(localStorage.getItem(recentAreasKey) || "[]");
    return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
  } catch {
    return [];
  }
}

function metricMatches(row, metric) {
  if (metric === "opportunities") return Number(row.opportunityScore) > 0;
  const tx = normalizeArabic(row.transaction);
  if (metric === "saleOffers") return tx.includes("بيع") && !tx.includes("مطلوب");
  if (metric === "buyRequests") return tx.includes("مطلوب") && tx.includes("شراء");
  if (metric === "rentOffers") return (tx.includes("ايجار") || tx.includes("اجار")) && !tx.includes("مطلوب");
  if (metric === "rentRequests") return tx.includes("مطلوب") && (tx.includes("ايجار") || tx.includes("اجار"));
  return true;
}

function countMetric(rows, metric) {
  return (rows || []).filter((row) => metricMatches(row, metric)).length;
}

function boardFilterValues() {
  return {
    metric: $("boardMetricFilter")?.value || "movement",
    governorate: $("boardGovernorateFilter")?.value.trim() || "",
    area: $("boardAreaFilter")?.value.trim() || "",
    transaction: $("boardTransactionFilter")?.value.trim() || "",
    propertyType: $("boardPropertyTypeFilter")?.value.trim() || "",
    listingMode: $("boardListingModeFilter")?.value || "",
  };
}

function selectedBoardPlatforms() {
  const inputs = [...document.querySelectorAll('input[name="boardPlatform"]')];
  if (!inputs.length) {
    return {
      sourceMode: $("sourceModeField")?.value || "all",
      selectedSource: $("selectedSourceField")?.value || "",
      selectedSources: [],
      includeLocal: ($("sourceModeField")?.value || "all") !== "source",
      includeExternal: ($("sourceModeField")?.value || "all") !== "local",
      label: "كل المنصات",
    };
  }
  const values = inputs.filter((input) => input.checked).map((input) => input.value).filter(Boolean);
  if (!values.length || values.includes("__all")) {
    return {
      sourceMode: "all",
      selectedSource: "",
      selectedSources: [],
      includeLocal: true,
      includeExternal: true,
      label: "كل المنصات",
    };
  }
  const includeLocal = values.includes("الفريج");
  const selectedSources = values.filter((value) => value !== "الفريج");
  return {
    sourceMode: selectedSources.length ? "custom" : "local",
    selectedSource: selectedSources[0] || "",
    selectedSources,
    includeLocal,
    includeExternal: selectedSources.length > 0,
    label: values.join("، "),
  };
}

function syncPlatformSelect() {
  const inputs = [...document.querySelectorAll('input[name="boardPlatform"]')];
  if (!inputs.length) return;
  const selected = inputs.filter((input) => input.checked).map((input) => input.value);
  if (selected.includes("__all") && selected.length > 1) {
    for (const input of inputs) {
      if (input.value === "__all") input.checked = false;
    }
  }
  if (!inputs.some((input) => input.checked)) {
    const all = inputs.find((input) => input.value === "__all");
    if (all) all.checked = true;
  }
}

function rowMatchesBoardFilters(row, ignoreArea = false, ignoreGovernorate = false, ignoreMetric = false) {
  const filters = boardFilterValues();
  if (!ignoreMetric && !metricMatches(row, filters.metric)) return false;
  if (!ignoreGovernorate && filters.governorate && normalizeArabic(row.governorate) !== normalizeArabic(filters.governorate)) return false;
  if (!ignoreArea && filters.area && normalizeArabic(row.area) !== normalizeArabic(filters.area)) return false;
  if (filters.transaction && !normalizeArabic(row.transaction).includes(normalizeArabic(filters.transaction))) return false;
  if (filters.propertyType && normalizeArabic(row.propertyType) !== normalizeArabic(filters.propertyType)) return false;
  if (filters.listingMode && normalizeArabic(row.listingMode) !== normalizeArabic(filters.listingMode)) return false;
  return true;
}

function boardTextFromFilters(overrides = {}) {
  const filters = { ...boardFilterValues(), ...overrides };
  const parts = [];
  const metric = filters.metric && filters.metric !== "movement" ? boardMetricLabels[filters.metric] : "";
  const transaction = filters.transaction || metric;
  if (transaction) parts.push(transaction);
  if (filters.propertyType) parts.push(filters.propertyType);
  if (filters.area) parts.push(`في ${filters.area}`);
  else if (filters.governorate) parts.push(`في ${filters.governorate}`);
  return parts.join(" ").trim() || "حركة الدلال";
}

function syncBoardToSearch(overrides = {}) {
  const filters = { ...boardFilterValues(), ...overrides };
  const metric = filters.metric || "movement";
  const transaction = filters.transaction || (metric === "saleOffers" ? "للبيع" : metric === "buyRequests" ? "مطلوب للشراء" : metric === "rentOffers" ? "للإيجار" : metric === "rentRequests" ? "مطلوب للإيجار" : "");
  const typeField = $("typeField");
  const transactionField = $("transactionField");
  const areasField = $("areasField");
  const chatInput = $("chatInput");
  if (transactionField) transactionField.value = transaction;
  if (typeField) typeField.value = filters.propertyType || "";
  if (areasField) areasField.value = filters.area || "";
  if (chatInput) chatInput.value = boardTextFromFilters({ ...filters, transaction });
  if (filters.area) rememberRecentArea(filters.area);
}

async function runBoardAnalysis(overrides = {}) {
  syncBoardToSearch(overrides);
  await sendChat();
}

// تحويل علامات **النص** إلى خط عريض بعد تأمين HTML (بدون مخاطرة XSS)
function formatSummary(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

// أول جملة مفيدة من الملخص فقط (دون العناوين العريضة) لفقاعة الشات المختصرة —
// التفاصيل الكاملة تبقى في لوحة التقرير تحتها فلا يتكرر النص في مكانين
function summaryLead(summary) {
  if (!summary) return "";
  const lines = String(summary)
    .split(/\n/)
    .map((line) => line.replace(/^\*\*[^*]*\*\*\s*/g, "").trim())
    .filter(Boolean);
  return lines[0] || "";
}

function extractedFiltersHtml(filters) {
  const list = (filters || []).filter((item) => item && item.value);
  if (!list.length) return "";
  return `<div class="extracted-filters">${list.map((item) => `
    <span class="filter-chip" title="${escapeHtml(item.source || "")}">
      <b>${escapeHtml(item.label || "")}</b>${escapeHtml(item.value || "")}
    </span>
  `).join("")}</div>`;
}

function setStatus(text) {
  const el = $("healthStatus");
  if (el) el.textContent = text;
}

function persistenceLabel(value) {
  if (!value) return "-";
  if (value.status === "saved") return "تم الحفظ";
  if (value.status === "not_configured") return "غير مضبوط";
  if (value.status === "failed") return "فشل الحفظ";
  return value.status || "-";
}

function sourceMatchesPlatformScope(row, scope) {
  if (!scope || scope.sourceMode === "all") return true;
  const source = normalizeArabic(row.source || "");
  const isLocal = source.includes(normalizeArabic("الفريج")) || source.includes("alforaij");
  if (scope.includeLocal && !scope.includeExternal) return isLocal;
  if (!scope.includeLocal && isLocal) return false;
  const selected = (scope.selectedSources || []).map(normalizeArabic);
  return !selected.length || selected.some((name) => source.includes(name) || name.includes(source));
}

function staticAnalyzeReport(payload) {
  const filters = payload.filters || {};
  const text = String(payload.text || "");
  const area = String(filters.areas || filters.area || "").trim();
  const propertyType = String(filters.propertyType || "").trim();
  const transaction = String(filters.transaction || "").trim();
  const minArea = Number(filters.minArea || 0);
  const maxArea = Number(filters.maxArea || 0);
  const budget = Number(filters.budget || filters.rentBudget || 0);
  const sourceScope = selectedBoardPlatforms();
  let rows = (boardState.allRecords || boardState.records || []).slice();

  if (area) rows = rows.filter((row) => normalizeArabic(row.area).includes(normalizeArabic(area)) || normalizeArabic(area).includes(normalizeArabic(row.area)));
  if (propertyType) rows = rows.filter((row) => normalizeArabic(row.propertyType).includes(normalizeArabic(propertyType)));
  if (transaction) rows = rows.filter((row) => normalizeArabic(row.transaction).includes(normalizeArabic(transaction)));
  if (minArea) rows = rows.filter((row) => Number(row.space || 0) >= minArea);
  if (maxArea) rows = rows.filter((row) => Number(row.space || 0) <= maxArea);
  rows = rows.filter((row) => sourceMatchesPlatformScope(row, sourceScope));

  const priced = rows.filter((row) => Number(row.price || 0) > 0);
  const medianPool = priced.map((row) => Number(row.price || 0)).sort((a, b) => a - b);
  const median = medianPool.length ? medianPool[Math.floor(medianPool.length / 2)] : 0;

  const results = rows.map((row) => {
    const price = Number(row.price || 0);
    const priceScore = budget && price ? Math.max(0, Math.min(100, 100 - Math.abs(price - budget) / budget * 100)) : Number(row.opportunityScore || 50);
    const score = Number(row.opportunityScore || priceScore || 50);
    const comps = priced
      .filter((other) => other.code !== row.code && (!row.area || normalizeArabic(other.area) === normalizeArabic(row.area)))
      .slice(0, 4)
      .map((other) => ({
        code: other.code,
        area: other.area,
        price: other.price,
        priceText: other.priceText,
        source: other.source,
        url: other.originalUrl,
        summary: other.summary,
      }));
    return {
      code: row.code || "STATIC",
      area: row.area,
      governorate: row.governorate,
      transaction: row.transaction,
      propertyType: row.propertyType,
      detailClass: row.detailClass,
      listingType: row.listingMode,
      source: row.source,
      price,
      priceText: row.priceText || (price ? formatMoney(price) : ""),
      space: row.space,
      publishedDate: row.publishedDate,
      originalUrl: row.originalUrl,
      summary: row.summary || row.features || "",
      features: row.features || "",
      recommendationScore: Math.round(score),
      matchScore: Math.round(priceScore || score),
      marketMedian: median,
      priceRatio: median && price ? price / median : null,
      valuationLabel: row.opportunityLabel || (score >= 75 ? "فرصة قوية" : score >= 60 ? "مناسبة" : "تحتاج مراجعة"),
      valuationReason: row.opportunityReason || "تقييم من لقطة البيانات المنشورة: مطابقة الفلاتر، السعر، وجود المقارنات، ومصدر الإعلان.",
      decisionLine: "نسخة GitHub Pages تستخدم لقطة بيانات منشورة. التحديث الحي يحتاج API backend.",
      reasons: [
        area ? `مطابق للمنطقة: ${area}` : "مطابق لنطاق البحث",
        propertyType ? `نوع العقار: ${propertyType}` : "نوع العقار من بيانات الإعلان",
        comps.length ? `يوجد ${comps.length} مقارنات من نفس النطاق` : "المقارنات محدودة في اللقطة الحالية",
      ],
      warnings: STATIC_SNAPSHOT_MODE ? ["التحليل من لقطة منشورة وليس اتصالًا حيًا"] : [],
      comparables: comps,
      numberSources: {
        price: { value: row.priceText || price, source: row.source, note: "من بيانات الإعلان" },
        space: { value: row.space || null, source: row.source, note: row.space ? "من بيانات الإعلان" : "غير مذكورة" },
        marketMedian: { value: median || null, source: "لقطة المقارنات", note: `${priced.length} إعلان بسعر معلن` },
        comparablesCount: { value: comps.length, source: "لقطة المقارنات", note: "نفس النطاق المتاح" },
        confidence: { value: Math.round(score), source: "تقييم static", note: "السعر + الفلاتر + الأدلة المتاحة" },
      },
      matchBreakdown: [
        { name: "مطابقة الفلاتر", points: area || propertyType ? 40 : 20, value: "حسب المدخلات", weight: "40%" },
        { name: "السعر", points: Math.round(priceScore || 0), value: row.priceText || price || "غير معلن", weight: "35%" },
        { name: "الأدلة", points: comps.length * 10, value: `${comps.length} مقارنات`, weight: "25%" },
      ],
      recommendationBreakdown: [
        { name: "درجة الفرصة", points: Math.round(score), value: row.opportunityReason || "لقطة منشورة", weight: "100%" },
      ],
    };
  }).sort((a, b) => b.recommendationScore - a.recommendationScore).slice(0, 20);

  return {
    generatedAt: new Date().toLocaleString("ar-KW"),
    analysisMethod: "local",
    summary: results.length
      ? `تم تحليل ${results.length} نتيجة من لقطة GitHub Pages. أفضل نتيجة ${results[0].code} بدرجة ${results[0].recommendationScore}/100.`
      : "لا توجد نتائج مطابقة في لقطة البيانات المنشورة. جرّب توسيع المنطقة أو المنصة.",
    request: { rawText: text, areas: area ? [area] : [], propertyType, transaction },
    extractedFilters: [
      { label: "المنطقة", value: area, source: "الفلاتر" },
      { label: "نوع العقار", value: propertyType, source: "الفلاتر" },
      { label: "العملية", value: transaction, source: "الفلاتر" },
    ],
    searchScope: { note: "تحليل من لقطة static منشورة. النتائج الحية تحتاج API backend." },
    rankingMethod: {
      title: "ترتيب static",
      description: "الترتيب حسب درجة الفرصة، مطابقة الفلاتر، السعر، وعدد المقارنات المتاحة في اللقطة.",
      weights: [
        { label: "مطابقة الطلب", value: "40%" },
        { label: "جاذبية السعر", value: "35%" },
        { label: "الأدلة", value: "25%" },
      ],
    },
    sourceStatus: [{ name: "GitHub Pages static snapshot", status: "success", records: rows.length }],
    similarExternal: { items: results.slice(0, 6), sources: Array.from(new Set(results.map((r) => r.source).filter(Boolean))) },
    profitOpportunities: { items: [] },
    results,
    persistence: { status: "static" },
  };
}

async function postJson(path, payload) {
  if (STATIC_SNAPSHOT_MODE && path === "/api/analyze") return staticAnalyzeReport(payload);
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function addChatMessage(role, htmlContent) {
  const win = $("chatWindow");
  if (!win) return;
  const msg = document.createElement("div");
  msg.className = `chat-message ${role}`;
  msg.innerHTML = htmlContent;
  win.appendChild(msg);
  win.scrollTop = win.scrollHeight;
}

function clearChat() {
  const win = $("chatWindow");
  if (!win) return;
  win.innerHTML = "";
  state.chatMessages = [];
}

function filteredBoardRows() {
  return boardState.records.filter((row) => rowMatchesBoardFilters(row));
}

function updateBoardSummary(rows) {
  const el = $("boardFilterSummary");
  if (!el) return;
  const filters = boardFilterValues();
  const parts = [
    boardMetricLabels[filters.metric] || "حركة الدلال",
    filters.governorate,
    filters.area,
    filters.transaction,
    filters.propertyType,
    filters.listingMode,
  ].filter(Boolean);
  const opportunityCount = rows.filter((row) => Number(row.opportunityScore) > 0).length;
  const totalScored = Number(boardState.opportunities?.totalScored || opportunityCount);
  el.textContent = `${parts.join(" - ") || "كل السجلات"} | ${rows.length} إعلان | ${opportunityCount} فرصة ظاهرة | ${totalScored} دخلت التقييم`;
}

function renderBoardMetricCards(rows) {
  const root = $("boardMetricCards");
  if (!root) return;
  const activeMetric = boardFilterValues().metric || "movement";
  root.innerHTML = Object.entries(boardMetricLabels).map(([key, label]) => {
    const count = countMetric(rows, key);
    const active = key === activeMetric ? " active" : "";
    return `
      <button class="board-metric-card${active}" type="button" data-board-metric="${escapeHtml(key)}">
        <span>${escapeHtml(label)}</span>
        <strong>${count.toLocaleString("en-US")}</strong>
        <small>اضغط للاختيار</small>
      </button>
    `;
  }).join("");
}

function renderBoardStats(rows) {
  const root = $("boardStats");
  if (!root) return;
  const priced = rows.filter((row) => Number(row.price) > 0).length;
  const withSpace = rows.filter((row) => Number(row.space) > 0).length;
  const opportunities = rows.filter((row) => Number(row.opportunityScore) > 0).length;
  const totalScored = Number(boardState.opportunities?.totalScored || opportunities);
  const evidence = rows.reduce((sum, row) => sum + Number(row.opportunityEvidenceCount || 0), 0);
  const direct = rows.filter((row) => normalizeArabic(row.listingMode).includes("مباشر")).length;
  const office = rows.filter((row) => normalizeArabic(row.listingMode).includes("مكتب")).length;
  root.innerHTML = [
    ["إجمالي الاختيار", rows.length],
    ["فرص ظاهرة", opportunities],
    ["دخلت التقييم", totalScored],
    ["أدلة ومقارنات", evidence],
    ["أسعار معلنة", priced],
    ["مساحات موثقة", withSpace],
    ["مباشر", direct],
    ["مكتب", office],
  ].map(([label, value]) => `
    <div class="board-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${Number(value).toLocaleString("en-US")}</strong>
    </div>
  `).join("");
}

function renderCompanionAds(rows) {
  const root = $("boardCompanionAds");
  if (!root) return;
  const items = rows
    .filter((row) => row.code || row.summary || row.originalUrl)
    .sort((a, b) => (Number(b.opportunityScore || 0) - Number(a.opportunityScore || 0)) || String(b.publishedDate || "").localeCompare(String(a.publishedDate || "")))
    .slice(0, 8);
  if (!items.length) {
    root.innerHTML = '<div class="empty compact-empty">لا توجد إعلانات مرافقة حسب الاختيارات الحالية.</div>';
    return;
  }
  root.innerHTML = items.map((item) => `
    <article class="companion-ad">
      <div class="companion-head">
        <strong>${escapeHtml(item.code || "إعلان")}</strong>
        <span>${escapeHtml(item.source || "مصدر غير محدد")}</span>
      </div>
      ${item.opportunityScore ? `<div class="companion-score">فرصة ${escapeHtml(Math.round(Number(item.opportunityScore)))} / 100 · ${escapeHtml(item.opportunityComparablesCount || 0)} مقارنة · ${escapeHtml(item.opportunityEvidenceCount || 0)} دليل</div>` : ""}
      <h4>${escapeHtml([item.area, item.propertyType].filter(Boolean).join(" - ") || "عقار")}</h4>
      <p>${escapeHtml(item.summary || item.features || "")}</p>
      <div class="companion-facts">
        <span><b>السعر</b>${escapeHtml(item.priceText || (item.price ? formatMoney(item.price) : "غير معلن"))}</span>
        <span><b>المساحة</b>${item.space ? `${escapeHtml(item.space)} م²` : "غير مذكورة"}</span>
        <span><b>التاريخ</b>${escapeHtml(item.publishedDate || "غير متاح")}</span>
      </div>
      ${item.opportunityReason ? `<p class="companion-reason">${escapeHtml(item.opportunityReason)}</p>` : ""}
      <div class="companion-actions">
        <button type="button" data-board-ad-code="${escapeHtml(item.code || "")}" data-board-ad-area="${escapeHtml(item.area || "")}" data-board-ad-type="${escapeHtml(item.propertyType || "")}">تحليل</button>
        ${item.originalUrl ? `<a href="${escapeHtml(item.originalUrl)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي</a>` : ""}
      </div>
    </article>
  `).join("");
}

function matchInCurrentBoardScope(match) {
  const filters = boardFilterValues();
  const sourceScope = selectedBoardPlatforms();
  if (filters.governorate && normalizeArabic(match.governorate) !== normalizeArabic(filters.governorate)) return false;
  if (filters.area && normalizeArabic(match.area) !== normalizeArabic(filters.area)) return false;
  if (filters.propertyType && normalizeArabic(match.propertyType) !== normalizeArabic(filters.propertyType)) return false;
  if (sourceScope.sourceMode !== "all") {
    const source = normalizeArabic(match.source || "");
    const selected = sourceScope.selectedSources.map(normalizeArabic);
    const isLocal = source.includes("الفريج") || source.includes("alforaij");
    if (sourceScope.includeLocal && !sourceScope.includeExternal && !isLocal) return false;
    if (selected.length && !selected.some((name) => source.includes(name))) return false;
  }
  return true;
}

function renderBoardMarketMatches(rows) {
  const root = $("boardMarketMatches");
  if (!root) return;
  const data = boardState.matching;
  if (!data) {
    root.innerHTML = '<div class="empty compact-empty">جاري تحميل فرص الربط...</div>';
    return;
  }
  const currentCodes = new Set(rows.map((row) => String(row.code || "")));
  const cards = [];
  for (const req of data.requests || []) {
    for (const match of req.matches || []) {
      if (!matchInCurrentBoardScope(match)) continue;
      if (currentCodes.size && match.code && !currentCodes.has(String(match.code)) && boardFilterValues().metric !== "movement") continue;
      const budget = Number(req.budget || 0);
      const price = Number(match.price || 0);
      const margin = budget && price && budget > price ? budget - price : 0;
      cards.push({ req, match, margin });
    }
  }
  cards.sort((a, b) => (b.margin - a.margin) || (Number(b.match.matchScore || 0) - Number(a.match.matchScore || 0)) || (Number(b.match.score || 0) - Number(a.match.score || 0)));
  const top = cards.slice(0, 5);
  if (!top.length) {
    root.innerHTML = '<div class="empty compact-empty">لا توجد فرص ربط مؤكدة حسب الفلاتر الحالية.</div>';
    return;
  }
  root.innerHTML = top.map(({ req, match, margin }) => {
    const kind = req.kind === "rent" ? "إيجار" : "شراء";
    const marginText = margin ? `${formatMoney(margin)} هامش محتمل` : "هامش غير محسوب";
    return `
      <article class="board-match-card">
        <div class="match-mini-head">
          <strong>${escapeHtml(kind)}: ${escapeHtml(req.area || match.area || "غير محددة")}</strong>
          <span>تطابق ${escapeHtml(match.matchScore || 0)} / 100</span>
        </div>
        <p>${escapeHtml(req.summary || req.transaction || "")}</p>
        <div class="match-mini-offer">
          <span>${escapeHtml(match.code || "")}</span>
          <b>${escapeHtml(match.priceText || formatMoney(match.price))}</b>
          <small>${escapeHtml(match.source || "")}</small>
        </div>
        <div class="match-margin">${escapeHtml(marginText)}</div>
        <div class="companion-actions">
          <button type="button" data-board-ad-code="${escapeHtml(match.code || "")}" data-board-ad-area="${escapeHtml(match.area || "")}" data-board-ad-type="${escapeHtml(match.propertyType || "")}">تحليل الفرصة</button>
          ${match.url ? `<a href="${escapeHtml(match.url)}" target="_blank" rel="noreferrer">فتح العرض</a>` : ""}
          ${req.url ? `<a href="${escapeHtml(req.url)}" target="_blank" rel="noreferrer">فتح الطلب</a>` : ""}
        </div>
      </article>
    `;
  }).join("");
}

function metricCells(rows, governorate = "", area = "") {
  const scope = rows.filter((row) => {
    if (governorate && row.governorate !== governorate) return false;
    if (area && row.area !== area) return false;
    return true;
  });
  return ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"].map((metric) => ({
    metric,
    count: countMetric(scope, metric),
  }));
}

function renderGovernorateTable(rows) {
  const body = $("governorateTableBody");
  if (!body) return;
  const governorates = uniqueValues(rows.map((row) => row.governorate));
  if (!governorates.length) {
    body.innerHTML = '<tr><td colspan="7">لا توجد بيانات حسب الفلاتر الحالية.</td></tr>';
    return;
  }
  const html = [];
  for (const governorate of governorates) {
    const govRows = rows.filter((row) => row.governorate === governorate);
    const cells = metricCells(rows, governorate);
    const expanded = boardState.expandedGovernorates.has(governorate);
    html.push(`
      <tr class="gov-row${expanded ? " expanded" : ""}" data-board-governorate="${escapeHtml(governorate)}">
        <td>
          <button class="gov-toggle" type="button" data-board-toggle-gov="${escapeHtml(governorate)}">${expanded ? "▲" : "▼"}</button>
          <strong>${escapeHtml(governorate)}</strong>
        </td>
        ${cells.map((cell) => `
          <td><button class="count-button" type="button" data-board-gov="${escapeHtml(governorate)}" data-board-metric-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"}>${cell.count.toLocaleString("en-US")}</button></td>
        `).join("")}
      </tr>
    `);
    if (expanded) {
      for (const area of uniqueValues(govRows.map((row) => row.area))) {
        const areaCells = metricCells(rows, governorate, area);
        html.push(`
          <tr class="area-row" data-board-area="${escapeHtml(area)}">
            <td><span class="area-indent">${escapeHtml(area)}</span></td>
            ${areaCells.map((cell) => `
              <td><button class="count-button area-count" type="button" data-board-gov="${escapeHtml(governorate)}" data-board-area-run="${escapeHtml(area)}" data-board-metric-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"}>${cell.count.toLocaleString("en-US")}</button></td>
            `).join("")}
          </tr>
        `);
      }
    }
  }
  body.innerHTML = html.join("");
}

function renderBoard() {
  const rows = filteredBoardRows();
  updateBoardSummary(rows);
  renderBoardMetricCards(boardState.records.filter((row) => rowMatchesBoardFilters(row, false, false, true)));
  renderBoardStats(rows);
  renderCompanionAds(rows);
  renderBoardMarketMatches(rows);
  renderGovernorateTable(rows);
}

async function loadDashboardBoard() {
  try {
    const platforms = selectedBoardPlatforms();
    const params = new URLSearchParams();
    if (platforms.selectedSources.length) {
      for (const source of platforms.selectedSources) params.append("platform", source);
    }
    if (platforms.includeLocal && platforms.sourceMode !== "all") params.append("platform", "الفريج");
    params.set("includeLocal", platforms.includeLocal ? "1" : "0");
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const data = await getJson(`/api/dashboard/summary${suffix}`);
    boardState.allRecords = data.records || [];
    boardState.records = STATIC_SNAPSHOT_MODE
      ? boardState.allRecords.filter((row) => sourceMatchesPlatformScope(row, platforms))
      : boardState.allRecords;
    boardState.metrics = data.metrics || [];
    boardState.opportunities = data.opportunities || { count: 0, items: [], calculation: "" };
    getJson("/api/market-matching")
      .then((matching) => {
        boardState.matching = matching;
        renderBoard();
      })
      .catch(() => {
        boardState.matching = { requests: [] };
        renderBoard();
      });
    const governorates = uniqueValues(boardState.records.map((row) => row.governorate));
    const recentAreas = readRecentAreas();
    setOptions("boardGovernorates", governorates);
    setOptions("boardAreas", uniqueValues([...recentAreas, ...boardState.records.map((row) => row.area)]));
    setOptions("boardTransactions", uniqueValues(boardState.records.map((row) => row.transaction)));
    setOptions("boardPropertyTypes", uniqueValues(boardState.records.map((row) => row.propertyType)));
    const modeSelect = $("boardListingModeFilter");
    if (modeSelect) {
      modeSelect.innerHTML = '<option value="">كل الأنماط</option>' + uniqueValues(boardState.records.map((row) => row.listingMode))
        .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
        .join("");
    }
    if (governorates[0]) boardState.expandedGovernorates.add(governorates[0]);
    renderBoard();
  } catch (err) {
    const body = $("governorateTableBody");
    if (body) body.innerHTML = `<tr><td colspan="7">تعذر تحميل لوحة المحافظات: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function collectAdvancedFilters() {
  return {
    transaction: $("transactionField")?.value.trim() || "",
    propertyType: $("typeField")?.value.trim() || "",
    governorate: $("boardGovernorateFilter")?.value.trim() || "",
    areas: $("areasField")?.value.trim() || "",
    minArea: $("minAreaField")?.value || "",
    maxArea: $("maxAreaField")?.value || "",
    budget: $("budgetField")?.value || "",
    rentBudget: $("rentBudgetField")?.value || "",
    bedrooms: $("bedroomsField")?.value || "",
  };
}

function buildTextFromFilters(filters) {
  const parts = [];
  if (filters.transaction) parts.push(filters.transaction);
  if (filters.propertyType) parts.push(filters.propertyType);
  if (filters.areas) parts.push(`في ${filters.areas}`);
  if (filters.minArea && filters.maxArea && filters.minArea === filters.maxArea) parts.push(`${filters.minArea}م`);
  else {
    if (filters.minArea) parts.push(`من ${filters.minArea}م`);
    if (filters.maxArea) parts.push(`إلى ${filters.maxArea}م`);
  }
  if (filters.budget) parts.push(`ميزانية ${filters.budget}`);
  if (filters.rentBudget) parts.push(`إيجار ${filters.rentBudget}`);
  if (filters.bedrooms) parts.push(`${filters.bedrooms} غرف`);
  return parts.join(" ").trim();
}

async function sendChat() {
  if (state.chatSubmitting) return;
  const input = $("chatInput");
  if (!input) return;
  const filters = collectAdvancedFilters();
  const text = (input.value && input.value.trim()) || buildTextFromFilters(filters);
  if (!text) return;
  state.chatSubmitting = true;
  const platformScope = selectedBoardPlatforms();
  const sourceMode = platformScope.sourceMode;
  const selectedSource = platformScope.selectedSource;
  const selectedSources = platformScope.selectedSources;
  const includeExternal = platformScope.includeExternal;
  const includeLocal = platformScope.includeLocal;
  const scope = platformScope.label;

  addChatMessage('user', `<div class="bubble user">${escapeHtml(text)}<div class="meta">نطاق: ${escapeHtml(scope)} | مصادر خارجية: ${includeExternal ? 'نعم' : 'لا'}</div></div>`);
  input.value = "";
  addChatMessage('assistant', `<div class="bubble assistant">جاري البحث والتقييم... <div class="meta">(${new Date().toLocaleTimeString()})</div></div>`);

  try {
    const payload = { text, mode: state.mode, includeExternal, includeLocal, sourceMode, selectedSource, selectedSources, filters };
    const report = await postJson('/api/analyze', payload);
    state.report = report;

    // استبدال آخر فقاعة مساعد بالملخص
    const win = $("chatWindow");
    if (win) {
      const last = win.querySelector('.chat-message.assistant:last-child');
      if (last) {
        const scopeText = report.searchScope && report.searchScope.note
          ? `<p class="scope-note">${escapeHtml(report.searchScope.note)}</p>`
          : "";
        const detectedAreas = requestedAreas(report).join("، ") || "غير محددة";
        const generatedAt = report.generatedAt || new Date().toLocaleString();
        last.innerHTML = `<div class="bubble assistant">
          <strong>النتيجة:</strong>
          <p class="scope-note">منطقة البحث المكتشفة: ${escapeHtml(detectedAreas)} | تاريخ التحليل: ${escapeHtml(generatedAt)}</p>
          ${extractedFiltersHtml(report.extractedFilters)}
          ${scopeText}
          <p>${formatSummary(summaryLead(report.summary || ''))}</p>
          <div class="chat-results-preview">${report.results && report.results.length ? `<strong>عدد النتائج:</strong> ${report.results.length} — أفضل توصية: ${Math.round(report.results[0].recommendationScore || 0)}/100` : 'لا توجد نتائج.'}</div>
          <div class="meta">${new Date().toLocaleTimeString()}</div>
        </div>`;
      }
    }

    renderReport(report);
    state.chatMessages.push({ role: 'assistant', text: report.summary || '', report });
    state.chatSubmitting = false;
  } catch (err) {
    state.chatSubmitting = false;
    console.error(err);
    addChatMessage('assistant', `<div class="bubble assistant error">تعذر الحصول على النتائج: ${escapeHtml(err.message)}</div>`);
  }
}

// تسمية عربية مفهومة لحالات المصادر بدل الكود الإنجليزي الخام
function sourceStatusLabel(status) {
  if (status === "success") return "نجح";
  if (status === "fallback") return "نجح عبر بديل";
  if (status === "failed") return "فشل";
  if (status === "no_results") return "لا نتائج";
  if (status === "no_data") return "لا بيانات";
  if (status === "page_reachable") return "الصفحة متاحة";
  return status || "";
}

function toneClass(tone) {
  if (tone === "strong") return "strong";
  if (tone === "medium") return "medium";
  return "weak";
}

function renderSourceSummary(statuses) {
  const root = $("sourceSummaryBar");
  if (!root) return;
  const list = statuses || [];
  const entered = list.filter((s) => s.trust && s.trust.scored).length;
  const helpers = list.filter((s) => s.trust && !s.trust.scored && ["page_reachable", "search_links"].includes(s.status)).length;
  const missing = list.filter((s) => s.trust && !s.trust.scored && !["page_reachable", "search_links"].includes(s.status)).length;
  const records = list.reduce((sum, s) => sum + Number(s.records || 0), 0);
  const topNames = list
    .filter((s) => s.trust && s.trust.scored)
    .slice(0, 4)
    .map((s) => s.name)
    .join("، ");
  root.innerHTML = `
    <div class="source-summary-card strong">
      <span>دخل التقييم</span>
      <strong>${entered}</strong>
      <p>${escapeHtml(topNames || "لا يوجد")}</p>
    </div>
    <div class="source-summary-card">
      <span>نتائج قابلة للتحليل</span>
      <strong>${records}</strong>
      <p>إجمالي السجلات الداخلة من المصادر</p>
    </div>
    <div class="source-summary-card medium">
      <span>مصادر مساعدة فقط</span>
      <strong>${helpers}</strong>
      <p>روابط أو صفحات لا تكفي وحدها للتقييم</p>
    </div>
    <div class="source-summary-card weak">
      <span>لم تدخل</span>
      <strong>${missing}</strong>
      <p>لا نتائج أو لا بيانات لهذا الطلب</p>
    </div>
  `;
}

function renderSources(report) {
  const root = $("sourceStatus");
  const statuses = report.sourceStatus || [];
  renderSourceSummary(statuses);
  if (!root) return;
  root.innerHTML = "";
  let connected = 0;
  for (const source of statuses) {
    // «نجح عبر بديل» يعوّض المصدر المتعذر بنتائج فعلية، لذا يُحتسب ضمن المتصل
    if (source.status === "success" || (source.status === "fallback" && source.records > 0)) connected += 1;
    const response = source.responseMs ? ` | ${source.responseMs}ms` : "";
    const available = source.availableCount ? ` | متاح بالموقع: ${source.availableCount}` : "";
    const candidates = source.candidates !== undefined ? ` | مفحوص: ${source.candidates}` : "";
    const url = source.url ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">فتح المصدر المفحوص</a>` : "";
    const trust = source.trust || {};
    const trustLine = trust.label
      ? `<em class="trust-badge ${toneClass(trust.tone)}">${escapeHtml(trust.label)} ${trust.score !== undefined ? `(${trust.score}%)` : ""}</em>`
      : "";
    const item = document.createElement("div");
    item.className = `source-card ${source.status}`;
    item.innerHTML = `
      <strong>${escapeHtml(source.name)}</strong>
      <span>${escapeHtml(sourceStatusLabel(source.status))} | دخل التقييم: ${escapeHtml(source.records)}${escapeHtml(candidates)}${escapeHtml(response)}${escapeHtml(available)}</span>
      ${trustLine}
      <p>${escapeHtml(source.note)}</p>
      ${trust.reason ? `<p class="source-trust-reason">${escapeHtml(trust.reason)}</p>` : ""}
      ${url}
    `;
    root.appendChild(item);
  }
  const connectedEl = $("connectedSources");
  if (connectedEl) connectedEl.textContent = connected || "-";

  const planRoot = $("externalSourcePlan");
  if (planRoot) {
    planRoot.innerHTML = "";
    for (const source of report.externalSourcePlan || []) {
      const item = document.createElement("div");
      const statusText = source.status || "";
      const done = /^منفذ ✓/.test(statusText);
      const partial = /منفذ جزئيًا/.test(statusText);
      item.className = done ? "source-card done" : (partial ? "source-card partial" : "source-card pending");
      item.innerHTML = `
        <strong>${escapeHtml(source.name)}</strong>
        <span>${escapeHtml(source.status)}</span>
        <p>${escapeHtml(source.action)}</p>
      `;
      planRoot.appendChild(item);
    }
  }

  const registryRoot = $("sourceRegistry");
  if (registryRoot) {
    registryRoot.innerHTML = "";
    for (const source of report.sourceRegistry || []) {
      const row = document.createElement("div");
      row.className = `registry-row ${source.status || ""}`;
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(source.name)}</strong>
          <span>${escapeHtml(source.category)} | ${escapeHtml(source.connection)}</span>
        </div>
        <p>${escapeHtml(source.role)}</p>
        <p>${escapeHtml(source.scoringPolicy)}</p>
        <em>${escapeHtml(source.trustLevel)}</em>
      `;
      registryRoot.appendChild(row);
    }
  }

  const linksRoot = $("externalLinks");
  if (linksRoot) {
    linksRoot.innerHTML = "";
    for (const link of report.externalSearchLinks || []) {
      const card = document.createElement("div");
      card.className = "external-link-card";
      card.innerHTML = `
        <strong>${escapeHtml(link.name)}</strong>
        <span>${escapeHtml(link.status || "رابط مراجعة")}</span>
        <p>${escapeHtml(link.evidenceStatus || "")}</p>
        <div>
          <a class="external-link" href="${escapeHtml(link.url || "#")}" target="_blank" rel="noreferrer">بحث مطابق</a>
          ${link.directUrl ? `<a class="external-link secondary" href="${escapeHtml(link.directUrl)}" target="_blank" rel="noreferrer">فتح الموقع</a>` : ""}
        </div>
      `;
      linksRoot.appendChild(card);
    }
  }
}

function renderMethod(report) {
  const method = report.rankingMethod;
  if (!method) return;
  const weights = method.weights || {};
  const el = $("rankingMethod");
  if (!el) return;
  el.innerHTML = `
    ${escapeHtml(method.note)}
    <br>
    <span>مطابقة الطلب ${escapeHtml(weights.matchScore)}</span>
    <span>جاذبية السعر ${escapeHtml(weights.dealScore)}</span>
    <span>الثقة ${escapeHtml(weights.confidence)}</span>
    <span>${escapeHtml(weights.missingDataPenalty)}</span>
  `;
}

function renderTransactionSummary(report) {
  const summary = report.transactionSummary;
  const el = $("transactionSummary");
  if (!el) return;
  if (!summary) {
    el.innerHTML = '<p>لا يوجد تأكيد لطريقة الحساب لهذا البحث.</p>';
    return;
  }
  const bd = summary.breakdown || {};
  const sale = bd.sale || {};
  const rent = bd.rent || {};
  el.innerHTML = `
    <p class="tscope"><strong>نوع العملية المكتشف:</strong> ${escapeHtml(summary.detected || "غير محدد")}</p>
    <p>${escapeHtml(summary.detectedWhen || "")}</p>
    <p><strong>طريقة الحساب المطبقة:</strong> ${escapeHtml(summary.calculation || "")}</p>
    <div class="transaction-badges">
      <span class="pill good">بيع/شراء: ${sale.count ?? 0} نتيجة — ${escapeHtml(sale.method || "")}</span>
      <span class="pill info">إيجار: ${rent.count ?? 0} نتيجة — ${escapeHtml(rent.method || "")}</span>
    </div>
    <p class="scope-note">${escapeHtml(summary.confirmation || "")}</p>
  `;
}

function scoreItem(label, value, type = "") {
  if (value === null || value === undefined || value === "") return "";
  return `<div class="score-item ${type}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function sourceItem(label, source) {
  if (!source) return "";
  const value = source.display ?? source.value ?? "غير متاح";
  return `
    <div class="source-line">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
      <p>${escapeHtml(source.source)}</p>
    </div>
  `;
}

function propertyProfileHtml(profile) {
  if (!profile) return "";
  const chips = [
    ["نوع الأصل", profile.assetClass],
    ["الملكية", profile.tenure],
    ["الاستخدام", profile.usage],
    ["التمويل", profile.financeStatus],
    ["المستندات", profile.legalStatus],
  ].filter(([, value]) => value && value !== "غير مذكور" && value !== "غير محدد");
  const flags = (profile.flags || []).map((flag) => `<span class="pill warn">${escapeHtml(flag)}</span>`).join("");
  return `
    <div class="property-profile">
      ${chips.map(([label, value]) => `<span class="profile-chip"><b>${escapeHtml(label)}</b>${escapeHtml(value)}</span>`).join("")}
      ${flags}
    </div>
  `;
}

function breakdownItem(item) {
  return `
    <div class="breakdown-item">
      <strong>${escapeHtml(item.name)}</strong>
      <span>${escapeHtml(item.points)} نقطة</span>
      <p>${escapeHtml(item.reason || `القيمة ${item.value ?? ""} - الوزن ${item.weight ?? ""}`)}</p>
    </div>
  `;
}

// قصّ النص إلى 3 أسطر مع زر «عرض المزيد/أقل» عند النقر — تفاصيل احترافية بلا ازدحام
function attachClampToggle(el) {
  if (!el || el.dataset.clamped) return;
  el.dataset.clamped = "1";
  // النص القصير لا يحتاج زرًا زائدًا — نقتصر على النصوص الطويلة فعلًا
  if ((el.textContent || "").trim().length <= 140) return;
  el.classList.add("clamp");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "clamp-toggle";
  btn.textContent = "عرض المزيد";
  btn.setAttribute("aria-expanded", "false");
  btn.addEventListener("click", () => {
    const open = el.classList.toggle("clamp-open");
    btn.textContent = open ? "عرض أقل" : "عرض المزيد";
    btn.setAttribute("aria-expanded", String(open));
  });
  el.after(btn);
}

function formatMoney(value) {
  if (!value && value !== 0) return "";
  return `${Number(value).toLocaleString("en-US")} د.ك`;
}

function analysisBadge(method) {
  if (method === "ai") return "تحليل ذكاء اصطناعي";
  if (method === "local") return "تحليل محلي احترافي";
  return "";
}

function signedNumber(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "غير محسوب";
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toLocaleString("en-US")}${suffix}`;
}

function requestedAreas(report) {
  return ((report.request && report.request.areas) || []).filter(Boolean);
}

function sameRequestedArea(report, item) {
  const areas = requestedAreas(report);
  if (!areas.length) return true;
  return areas.includes(item.area || "");
}

function viewsText(item) {
  if (item.views !== null && item.views !== undefined && item.views !== "") {
    return `${Number(item.views).toLocaleString("en-US")} مشاهدة`;
  }
  return "غير متاحة من المصدر";
}

function dateText(value) {
  return value ? String(value) : "غير متاح";
}

function renderSimilarExternal(report) {
  const box = $("similarExternalList");
  const meta = $("similarExternalMeta");
  const note = $("similarExternalNote");
  const data = report.similarExternal || {};
  const areas = requestedAreas(report);
  const rawItems = data.items || [];
  const items = rawItems.filter((item) => sameRequestedArea(report, item));
  if (meta) {
    const sources = (data.sources || []).join("، ") || "لا يوجد مصدر مطابق";
    const areaPart = areas.length ? ` | نفس المنطقة فقط: ${areas.join("، ")}` : "";
    meta.textContent = `${items.length} إعلان | ${sources}${areaPart}`;
  }
  if (note) {
    const dropped = rawItems.length - items.length;
    note.textContent = dropped > 0
      ? `${data.note || ""} تم إخفاء ${dropped} إعلان لأنه ليس من نفس منطقة الطلب.`
      : (data.note || "");
    note.hidden = !note.textContent;
  }
  if (!box) return;
  if (!items.length) {
    box.innerHTML = `
      <div class="empty compact-empty">
        لا توجد مقارنة خارجية رقمية مطابقة لنفس المنطقة الآن. افتح روابط المصادر بالأسفل للمراجعة اليدوية، ولا يتم احتساب أي موقع لا يعطينا سعرًا/مساحة/رابط إعلان واضح.
      </div>
    `;
    return;
  }
  box.innerHTML = items.map((item) => {
    const price = item.priceText || formatMoney(item.price) || "غير معلن";
    const space = item.space ? `${item.space} م²` : "مساحة غير مذكورة";
    const priceDelta = signedNumber(item.priceDelta, " د.ك");
    const spaceDelta = signedNumber(item.spaceDelta, " م²");
    const published = dateText(item.publishedDate);
    const views = viewsText(item);
    const reasons = (item.reasons || []).slice(0, 5).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
    const link = item.originalUrl
      ? `<a href="${escapeHtml(item.originalUrl)}" target="_blank" rel="noreferrer">فتح المصدر</a>`
      : "";
    return `
      <article class="similar-external-card">
        <div>
          <span class="source-pill">${escapeHtml(item.source || "مصدر خارجي")}</span>
          <h3>${escapeHtml(item.code || "إعلان خارجي")} - ${escapeHtml(item.area || "")}</h3>
          <p>${escapeHtml(item.summary || "")}</p>
        </div>
        <div class="similar-metrics">
          <span><b>السعر</b>${escapeHtml(price)}</span>
          <span><b>المساحة</b>${escapeHtml(space)}</span>
          <span><b>تاريخ الإعلان</b>${escapeHtml(published)}</span>
          <span><b>المشاهدات</b>${escapeHtml(views)}</span>
          <span><b>فرق السعر</b>${escapeHtml(priceDelta)}</span>
          <span><b>فرق المساحة</b>${escapeHtml(spaceDelta)}</span>
        </div>
        <details>
          <summary>سبب التشابه والدليل</summary>
          <ul>${reasons}</ul>
        </details>
        ${oppClientChips(item)}
        ${link}
      </article>
    `;
  }).join("");
}

function renderProfitOpportunities(report) {
  const box = $("profitList");
  const meta = $("profitMeta");
  const note = $("profitNote");
  const data = report.profitOpportunities || {};
  const items = data.items || [];
  if (meta) {
    const total = data.totalPotentialProfitKwd != null ? `${Number(data.totalPotentialProfitKwd).toLocaleString("en-US")} د.ك` : "0 د.ك";
    meta.textContent = `${data.count || 0} فرصة | إجمالي مكسب محتمل ${total}`;
  }
  if (note) {
    note.textContent = data.note || "";
    note.hidden = !data.note;
  }
  if (!box) return;
  if (!items.length) {
    box.innerHTML = '<div class="empty compact-empty">لا توجد فرصة مكسب مؤكدة لنفس المنطقة الآن.</div>';
    return;
  }
  box.innerHTML = items.map((item) => {
    const profit = `${Number(item.potentialProfitKwd || 0).toLocaleString("en-US")} د.ك`;
    const listingPrice = item.listingPrice ? `${Number(item.listingPrice).toLocaleString("en-US")} د.ك` : (item.listingPriceText || "غير معلن");
    const budget = item.clientBudget ? `${Number(item.clientBudget).toLocaleString("en-US")} د.ك` : "غير محددة";
    const link = item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">فتح الإعلان</a>` : "";
    return `
      <article class="profit-card">
        <div>
          <span class="source-pill">${escapeHtml(item.listingSource || "مصدر")}</span>
          <h3>${escapeHtml(item.listingCode || "إعلان")} - ${escapeHtml(item.area || "")}</h3>
          <p>${escapeHtml(item.propertyType || "")} | عميل من ${escapeHtml(item.clientSource || "غير محدد")} | تطابق ${Math.round(item.matchScore || 0)}/100</p>
        </div>
        <strong class="profit-value">${escapeHtml(profit)}</strong>
        <div class="similar-metrics">
          <span><b>سعر الإعلان</b>${escapeHtml(listingPrice)}</span>
          <span><b>ميزانية العميل</b>${escapeHtml(budget)}</span>
        </div>
        <p>${escapeHtml(item.reason || "")}</p>
        <code dir="ltr">${escapeHtml(item.phones || "")}</code>
        ${link}
      </article>
    `;
  }).join("");
}

function renderReport(report) {
  const summaryEl = $("summaryText");
  const summary = report.summary || "";
  if (summaryEl) summaryEl.innerHTML = formatSummary(summaryLead(summary) || summary);
  const fullSummaryBox = $("fullSummaryBox");
  const fullSummaryText = $("fullSummaryText");
  if (fullSummaryBox && fullSummaryText) {
    const showFull = String(summary).trim().length > String(summaryLead(summary) || "").trim().length + 20;
    fullSummaryBox.hidden = !showFull;
    fullSummaryText.innerHTML = showFull ? formatSummary(summary) : "";
  }
  const scopeEl = $("searchScopeNote");
  if (scopeEl) {
    scopeEl.innerHTML = `${escapeHtml((report.searchScope && report.searchScope.note) || "")}${extractedFiltersHtml(report.extractedFilters)}`;
    scopeEl.hidden = !report.searchScope;
  }
  const badge = $("analysisBadge");
  if (badge) {
    badge.textContent = analysisBadge(report.analysisMethod);
    badge.classList.toggle("ai", report.analysisMethod === "ai");
    badge.classList.toggle("local", report.analysisMethod === "local");
  }
  renderSources(report);
  renderProfitOpportunities(report);
  renderSimilarExternal(report);
  renderMethod(report);    const results = report.results || [];
  const exactResults = results.filter((item) => !(item.warnings || []).some((warning) => String(warning).includes("خارج المنطقة المطلوبة")));
  const expandedResults = results.filter((item) => (item.warnings || []).some((warning) => String(warning).includes("خارج المنطقة المطلوبة")));
  const resultCountEl = $("resultCount");
  if (resultCountEl) {
    resultCountEl.textContent = expandedResults.length
      ? `${exactResults.length} مطابق + ${expandedResults.length} توسعة`
      : results.length;
  }
  const topResult = exactResults[0] || results[0];
  const topScoreEl = $("topScore");
  if (topScoreEl) topScoreEl.textContent = topResult ? `${Math.round(topResult.recommendationScore)} / 100` : "-";
  const persistenceEl = $("persistenceStatus");
  if (persistenceEl) persistenceEl.textContent = persistenceLabel(report.persistence);
  renderTransactionSummary(report);

  const root = $("results");
  if (!root) return;
  root.innerHTML = "";
  if (!results.length) {
    root.innerHTML = '<div class="empty">لا توجد نتائج كافية حسب الفلاتر الحالية.</div>';
    return;
  }

  const template = $("resultTemplate");
  if (!template) return;

  let renderedIndex = 0;
  const renderItem = (item) => {
    const node = template.content.cloneNode(true);
    renderedIndex += 1;
    node.querySelector(".rank-cell").textContent = renderedIndex;
    node.querySelector("h3").textContent = `${item.code} - ${item.area || "منطقة غير محددة"}`;
    const sourceLabel = item.fallbackFor
      ? `${item.source || "مصدر غير محدد"} (عبر بديل ${item.fallbackFor})`
      : (item.source || "مصدر غير محدد");
    node.querySelector(".meta").textContent = `${sourceLabel} | ${item.governorate || ""} | ${item.transaction || ""} | ${item.propertyType || item.detailClass || ""} | ${item.listingType || "غير محدد"}`;
    const outsideBadge = node.querySelector(".outside-area");
    if (outsideBadge) {
      const labels = (item.warnings || []).filter((w) => String(w).includes("خارج المنطقة المطلوبة"));
      outsideBadge.textContent = labels[0] || "";
      outsideBadge.hidden = !labels.length;
    }
    node.querySelector(".verdict-label").textContent = item.valuationLabel || "بدون حكم";
    node.querySelector(".recommendation").textContent = `توصية ${Math.round(item.recommendationScore || 0)} / 100`;
    const isRental = !!item.rental;
    node.querySelector(".score-grid").innerHTML = isRental ? [
      scoreItem("الإيجار الشهري", item.priceText || item.price),
      scoreItem("الإيجار السنوي", item.annualRent ? `${Number(item.annualRent).toLocaleString("en-US")} د.ك` : "—"),
      scoreItem("المساحة", item.space ? `${item.space} م²` : "غير مذكورة"),
      scoreItem("تاريخ الإعلان", dateText(item.publishedDate)),
      scoreItem("المشاهدات", viewsText(item)),
      scoreItem("وسيط إيجارات المنطقة", item.marketMedian ? `${Number(item.marketMedian).toLocaleString("en-US")} د.ك/شهر` : "غير كافية"),
      scoreItem("مطابقة الطلب", `${Math.round(item.matchScore || 0)} / 100`),
    ].join("") : [
      scoreItem("السعر", item.priceText || item.price),
      scoreItem("المساحة", item.space ? `${item.space} م²` : "غير مذكورة"),
      scoreItem("تاريخ الإعلان", dateText(item.publishedDate)),
      scoreItem("المشاهدات", viewsText(item)),
      scoreItem("وسيط المقارنات", formatMoney(item.marketMedian)),
      scoreItem("نسبة السعر للوسيط", item.priceRatio ? `${Math.round(item.priceRatio * 100)}%` : "غير كافية"),
      scoreItem("مطابقة الطلب", `${Math.round(item.matchScore || 0)} / 100`),
    ].join("");
    const quality = item.dataQuality || {};
    const trust = item.sourceTrust || {};
    const qualityEl = node.querySelector(".data-quality");
    if (qualityEl) {
      qualityEl.className = `data-quality insight-chip ${toneClass(quality.tone)}`;
      qualityEl.textContent = quality.label ? `جودة البيانات: ${quality.label} (${Math.round(quality.score || 0)}%)` : "";
      qualityEl.title = (quality.reasons || []).join(" | ");
    }
    const trustEl = node.querySelector(".source-trust");
    if (trustEl) {
      trustEl.className = `source-trust insight-chip ${toneClass(trust.tone)}`;
      trustEl.textContent = trust.label ? `ثقة المصدر: ${trust.label} (${Math.round(trust.score || 0)}%)` : "";
      trustEl.title = trust.reason || "";
    }
    const insights = node.querySelector(".result-insights");
    if (insights) insights.insertAdjacentHTML("afterend", propertyProfileHtml(item.propertyProfile));
    const decisionEl = node.querySelector(".decision-line");
    if (decisionEl) decisionEl.textContent = item.decisionLine || "";
    // قصّ النصوص الطويلة مع زر «عرض المزيد» عند النقر — لا كلام مكرر ظاهر بلا فائدة
    const reasonEl = node.querySelector(".valuation-reason");
    reasonEl.textContent = item.valuationReason || "لا يوجد سبب تقييم كاف.";
    attachClampToggle(reasonEl);
    const descEl = node.querySelector(".description");
    descEl.textContent = item.summary || item.features || "";
    if (descEl.textContent) attachClampToggle(descEl);

    const financingBlock = node.querySelector(".financing-info");
    if (isRental) {
      financingBlock.innerHTML = "";
    } else if (item.financing && item.financing.monthly_payment) {
      financingBlock.innerHTML = `
        <h4 style="margin-top:15px; margin-bottom:10px;">معلومات التمويل العقاري المتوقعة</h4>
        <div class="score-grid">
          ${scoreItem("الدفعة المقدمة", formatMoney(item.financing.down_payment))}
          ${scoreItem("القسط الشهري", formatMoney(item.financing.monthly_payment), "monthly")}
          ${scoreItem("الفائدة", item.financing.interest_rate_percent ? `${item.financing.interest_rate_percent}%` : "")}
          ${scoreItem("مدة القرض", item.financing.years ? `${item.financing.years} سنة` : "")}
        </div>
      `;
    } else {
      financingBlock.innerHTML = "";
    }

    node.querySelector(".reasons").innerHTML = (item.reasons || [])
      .map((reason) => `<span class="pill good">${escapeHtml(reason)}</span>`)
      .join("");
    node.querySelector(".warnings").innerHTML = (item.warnings || [])
      .map((warning) => `<span class="pill warn">${escapeHtml(warning)}</span>`)
      .join("");
    // كل مقارنة = صندوق دليل مستقل باسم مصدرها وتفاصيل إعلانها ورابط فتحه
    const comps = node.querySelector(".comparables");
    comps.innerHTML = (item.comparables || []).map(compEvidenceHtml).join("") || '<span class="comp">لا توجد مقارنات كافية</span>';

    const sources = item.numberSources || {};
    node.querySelector(".number-sources").innerHTML = isRental ? [
      sourceItem("الإيجار الشهري", sources.price),
      sourceItem("الإيجار السنوي", sources.annualRent),
      sourceItem("المساحة", sources.space),
      sourceItem("إيجار المتر (شهريًا)", sources.pricePerSqm),
      sourceItem("وسيط إيجارات المنطقة", sources.marketMedian),
      sourceItem("وسيط إيجار المتر", sources.medianPerSqm),
      sourceItem("قيمة العقار التقديرية", sources.officialValue),
      sourceItem("العائد الإيجاري السنوي", sources.rentalYield),
      sourceItem("التصنيف القانوني/التمويلي", sources.propertyProfile),
      sourceItem("نسبة الإيجار للوسيط", sources.priceRatio),
      sourceItem("عدد المقارنات الداخلة", sources.comparablesCount),
      sourceItem("الثقة", sources.confidence),
    ].join("") : [
      sourceItem("السعر المطلوب", sources.price),
      sourceItem("المساحة", sources.space),
      sourceItem("سعر المتر المطلوب", sources.pricePerSqm),
      sourceItem("وسيط أسعار المقارنات", sources.marketMedian),
      sourceItem("وسيط سعر المتر", sources.medianPerSqm),
      sourceItem("التقييم الرسمي للمنطقة", sources.officialValue),
      sourceItem("التصنيف القانوني/التمويلي", sources.propertyProfile),
      sourceItem("نسبة السعر للوسيط", sources.priceRatio),
      sourceItem("عدد المقارنات الداخلة", sources.comparablesCount),
      sourceItem("الثقة", sources.confidence),
    ].join("");
    node.querySelector(".match-breakdown").innerHTML = (item.matchBreakdown || [])
      .map(breakdownItem)
      .join("");
    node.querySelector(".recommendation-breakdown").innerHTML = (item.recommendationBreakdown || [])
      .map((row) => `
        <div class="breakdown-item">
          <strong>${escapeHtml(row.name)}</strong>
          <span>${escapeHtml(row.points)} نقطة</span>
          <p>القيمة: ${escapeHtml(row.value)} | الوزن: ${escapeHtml(row.weight)}</p>
        </div>
      `)
      .join("");

    // العملاء المحتملون لنتيجة بيعية: يُعرضون في بطاقة التحليل (من ملف العملاء + Supabase)
    const clientsBlock = node.querySelector(".result-clients");
    if (clientsBlock) {
      const chips = oppClientChips(item);
      clientsBlock.innerHTML = chips ? `<h4>عملاء محتملون للشراء</h4>${chips}` : "";
    }

    const link = node.querySelector(".open-link");
    link.href = item.originalUrl || "#";
    link.hidden = !item.originalUrl;
    // زر «نسخ ملخص» في نتائج الشات: نفس الرسالة المولّدة بمصادر الأدلة + زر إرسال واتساب مباشر
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "opp-copy-btn chat-copy-btn";
    copyBtn.textContent = "نسخ ملخص";
    copyBtn.addEventListener("click", () => {
      copyText(oppWhatsAppSummary(item), copyBtn);
      trackOutreach({ action: "copy", channel: "chat_result", opportunityCode: item.code || "" });
    });
    link.after(copyBtn);
    const shareLink = document.createElement("a");
    shareLink.className = "wa-share chat-wa-share";
    shareLink.href = waShareLink(oppWhatsAppSummary(item));
    shareLink.target = "_blank";
    shareLink.rel = "noreferrer";
    shareLink.textContent = "إرسال واتساب";
    shareLink.addEventListener("click", () => trackOutreach({ action: "send", channel: "chat_result", opportunityCode: item.code || "" }));
    copyBtn.after(shareLink);
    root.appendChild(node);
  };

  exactResults.forEach(renderItem);
  if (expandedResults.length) {
    const separator = document.createElement("div");
    separator.className = "expanded-results-note";
    separator.innerHTML = `
      <strong>نتائج توسعة وليست نفس المنطقة</strong>
      <span>ظهرت لأن عدد إعلانات نفس المنطقة قليل. استخدمها كمقارنة احتياطية فقط، ولا تدخل في فرص المكسب المؤكدة إلا إذا تطابقت المنطقة والعميل.</span>
    `;
    root.appendChild(separator);
    expandedResults.forEach(renderItem);
  }
}

function downloadReport() {
  if (!state.report) return;
  const blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `alforaij-research-report-${Date.now()}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

async function downloadPdfReport(btnId) {
  if (!state.report) return;
  const btn = btnId ? $(btnId) : null;
  const original = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "جاري توليد PDF...";
  }
  try {
    const response = await fetch(apiUrl("/api/report-pdf"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report: state.report }),
    });
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `alforaij-report-${Date.now()}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error(err);
    alert("تعذر توليد تقرير PDF: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = original;
    }
  }
}

// ---------------------------------------------------------------------------
// أفضل الفرص والتوقعات
// ---------------------------------------------------------------------------
const oppState = {
  data: null,
  tier: "best",
  source: "", // "" الكل | external مواقع خارجية | local الفريج فقط
  kind: "", // "" كل الأنواع | مباشر | مكتب
  gov: "",
  area: "",
  type: "",
  minPrice: null,
  maxPrice: null,
  minScore: null,
};

const OPP_TIER_LABELS = { best: "الأفضل", daily: "يومية", weekly: "أسبوعية", monthly: "شهرية", yearly: "سنوية" };

function oppMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  return `${Number(value).toLocaleString("en-US")} د.ك`;
}

function fillOppSelect(id, values) {
  const el = $(id);
  if (!el) return;
  const current = el.value;
  const seen = new Set();
  let options = '<option value="">الكل</option>';
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options += `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`;
  }
  el.innerHTML = options;
  el.value = current;
}

function collectOppFilters() {
  const gov = $("oppGovFilter")?.value || "";
  const area = $("oppAreaFilter")?.value || "";
  const type = $("oppTypeFilter")?.value || "";
  const transaction = $("oppTransactionFilter")?.value || "";
  const minPrice = parseFloat($("oppMinPrice")?.value) || null;
  const maxPrice = parseFloat($("oppMaxPrice")?.value) || null;
  const minScore = parseFloat($("oppMinScore")?.value) || null;
  Object.assign(oppState, { gov, area, type, transaction, minPrice, maxPrice, minScore });
}

// «الفريج فقط» = بيانات الشركة المحلية؛ «مواقع خارجية» = كل المسح الحي (OpenSooq/Mourjan/Q8Aqar/…)
function oppItemIsLocal(item) {
  return (item.source || "") === "الفريج";
}

function oppFilteredItems(items) {
  return (items || []).filter((item) => {
    if (oppState.source === "external" && oppItemIsLocal(item)) return false;
    if (oppState.source === "local" && !oppItemIsLocal(item)) return false;
    if (oppState.kind && (item.listingType || "غير محدد") !== oppState.kind) return false;
    if (oppState.gov && item.governorate !== oppState.gov) return false;
    if (oppState.area && item.area !== oppState.area) return false;
    if (oppState.type && (item.propertyType || "") !== oppState.type) return false;
    if (oppState.transaction === "بيع" && item.rental) return false;
    if (oppState.transaction === "إيجار" && !item.rental) return false;
    if (oppState.minPrice != null && (item.price ?? 0) < oppState.minPrice) return false;
    if (oppState.maxPrice != null && (item.price ?? Infinity) > oppState.maxPrice) return false;
    if (oppState.minScore != null && (item.score ?? 0) < oppState.minScore) return false;
    return true;
  });
}

// عدّادات فلتر المصدر: «الكل / مواقع خارجية / الفريج فقط» + عدّادات مباشر/مكتب لكل فئة
function renderOppSourceCounts(items) {
  const list = items || [];
  const external = list.filter((item) => !oppItemIsLocal(item)).length;
  const direct = list.filter((item) => (item.listingType || "غير محدد") === "مباشر").length;
  const office = list.filter((item) => (item.listingType || "غير محدد") === "مكتب").length;
  const setCount = (id, value) => {
    const el = $(id);
    if (el) el.textContent = value;
  };
  setCount("oppCountAll", list.length);
  setCount("oppCountExternal", external);
  setCount("oppCountLocal", list.length - external);
  setCount("oppCountDirect", direct);
  setCount("oppCountOffice", office);
  document.querySelectorAll(".opp-source-chip").forEach((chip) => {
    if ("kind" in chip.dataset) {
      chip.classList.toggle("active", (chip.dataset.kind || "") === (oppState.kind || ""));
    } else {
      chip.classList.toggle("active", (chip.dataset.source || "") === (oppState.source || ""));
    }
  });
}

function setOppSourceRowVisible(visible) {
  const row = $("oppSourceFilterRow");
  if (row) row.hidden = !visible;
  const kindRow = $("oppKindFilterRow");
  if (kindRow) kindRow.hidden = !visible;
}

function oppClientChips(item) {
  if (!item.clients || !item.clients.length) return "";
  return `<div class="opp-clients">
    <strong>عملاء محتملون (${item.clients.length}):</strong>
    ${item.clients.map((client) => `
      <div class="opp-client">
        <span>${escapeHtml(client.area || "")} ${escapeHtml(client.type || "")} — تطابق ${client.matchScore}/100 (${escapeHtml((client.reasons || []).join("، "))})</span>
        <span class="client-profit">مصدر العميل: ${escapeHtml(client.source || "غير محدد")} | ميزانية العميل: ${client.clientBudget ? `${Number(client.clientBudget).toLocaleString("en-US")} د.ك` : "غير محددة"} | المكسب التقديري: ${client.potentialProfitKwd != null ? `${Number(client.potentialProfitKwd).toLocaleString("en-US")} د.ك` : "غير محسوب"}</span>
        ${client.profitReason ? `<p class="client-msg">${escapeHtml(client.profitReason)}</p>` : ""}
        <code dir="ltr">${escapeHtml(client.phones || "")}</code>
        ${client.message ? `<p class="client-msg">${escapeHtml(client.message)}</p>` : ""}
      </div>`).join("")}
  </div>`;
}

function oppSourceKindLabel(item) {
  if (item.officialSourceKind === "official_transactions") return "صفقات رسمية مسجلة";
  if (item.officialSourceKind === "official") return "معيار رسمي";
  if (item.officialSourceKind === "derived") return "مشتق من السوق";
  return "غير متوفر";
}

// صندوق دليل موحد لكل مقارنة/دليل: اسم المصدر + تفاصيل الإعلان + رابط فتحه (يُستخدم في النتائج والفرص)
function compEvidenceHtml(comp) {
  const price = comp.priceText || (comp.price ? `${Number(comp.price).toLocaleString("en-US")} د.ك` : "غير معلن");
  const source = comp.source || "مصدر غير محدد";
  const space = comp.space ? ` | ${escapeHtml(String(comp.space))} م²` : "";
  const date = comp.date ? ` | ${escapeHtml(String(comp.date))}` : "";
  const link = comp.url
    ? `<a class="comp-open" href="${escapeHtml(comp.url)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي ↗</a>`
    : "";
  return `<div class="comp-evidence">
    <span class="comp-source">دليل من ${escapeHtml(source)}</span>
    <div class="comp-body">
      <strong>${escapeHtml(comp.code)}</strong>
      <span>${escapeHtml(comp.area || "")}${space}${date}</span>
      <span class="comp-price">${escapeHtml(price)}</span>
    </div>
    ${link}
  </div>`;
}

function oppEvidenceBox(item) {
  const evidence = item.evidence || [];
  if (!evidence.length) return "";
  return `<details class="evidence" open>
    <summary>الأدلة والمقارنات (${evidence.length})</summary>
    ${evidence.map(compEvidenceHtml).join("")}
  </details>`;
}

// رسالة واتساب جاهزة لتسويق الفرصة للعميل: بيانات الفرصة + مصادر الأدلة بروابط إعلاناتها.
// تخدم شكلين: بطاقة الفرص (evidence/score) ونتيجة تحليل الشات (comparables/recommendationScore).
function oppWhatsAppSummary(item) {
  const isRental = !!item.rental;
  const price = item.priceText || oppMoney(item.price);
  const lines = [
    `🏠 فرصة: ${item.propertyType || "عقار"} ${item.transaction || ""}`,
    `📍 المنطقة: ${item.area || "غير محددة"}${item.governorate ? ` (${item.governorate})` : ""}`,
    isRental ? `💰 الإيجار الشهري: ${price}` : `💰 السعر: ${price}`,
  ];
  if (item.space) lines.push(`📐 المساحة: ${item.space} م²`);
  if (!isRental && item.pricePerSqm) lines.push(`💵 سعر المتر: ${item.pricePerSqm} د.ك/م²`);
  if (item.valuationLabel) {
    const official = item.officialValue ? ` (قيمة مقدرة ${oppMoney(item.officialValue)})` : "";
    lines.push(`📊 التقييم: ${item.valuationLabel}${official}`);
  }
  if (item.score != null || item.recommendationScore != null) {
    const score = item.score != null ? item.score : Math.round(item.recommendationScore);
    lines.push(`⭐ درجة الفرصة: ${score}/100`);
  }
  const evidence = (item.evidence || item.comparables || []).filter((e) => e.source || e.url);
  if (evidence.length) {
    lines.push(`\n📎 مصادر الأدلة (${evidence.length}):`);
    evidence.forEach((e, i) => {
      const detail = [e.source, e.code ? `إعلان ${e.code}` : "", e.priceText ? `(${e.priceText})` : ""].filter(Boolean).join(" — ");
      lines.push(`${i + 1}. ${detail}${e.url ? `\n   🔗 ${e.url}` : ""}`);
    });
  } else if (item.source) {
    lines.push(`\n📎 المصدر: ${item.source}${item.url ? `\n🔗 ${item.url}` : ""}`);
  }
  lines.push("\nهل ترغب بمشاهدة التفاصيل أو حجز موعد معاينة؟");
  return lines.join("\n");
}

// رابط واتساب عام (بدون رقم): يفتح محرر واتساب والرسالة جاهزة للاختيار/الإرسال
function waShareLink(message) {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}

// تتبع نقرات التسويق (نسخ/إرسال فرصة أو عميل) في Supabase — بلا انتظار وبلا كسر أي شيء عند الفشل
function trackOutreach(click) {
  try {
    fetch(apiUrl("/api/outreach-click"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(click),
    }).catch(() => {});
  } catch { /* ignore */ }
}

// روابط إرسال شخصية لكل عميل مطابق: رسالة مخصصة بمنطقته/نوعه وميزانيته + الفرصة كاملة بأدلتها
function oppClientSendLinks(item) {
  const base = oppWhatsAppSummary(item);
  const clients = (item.clients || []).filter((c) => c.phones);
  if (!clients.length) return "";
  const links = clients.map((client, i) => {
    const label = [client.area, client.type].filter(Boolean).join(" - ") || `العميل ${i + 1}`;
    const budget = client.price ? ` (ميزانية ${client.price} د.ك)` : "";
    const personalized = `السلام عليكم، لدي فرصة تناسب طلبكم: ${label}${budget}\n\n${base}`;
    const firstPhone = String(client.phones).split(/[|،,]+/)[0] || "";
    const link = waLink(firstPhone);
    return `<a class="wa-client" href="${escapeHtml(link)}?text=${encodeURIComponent(personalized)}" target="_blank" rel="noreferrer">📲 إرسال لـ ${escapeHtml(label)}</a>`;
  }).join("");
  return `<div class="opp-client-send">${links}</div>`;
}

function oppCard(item, index) {
  const price = item.priceText || oppMoney(item.price);
  const days = item.daysAgo != null ? `${item.daysAgo} يوم` : "—";
  const isRental = !!item.rental;
  const grid = isRental ? [
    scoreItem("الإيجار الشهري", price),
    scoreItem("الإيجار السنوي", item.annualRent ? `${Number(item.annualRent).toLocaleString("en-US")} د.ك` : "—"),
    scoreItem("المساحة", item.space ? `${item.space} م²` : "—"),
    scoreItem("إيجار المتر (شهريًا)", item.rentPerSqm ? `${item.rentPerSqm} د.ك/م²/شهر` : "—"),
    scoreItem("وسيط إيجارات المنطقة", item.medianRent ? `${Number(item.medianRent).toLocaleString("en-US")} د.ك/شهر` : "—"),
    scoreItem("العائد الإيجاري السنوي", item.rentalYieldPercent != null ? `${item.rentalYieldPercent}%` : "—", "confidence"),
    scoreItem("قيمة العقار التقديرية", oppMoney(item.capitalValue)),
    scoreItem("مقارنات", item.comparablesCount),
    scoreItem("الثقة", `${Math.round((item.confidence || 0) * 100)}%`, "confidence"),
    scoreItem("جاذبية الإيجار", `${Math.round(item.dealScore || 0)}/100`),
  ] : [
    scoreItem("السعر", price),
    scoreItem("المساحة", item.space ? `${item.space} م²` : "—"),
    scoreItem("سعر المتر", item.pricePerSqm ? `${item.pricePerSqm} د.ك/م²` : "—"),
    scoreItem("وسيط المقارنات", oppMoney(item.marketMedian)),
    scoreItem("التقييم", oppMoney(item.officialValue)),
    scoreItem("أساس التقييم", oppSourceKindLabel(item)),
    scoreItem("مقارنات", item.comparablesCount),
    scoreItem("الثقة", `${Math.round((item.confidence || 0) * 100)}%`, "confidence"),
    scoreItem("جاذبية السعر", `${Math.round(item.dealScore || 0)}/100`),
  ];
  const badges = [
    item.bestTier ? `<span class="opp-badge opp-badge-tier">${escapeHtml(OPP_TIER_LABELS[item.bestTier] || item.bestTier)}</span>` : "",
    item.listingType && item.listingType !== "غير محدد" ? `<span class="opp-badge opp-badge-kind kind-${escapeHtml(item.listingType)}">${escapeHtml(item.listingType)}</span>` : "",
  ].join("");
  return `<article class="result-card opp-card">
    <div class="rank-cell opp-rank">${index + 1}</div>
    <div class="result-body">
      <div class="result-head">
        <div>
          <div class="opp-badges">${badges}</div>
          <h3>${escapeHtml(item.code)} — ${escapeHtml(item.area || "غير محددة")}</h3>
          <p class="meta">${escapeHtml(item.source || "")} | ${escapeHtml(item.governorate || "")} | ${escapeHtml(item.transaction || "")} | ${escapeHtml(item.propertyType || "")} | نُشر منذ ${escapeHtml(days)}</p>
        </div>
        <div class="verdict opp-verdict">
          <span class="verdict-label">فرصة ${item.score}/100</span>
          <strong class="recommendation">${escapeHtml(item.valuationLabel || "")}</strong>
        </div>
      </div>
      <div class="score-grid">${grid.join("")}</div>
      <p class="valuation-reason opp-reason">${escapeHtml(item.valuationReason || "")}</p>
      ${oppEvidenceBox(item)}
      ${oppClientChips(item)}
      <div class="opp-actions">
        ${item.url ? `<a class="open-link" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي</a>` : ""}
        <button class="opp-copy-btn" type="button">نسخ ملخص الفرصة</button>
        <a class="wa-share" href="${waShareLink(oppWhatsAppSummary(item))}" target="_blank" rel="noreferrer">إرسال واتساب</a>
      </div>
      ${oppClientSendLinks(item)}
    </div>
  </article>`;
}

function oppForecastCard(item, index) {
  const directionClass = item.direction === "صاعد" ? "up" : item.direction === "هابط" ? "down" : "flat";
  const change = item.changePercent != null ? ` (${item.changePercent > 0 ? "+" : ""}${item.changePercent}%)` : "";
  return `<article class="result-card opp-card forecast-card">
    <div class="rank-cell opp-rank forecast-rank">${index + 1}</div>
    <div class="result-body">
      <div class="result-head">
        <div>
          <h3>${escapeHtml(item.area)}</h3>
          <p class="meta">توقعات سعر المتر — ${item.sampleCount} عينة ${escapeHtml(item.sourceKind === "official" ? "(معيار رسمي)" : "(مشتق من السوق)")}</p>
        </div>
        <div class="verdict opp-verdict">
          <span class="verdict-label opp-direction ${directionClass}">${escapeHtml(item.direction)}${escapeHtml(change)}</span>
          <strong class="recommendation">${item.expectedPricePerSqm ? `${item.expectedPricePerSqm} د.ك/م²` : "—"}</strong>
        </div>
      </div>
      <div class="score-grid">
        ${scoreItem("سعر المتر المتوقع", item.expectedPricePerSqm ? `${item.expectedPricePerSqm} د.ك/م²` : "—")}
        ${scoreItem("وسيط حديث (30 يوم)", item.recentMedian ? `${item.recentMedian} د.ك/م²` : "—")}
        ${scoreItem("وسيط سابق", item.olderMedian ? `${item.olderMedian} د.ك/م²` : "—")}
        ${scoreItem("معيار رسمي", item.officialRate ? `${item.officialRate} د.ك/م²` : "غير متوفر")}
        ${scoreItem("قيمة 400 م² تقريبًا", oppMoney(item.expectedPricePerSqm ? item.expectedPricePerSqm * 400 : null))}
      </div>
    </div>
  </article>`;
}

// ---------------------------------------------------------------------------
// العملاء المحتملون + تنبيهات واتساب + الأداء الزمني
// ---------------------------------------------------------------------------
function waLink(phone) {
  const digits = String(phone || "").replace(/\D/g, "");
  if (!digits) return "";
  if (digits.startsWith("01") && digits.length === 11) return `https://wa.me/20${digits.slice(1)}`;
  if (!digits.startsWith("965") && digits.length <= 10) return `https://wa.me/965${digits.replace(/^0+/, "")}`;
  return `https://wa.me/${digits}`;
}

function copyText(text, btn) {
  const done = () => {
    const old = btn.textContent;
    btn.textContent = "تم النسخ ✓";
    setTimeout(() => { btn.textContent = old; }, 1600);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}

function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); done(); } catch { /* ignore */ }
  ta.remove();
}

function oppAlertCard(alert, index) {
  const badge = alert.change === "new" ? "فرصة جديدة" : "انخفاض سعر";
  const badgeClass = alert.change === "new" ? "pill good" : "pill warn";
  const links = (alert.waLinks || []).map((link) =>
    `<a class="wa-open" href="${escapeHtml(link)}" target="_blank" rel="noreferrer">فتح واتساب</a>`
  ).join(" ");
  return `<article class="result-card opp-card alert-card">
    <div class="rank-cell opp-rank">${index + 1}</div>
    <div class="result-body">
      <div class="result-head">
        <div>
          <h3>${escapeHtml(alert.code)} — ${escapeHtml(alert.area || "غير محددة")}</h3>
          <p class="meta">${escapeHtml(alert.clientArea || "")} ${escapeHtml(alert.clientType || "")} | تطابق ${alert.matchScore}/100</p>
        </div>
        <div class="verdict opp-verdict">
          <span class="verdict-label ${badgeClass}">${badge}</span>
          <strong class="recommendation">${escapeHtml(alert.priceText || "")}${alert.oldPrice ? ` <small class="old-price">(كان ${Number(alert.oldPrice).toLocaleString("en-US")} د.ك)</small>` : ""}</strong>
        </div>
      </div>
      <p class="client-msg">${escapeHtml(alert.message || "")}</p>
      <div class="alert-actions">
        <span class="alert-phones">${(alert.phones || []).map((p) => `<code dir="ltr">${escapeHtml(p)}</code>`).join(" ")}</span>
        ${links}
        <button class="copy-btn" data-copy="alert-${index}">نسخ الرسالة</button>
        <textarea id="alert-${index}" hidden>${escapeHtml(alert.message || "")}</textarea>
      </div>
    </div>
  </article>`;
}

function renderClientsTab(root) {
  const clients = oppState.clients || [];
  const rows = clients.map((client) => {
    const firstWa = (client.waLinks && client.waLinks[0]) || waLink((client.phones || "").split("|")[0] || "");
    return `
    <div class="client-row">
      <strong>${escapeHtml(client.code || "-")}</strong>
      <span>${escapeHtml(client.area || "")} ${escapeHtml(client.type || "")}</span>
      <span>${escapeHtml(client.price || "")}</span>
      <code dir="ltr">${escapeHtml(client.phones || "")}</code>
      <a class="wa-open" href="${escapeHtml(firstWa)}" target="_blank" rel="noreferrer">واتساب</a>
    </div>`;
  }).join("");
  root.innerHTML = `
    <form id="clientForm" class="client-form">
      <h3>إضافة عميل محتمل جديد</h3>
      <div class="fields">
        <label>رقم الهاتف (مطلوب)<input id="clientPhone" type="text" placeholder="01064955051" required></label>
        <label>المنطقة<input id="clientArea" type="text" placeholder="النهضة"></label>
        <label>نوع العقار<input id="clientType" type="text" placeholder="بيت / شقة"></label>
        <label>الميزانية (د.ك)<input id="clientPrice" type="number" min="0" placeholder="400000"></label>
        <label class="wide">ملاحظة / رسالة التواصل<input id="clientNote" type="text" placeholder="ما الذي يبحث عنه هذا العميل؟"></label>
      </div>
      <button class="primary" type="submit">حفظ العميل</button>
      <span id="clientFormStatus" class="scope-note"></span>
    </form>
    <div class="client-list-head"><strong>قاعدة العملاء المحتملين (${clients.length})</strong></div>
    <div class="client-list">${rows || '<div class="empty">لا يوجد عملاء بعد.</div>'}</div>
  `;
  const form = $("clientForm");
  if (form) form.addEventListener("submit", (ev) => { ev.preventDefault(); saveClient(); });
}

async function saveClient() {
  const status = $("clientFormStatus");
  const payload = {
    phone: $("clientPhone")?.value.trim() || "",
    area: $("clientArea")?.value.trim() || "",
    type: $("clientType")?.value.trim() || "",
    price: $("clientPrice")?.value || "",
    note: $("clientNote")?.value.trim() || "",
  };
  if (!payload.phone) { if (status) status.textContent = "رقم الهاتف مطلوب."; return; }
  if (status) status.textContent = "جاري الحفظ...";
  try {
    const result = await postJson("/api/clients", payload);
    if (status) status.textContent = result.status === "added" ? "تمت الإضافة بنجاح ✓" : (result.status === "exists" ? "الرقم موجود مسبقًا (تم التحديث)" : `فشل: ${result.status}`);
    await loadOpportunityTab("clients");
  } catch (err) {
    console.error(err);
    if (status) status.textContent = `تعذر الحفظ: ${err.message}`;
  }
}

// ─── الموجز الأسبوعي: أفضل 10 فرص لكل عميل مع رسالة واتساب جاهزة ──────────
function oppDigestItem(item, i) {
  const price = item.priceText || oppMoney(item.price);
  const sources = Array.from(new Set((item.evidence || []).map((e) => e.source).filter(Boolean)));
  const sourcesText = sources.length ? ` — المصادر: ${sources.join("، ")}` : "";
  const link = item.url ? ` <a class="comp-open" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">فتح الإعلان ↗</a>` : "";
  return `<div class="digest-item">
    <span class="digest-rank">${i + 1}</span>
    <strong>${escapeHtml(item.code || "")}</strong>
    <span>${escapeHtml(item.area || "غير محددة")} — ${escapeHtml(price)}</span>
    <span class="recommendation">${escapeHtml(item.valuationLabel || "")}</span>
    <small>${escapeHtml(sourcesText)}</small>
    ${link}
  </div>`;
}

function renderDigestTab(root) {
  const payload = oppState.digest;
  if (!payload) {
    root.innerHTML = '<div class="empty">جاري التحميل...</div>';
    return;
  }
  const note = payload.note || "";
  if (!payload.digests || !payload.digests.length) {
    root.innerHTML = (note ? `<p class="scope-note">${escapeHtml(note)}</p>` : "") +
      '<div class="empty">لا توجد فرص مطابقة للعملاء المسجلين حاليًا. أضف عملاء جددًا أو انتظر فرصًا جديدة في مناطقهم.</div>';
    return;
  }
  root.innerHTML = (note ? `<p class="scope-note">${escapeHtml(note)}</p>` : "") +
    payload.digests.map((d, di) => {
      const label = [d.client.area, d.client.type].filter(Boolean).join(" - ") || "عميل";
      const budget = d.client.price ? ` (ميزانية ${d.client.price} د.ك)` : "";
      const phones = (d.phones || []).map((p) => `<code dir="ltr">${escapeHtml(p)}</code>`).join(" ");
      const sendLinks = (d.phones || []).map((phone) => {
        const base = waLink(phone);
        return base ? `<a class="wa-open" href="${escapeHtml(base)}?text=${encodeURIComponent(d.message)}" target="_blank" rel="noreferrer">📲 إرسال واتساب</a>` : "";
      }).join(" ");
      return `<article class="result-card opp-card digest-card">
        <div class="rank-cell opp-rank">${di + 1}</div>
        <div class="result-body">
          <div class="result-head">
            <div>
              <h3>${escapeHtml(label)}${escapeHtml(budget)}</h3>
              <p class="meta">أفضل ${d.matchCount} فرص هذا الأسبوع | ${phones}</p>
            </div>
            <div class="verdict opp-verdict">
              <span class="verdict-label">موجز أسبوعي</span>
              <strong class="recommendation">${d.matchCount} فرصة</strong>
            </div>
          </div>
          <div class="digest-list">${(d.opportunities || []).map(oppDigestItem).join("")}</div>
          <details class="digest-message">
            <summary>الرسالة الجاهزة للإرسال</summary>
            <textarea id="digest-msg-${di}" rows="8" dir="auto">${escapeHtml(d.message)}</textarea>
          </details>
          <div class="opp-actions">
            <button class="opp-copy-btn digest-copy" type="button" data-digest="${di}">نسخ الرسالة</button>
            ${sendLinks}
          </div>
        </div>
      </article>`;
    }).join("");
  root.querySelectorAll(".digest-card").forEach((card, di) => {
    const digest = (oppState.digest.digests || [])[di] || {};
    card.querySelectorAll(".digest-copy").forEach((btn) => {
      btn.addEventListener("click", () => {
        copyText(digest.message || "", btn);
        trackOutreach({ action: "copy", channel: "weekly_digest" });
      });
    });
    card.querySelectorAll(".wa-open").forEach((link) => {
      link.addEventListener("click", () => trackOutreach({
        action: "send",
        channel: "weekly_digest",
        clientPhone: String((digest.phones || [])[0] || ""),
        clientArea: digest.client ? digest.client.area : "",
        clientType: digest.client ? digest.client.type : "",
      }));
    });
  });
}

function renderAlertsTab(root) {
  const alerts = oppState.alerts || [];
  const note = oppState.alertsNote || "";
  root.innerHTML = (note ? `<p class="scope-note">${escapeHtml(note)}</p>` : "") +
    `<p class="scope-note">تُقارن آخر لقطتين للفرص يوميًا وتُبنى رسالة جاهزة لكل عميل مطابق — اضغط «نسخ الرسالة» ثم ألصقها في واتساب.</p>` +
    (alerts.length ? alerts.map(oppAlertCard).join("") : '<div class="empty">لا توجد تنبيهات جديدة حاليًا. تحدّث الآن ثم عُد لاحقًا لرؤية التغيرات.</div>');
  root.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ta = $("alert-" + btn.dataset.copy);
      copyText(ta ? ta.value : "", btn);
    });
  });
}

// مخطط أعمدة مكدسة لتطور نقرات التسويق (نسخ أزرق + إرسال أخضر) من outreach_clicks
function oppClicksBarChart(buckets, labelKey) {
  const width = 720;
  const height = 170;
  const padT = 14;
  const padB = 20;
  const padL = 30;
  const padR = 8;
  const plotH = height - padT - padB;
  const max = Math.max(...buckets.map((b) => b.total || 0), 1);
  const n = buckets.length || 1;
  const slot = (width - padL - padR) / n;
  const barW = Math.max(4, slot * 0.62);
  const bars = buckets.map((b, i) => {
    const x = padL + i * slot + (slot - barW) / 2;
    const cH = ((b.copies || 0) / max) * plotH;
    const sH = ((b.sends || 0) / max) * plotH;
    const yTop = padT + plotH - (cH + sH);
    return `
      <rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${barW.toFixed(1)}" height="${cH.toFixed(1)}" fill="#1457a8" rx="2"/>
      <rect x="${x.toFixed(1)}" y="${(yTop + cH).toFixed(1)}" width="${barW.toFixed(1)}" height="${sH.toFixed(1)}" fill="#25d366" rx="2"/>`;
  }).join("");
  const step = Math.max(1, Math.ceil(n / 10));
  const labels = buckets.map((b, i) => {
    if (i % step !== 0) return "";
    const x = padL + i * slot + slot / 2;
    return `<text x="${x.toFixed(1)}" y="${height - 4}" text-anchor="middle" class="hist-date">${escapeHtml(String(b[labelKey] || "").slice(5))}</text>`;
  }).join("");
  return `
    <div class="hist-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="تطور نقرات التسويق عبر الزمن">
        ${bars}
        ${labels}
      </svg>
    </div>
    <div class="hist-legend">
      <span class="hist-legend-item"><i style="background:#1457a8"></i>نسخ</span>
      <span class="hist-legend-item"><i style="background:#25d366"></i>إرسال</span>
    </div>`;
}

function renderHistoryTab(root) {
  const data = oppState.history;
  let historyHtml = '<div class="empty">لا توجد لقطات تاريخية كافية بعد. حدّث «أفضل الفرص» بانتظام لتُبنى سلسلة الأداء مع الوقت.</div>';
  if (data && data.series && data.series.length) {
    const series = data.series.slice(0, 6);
    const allValues = series.flatMap((entry) => entry.points.map((p) => p.value));
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const span = (max - min) || 1;
    const width = 720;
    const height = 240;
    const padL = 8;
    const padR = 8;
    const padT = 14;
    const padB = 18;
    const xFor = (i, len) => padL + (len <= 1 ? width / 2 : (i / (len - 1)) * (width - padL - padR));
    const yFor = (v) => padT + (1 - (v - min) / span) * (height - padT - padB);
    const colors = ["#1a7f4f", "#2b6cb0", "#c05621", "#6b46c1", "#b83280", "#2c7a7b"];
    const lines = series.map((entry, s) => {
      const pts = entry.points.map((p, i) => `${xFor(i, entry.points.length).toFixed(1)},${yFor(p.value).toFixed(1)}`).join(" ");
      return `<polyline fill="none" stroke="${colors[s % colors.length]}" stroke-width="2.5" points="${pts}"/>`;
    }).join("");
    const legend = series.map((entry, s) => {
      const cls = entry.direction === "صاعد" ? "up" : entry.direction === "هابط" ? "down" : "flat";
      const change = entry.changePercent != null ? `${entry.changePercent > 0 ? "+" : ""}${entry.changePercent}%` : "";
      return `<div class="hist-legend-item"><i style="background:${colors[s % colors.length]}"></i>${escapeHtml(entry.area)} <span class="opp-direction ${cls}">${escapeHtml(entry.direction)} ${escapeHtml(change)}</span></div>`;
    }).join("");
    const dates = data.dates || [];
    historyHtml = `
      <p class="scope-note">سلسلة الأداء من ${data.snapshotCount} لقطة محفوظة في Supabase — وسيط سعر المتر (د.ك/م²) لكل منطقة عبر الزمن.</p>
      <div class="hist-chart">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="تطور أسعار المتر عبر الزمن">
          ${lines}
          ${dates.map((d, i) => `<text x="${(xFor(i, dates.length)).toFixed(1)}" y="${height - 2}" class="hist-date">${escapeHtml(d.slice(5))}</text>`).join("")}
        </svg>
      </div>
      <div class="hist-legend">${legend}</div>
    `;
  }

  // تفاعل العملاء مع فرص التسويق (نسخ/إرسال) — عدّادات من جدول outreach_clicks
  const outreach = oppState.outreach;
  let outreachHtml = "";
  if (outreach) {
    if (!outreach.tableOk) {
      outreachHtml = `
        <div class="outreach-block">
          <h3>تفاعل العملاء مع فرص التسويق</h3>
          <p class="scope-note">جدول <code dir="ltr">outreach_clicks</code> غير موجود في Supabase بعد. أنشئه بتشغيل
          <code dir="ltr">supabase/migrations/007_outreach_clicks.sql</code> في SQL Editor ثم أعد التحميل.</p>
        </div>`;
    } else {
      const t = outreach.totals || {};
      const timeline = outreach.timeline || [];
      const weekly = outreach.weekly || [];
      const charts = (timeline.length
        ? `<h4 class="outreach-chart-title">يوميًا (آخر 30 يومًا)</h4>${oppClicksBarChart(timeline, "date")}`
        : "") + (weekly.length
        ? `<h4 class="outreach-chart-title">أسبوعيًا (آخر 12 أسبوعًا)</h4>${oppClicksBarChart(weekly, "week")}`
        : "");
      // أفضل 5 عملاء تفاعلًا مع الفرص المرسلة إليهم + شارة نسبة الرد المتوقعة
      const top = (outreach.clients || []).slice(0, 5);
      const topHtml = top.length ? `
        <h4 class="outreach-chart-title">أفضل العملاء نشاطًا (أعلى 5)</h4>
        <div class="top-clients">
          ${top.map((c, i) => {
            const pct = c.expectedResponse ?? 0;
            const cls = pct >= 50 ? "resp-high" : (pct >= 25 ? "resp-mid" : "resp-low");
            return `<div class="top-client">
              <span class="top-client-rank">${i + 1}</span>
              <div class="top-client-info">
                <strong>${escapeHtml(c.area || "")} ${escapeHtml(c.type || "")}</strong>
                <code dir="ltr">${escapeHtml(c.phone || "غير مرتبط")}</code>
                <small>${c.count} نقرة · ${escapeHtml(c.activityTier || "")} · نسخ ${c.copies} | إرسال ${c.sends}</small>
              </div>
              <span class="resp-badge ${cls}" title="نسبة الرد المتوقعة (تقدير حتمي)">${pct}%</span>
            </div>`;
          }).join("")}
        </div>
        <p class="scope-note">${escapeHtml(outreach.responseMethod || "")}</p>` : "";
      const rows = (outreach.clients || []).map((c, i) => `
        <div class="client-row">
          <strong>${i + 1}</strong>
          <code dir="ltr">${escapeHtml(c.phone || "غير مرتبط بعميل")}</code>
          <span>${escapeHtml(c.area || "")} ${escapeHtml(c.type || "")}</span>
          <span>نسخ ${c.copies} | إرسال ${c.sends}</span>
          <span class="outreach-total">${c.count} نقرة</span>
          <small>${escapeHtml(String(c.lastAt || "").slice(0, 16).replace("T", " "))}</small>
        </div>`).join("") || '<div class="empty">لا توجد نقرات مسجلة بعد — انقر «نسخ ملخص» أو «إرسال واتساب» على أي فرصة لتظهر هنا.</div>';
      outreachHtml = `
        <div class="outreach-block">
          <h3>تفاعل العملاء مع فرص التسويق</h3>
          <p class="scope-note">الإجمالي: ${t.total ?? 0} نقرة (نسخ ${t.copies ?? 0} | إرسال ${t.sends ?? 0}) عبر ${t.clients ?? 0} عميل.</p>
          ${charts}
          ${topHtml}
          <div class="client-list">${rows}</div>
        </div>`;
    }
  }
  root.innerHTML = historyHtml + outreachHtml;
}

// ---------------------------------------------------------------------------
// العرض والطلب + الجديد والمحذوف
// ---------------------------------------------------------------------------
function renderMatchingTab(root) {
  const data = oppState.matching;
  if (!data) { root.innerHTML = '<div class="empty">لا توجد بيانات.</div>'; return; }
  const byKind = data.byKind || {};
  const head = `<div class="matching-stats">
      <span class="stat-chip stat-buy">طلبات شراء <b>${byKind.buy || 0}</b></span>
      <span class="stat-chip stat-rent">طلبات إيجار <b>${byKind.rent || 0}</b></span>
      <span class="stat-chip stat-ok">طلبات لها فرص مطابقة <b>${data.matchedDemandCount || 0}</b></span>
      <span class="stat-chip">فرص متاحة مقيّمة <b>${data.supplyCount || 0}</b></span>
    </div>
    <p class="scope-note">${escapeHtml(data.note || "")}</p>`;
  const requests = (data.requests || []).filter((r) => r.matchCount).slice(0, 20);
  const cards = requests.map((req) => {
    const kindLabel = req.kind === "buy" ? "شراء" : (req.kind === "rent" ? "إيجار" : "بيع");
    const budget = req.budgetText ? `<span class="demand-budget">ميزانية ${escapeHtml(req.budgetText)}</span>` : "";
    const matches = (req.matches || []).slice(0, 4).map((m, i) => `
      <div class="match-item">
        <div class="match-head">
          <span class="match-rank">${i + 1}</span>
          <strong>${escapeHtml(m.code)} — ${escapeHtml(m.area || "غير محددة")}</strong>
          <span class="match-score">تطابق ${m.matchScore}/100</span>
        </div>
        <p class="meta">${escapeHtml(m.source || "")}${m.listingType && m.listingType !== "غير محدد" ? ` | ${escapeHtml(m.listingType)}` : ""} | ${escapeHtml(m.transaction || "")} | ${escapeHtml(m.propertyType || "")} | ${m.matchReasons ? escapeHtml(m.matchReasons.join(" · ")) : ""}</p>
        <div class="score-grid">
          ${scoreItem("السعر", m.priceText || oppMoney(m.price))}
          ${scoreItem("المساحة", m.space ? `${m.space} م²` : "—")}
          ${scoreItem("التقييم", m.valuationLabel || "—")}
          ${scoreItem("درجة الفرصة", `${Math.round(m.score || 0)}/100`)}
          ${scoreItem("وسيط المقارنات", oppMoney(m.marketMedian))}
          ${scoreItem("مصادر", (m.evidence || []).length)}
        </div>
        <p class="valuation-reason opp-reason">${escapeHtml(m.valuationReason || "")}</p>
        <div class="match-sources">${(m.evidence || []).slice(0, 3).map((e) => `<span class="comp-source">${escapeHtml(e.source || "")} ${escapeHtml(e.code || "")} ${escapeHtml(e.priceText || "")}</span>`).join(" ")}</div>
        <div class="opp-actions">
          ${m.url ? `<a class="open-link" href="${escapeHtml(m.url)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي</a>` : ""}
          ${m.clients && m.clients.length ? `<span class="match-clients-note">عملاء مطابقون: ${m.clients.length}</span>` : ""}
        </div>
      </div>`).join("");
    return `<details class="demand-card">
      <summary>
        <div class="demand-head">
          <span class="demand-badge demand-${escapeHtml(req.kind)}">${kindLabel}</span>
          <strong>${escapeHtml(req.transaction)} — ${escapeHtml(req.area || "غير محددة")}</strong>
          ${budget}
          <span class="demand-count">${req.matchCount} فرصة مطابقة</span>
        </div>
      </summary>
      <p class="demand-summary">${escapeHtml(req.summary || "")}</p>
      <div class="match-list">${matches || '<div class="empty">لا توجد فرص مطابقة.</div>'}</div>
      ${req.url ? `<a class="open-link" href="${escapeHtml(req.url)}" target="_blank" rel="noreferrer">فتح طلب العميل الأصلي</a>` : ""}
    </details>`;
  }).join("");
  const hot = (data.hotOffers || []).slice(0, 10).map((h, i) => `
    <div class="hot-offer">
      <span class="hot-rank">${i + 1}</span>
      <strong>${escapeHtml(h.code)} — ${escapeHtml(h.area || "غير محددة")}</strong>
      <span class="hot-price">${escapeHtml(h.priceText || oppMoney(h.price))}</span>
      <span class="hot-demand">يطلبه ${h.demandCount} طلب</span>
      <span class="hot-score">${Math.round(h.score || 0)}/100</span>
      ${h.url ? `<a class="open-link" href="${escapeHtml(h.url)}" target="_blank" rel="noreferrer">فتح</a>` : ""}
    </div>`).join("");
  const hotSection = hot ? `<h4 class="opp-subhead">الفرص الأكثر طلبًا (الأعلى تطابقًا مع أكبر عدد من الطلبات)</h4><div class="hot-list">${hot}</div>` : "";
  root.innerHTML = head
    + (cards ? `<h4 class="opp-subhead">التوفيق العملي لكل طلب — بأفضل الفرص المقيّمة</h4>${cards}` : '<div class="empty">لا توجد طلبات مطابقة حاليًا.</div>')
    + hotSection;
  root.querySelectorAll(".opp-card .opp-reason, .valuation-reason").forEach(attachClampToggle);
}

function renderDeltaTab(root) {
  const data = oppState.delta;
  if (!data) { root.innerHTML = '<div class="empty">لا توجد بيانات.</div>'; return; }
  const counts = data.counts || {};
  const stats = `<div class="matching-stats">
      <span class="stat-chip stat-new">فرص جديدة <b>${counts.added || 0}</b></span>
      <span class="stat-chip stat-removed">محذوفة <b>${counts.removed || 0}</b></span>
      <span class="stat-chip stat-drop">انخفاض سعر <b>${counts.priceDrops || 0}</b></span>
    </div>
    <p class="scope-note">${escapeHtml(data.note || "")}${!data.hasPrevious ? ' · أول لقطة فقط (لا توجد لقطة سابقة للمقارنة بعد) — عدّها بعد التحديث التالي.' : ""}</p>`;
  const section = (title, items, cls) => items.length ? `
    <h4 class="opp-subhead">${title} (${items.length})</h4>
    ${items.map((d) => `
      <article class="result-card delta-card ${cls}">
        <div class="result-body">
          <div class="result-head">
            <div>
              <h3>${escapeHtml(d.code)} — ${escapeHtml(d.area || "غير محددة")}</h3>
              <p class="meta">${escapeHtml(d.source || "")}${d.listingType && d.listingType !== "غير محدد" ? ` | ${escapeHtml(d.listingType)}` : ""} | ${escapeHtml(d.propertyType || "")}</p>
            </div>
            <div class="verdict"><strong class="recommendation">${escapeHtml(d.priceText || oppMoney(d.price))}</strong></div>
          </div>
          ${d.oldPriceText || d.oldPrice ? `<p class="delta-price">قبل: ${escapeHtml(d.oldPriceText || oppMoney(d.oldPrice))} ← بعد: ${escapeHtml(d.priceText || oppMoney(d.price))}</p>` : ""}
          <p class="delta-guidance">💡 ${escapeHtml(d.guidance || "")}</p>
          ${d.clients && d.clients.length ? `<div class="opp-clients"><strong>عملاء مطابقون (${d.clients.length}):</strong> ${d.clients.map((c) => `<span>${escapeHtml(c.area || "")} ${escapeHtml(c.type || "")} — تطابق ${c.matchScore}/100</span>`).join(" · ")}</div>` : ""}
          ${d.url ? `<a class="open-link" href="${escapeHtml(d.url)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي</a>` : ""}
        </div>
      </article>`).join("")}` : "";
  root.innerHTML = stats
    + section("🆕 فرص جديدة دخلت السوق", data.added || [], "delta-new")
    + section("🗑️ فرص اختفت من السوق", data.removed || [], "delta-removed")
    + section("📉 انخفاض الأسعار", data.priceDrops || [], "delta-drop");
}

function renderOppTier() {
  const root = $("oppList");
  if (!root || !oppState.data) return;
  // مرشّح المصدر ونوع الإعلان (مباشر/مكتب) خاص بتبويبات الفرص (الأفضل + الفئات الزمنية)
  setOppSourceRowVisible(["best", "daily", "weekly", "monthly", "yearly"].includes(oppState.tier));
  if (oppState.tier === "clients") { renderClientsTab(root); return; }
  if (oppState.tier === "alerts") { renderAlertsTab(root); return; }
  if (oppState.tier === "history") { renderHistoryTab(root); return; }
  if (oppState.tier === "forecast") {
    const total = oppState.data.forecast || [];
    const items = total.filter((item) => {
      // كل توقع خاص بمنطقة: فلتر المنطقة يعمل مباشرة، ونوع العقار/الدرجة لا تنطبق على التوقعات المجمعة
      if (oppState.area && item.area !== oppState.area) return false;
      if (oppState.minPrice != null && (item.expectedPricePerSqm ?? 0) * 400 < oppState.minPrice) return false;
      if (oppState.maxPrice != null && (item.expectedPricePerSqm ?? Infinity) * 400 > oppState.maxPrice) return false;
      return true;
    });
    const hint = items.length !== total.length
      ? '<p class="scope-note">الفلاتر المطبقة: المنطقة و/أو نطاق السعر (مقدرًا على 400 م²). فلاتر نوع العقار والدرجة خاصة بتبويبات الفرص.</p>'
      : "";
    root.innerHTML = hint + (items.length
      ? items.map(oppForecastCard).join("")
      : '<div class="empty">لا توجد توقعات كافية بعد.</div>');
    return;
  }
  let items;
  let note;
  if (oppState.tier === "best") {
    // «الأفضل»: دمج كل الفئات الزمنية (بإزالة التكرار بالكود) مع شارة الفئة الأدق لكل فرصة
    const pool = [];
    const seen = new Set();
    const tierItems = oppState.data.tiers || {};
    for (const key of ["daily", "weekly", "monthly", "yearly"]) {
      for (const item of (tierItems[key]?.items || [])) {
        if (item.code && seen.has(item.code)) continue;
        if (item.code) seen.add(item.code);
        pool.push({ ...item, bestTier: key });
      }
    }
    renderOppSourceCounts(pool);
    items = oppFilteredItems(pool);
    note = `أفضل الفرص على الإطلاق — مدمجة من كل الفئات الزمنية (يعرض ${items.length} من أصل ${pool.length}) مع شارة الفئة الأدق لكل فرصة`;
  } else {
    const tier = (oppState.data.tiers || {})[oppState.tier];
    if (!tier) {
      root.innerHTML = '<div class="empty">لا توجد بيانات.</div>';
      return;
    }
    renderOppSourceCounts(tier.items || []);
    items = oppFilteredItems(tier.items);
    note = `${tier.label} — ${tier.description} (يعرض ${items.length} من أصل ${(tier.items || []).length})`;
  }
  root.innerHTML = `<p class="scope-note">${escapeHtml(note)}</p>` +
    (items.length ? items.map(oppCard).join("") : '<div class="empty">لا توجد فرص مطابقة للفلاتر الحالية.</div>');
  root.querySelectorAll(".opp-card .opp-reason").forEach(attachClampToggle);
  // أزرار التسويق في كل بطاقة فرصة: نسخ/إرسال واتساب + إرسال شخصي لكل عميل — مع تتبع النقرات
  root.querySelectorAll(".opp-card").forEach((card, i) => {
    const item = items[i] || {};
    const code = item.code || "";
    const clients = (item.clients || []).filter((c) => c.phones);
    card.querySelectorAll(".opp-copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        copyText(oppWhatsAppSummary(item), btn);
        trackOutreach({ action: "copy", channel: "opportunity_card", opportunityCode: code });
      });
    });
    card.querySelectorAll(".wa-share").forEach((link) => {
      link.addEventListener("click", () => trackOutreach({ action: "send", channel: "opportunity_card", opportunityCode: code }));
    });
    card.querySelectorAll(".wa-client").forEach((link, j) => {
      const client = clients[j] || {};
      link.addEventListener("click", () => trackOutreach({
        action: "send",
        channel: "client_send",
        opportunityCode: code,
        clientPhone: String(client.phones || "").split(/[|،,]+/)[0] || "",
        clientArea: client.area || "",
        clientType: client.type || "",
      }));
    });
  });
}

function renderOppMeta() {
  const updated = $("oppUpdated");
  if (updated && oppState.data) updated.textContent = `آخر تحديث: ${oppState.data.generatedDate || ""} — ${oppState.data.totalScored} فرصة مُسجَّلة`;
  const note = $("oppOfficialNote");
  if (note && oppState.data) {
    const rental = oppState.data.rentalNote ? ` ${oppState.data.rentalNote}` : "";
    note.textContent = (oppState.data.officialDataNote || "") + rental;
    note.hidden = !note.textContent;
  }
  const method = $("oppConfidenceMethod");
  if (method && oppState.data) {
    method.textContent = oppState.data.confidenceMethod || "";
    method.hidden = !method.textContent;
  }
}

function updateNoticeItem(label, value, tone = "") {
  return `<span class="update-count ${tone}"><b>${escapeHtml(String(value ?? 0))}</b>${escapeHtml(label)}</span>`;
}

function renderDailyUpdateNotice(data) {
  const box = $("dailyUpdateNotice");
  if (!box) return;
  if (!data) {
    box.hidden = true;
    return;
  }
  const counts = data.counts || {};
  const official = data.officialTransactions || {};
  const generated = data.generatedAt ? String(data.generatedAt).replace("T", " ").slice(0, 16) : "لم يعمل بعد";
  const nextRun = "6:00 صباحًا يوميًا";
  const officialText = official.storedCount != null
    ? `${official.storedCount} صفقة رسمية محفوظة`
    : "لا يوجد عداد صفقات رسمية";
  const actions = (data.actions || []).map((action) => `<li>${escapeHtml(action)}</li>`).join("");
  box.innerHTML = `
    <div class="update-main">
      <strong>ملخص التحديث اليومي</strong>
      <span>آخر تشغيل: ${escapeHtml(generated)} · القادم: ${escapeHtml(nextRun)}</span>
    </div>
    <div class="update-counts">
      ${updateNoticeItem("فرص جديدة", counts.added, "good")}
      ${updateNoticeItem("انخفاض سعر", counts.priceDrops, "hot")}
      ${updateNoticeItem("محذوف/اختفى", counts.removed, "muted")}
      ${updateNoticeItem("صفقات وزارة العدل", official.importCount || 0, official.importCount ? "good" : "warn")}
    </div>
    <div class="update-official">${escapeHtml(officialText)} · حالة آخر استيراد: ${escapeHtml(official.importStatus || "غير معروف")} · الكاش: يومي للفرص، أسبوعي للموجز.</div>
    ${actions ? `<ul class="update-actions">${actions}</ul>` : ""}
    <div class="update-agent-actions">
      <button id="runDailyAgentBtn" class="secondary" type="button">تشغيل وكيل التحديث الآن</button>
      <span id="dailyAgentState" class="update-agent-state"></span>
    </div>
  `;
  box.hidden = false;
  const runBtn = $("runDailyAgentBtn");
  if (runBtn) runBtn.addEventListener("click", runDailyAgentNow);
}

function renderDailyAgentOfficialSources(status) {
  const box = $("dailyUpdateNotice");
  if (!box || !status || !status.summary) return;
  const official = status.summary.officialReferenceSources;
  if (!official || !official.sources) return;
  const existing = box.querySelector(".official-reference-strip");
  if (existing) existing.remove();
  const strip = document.createElement("div");
  strip.className = "official-reference-strip";
  strip.innerHTML = `
    <strong>مصادر رسمية مرجعية:</strong>
    <span>${official.reachable || 0}/${official.count || 0} متاح</span>
    ${(official.sources || []).slice(0, 4).map((source) => `
      <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.name)}</a>
    `).join("")}
  `;
  box.appendChild(strip);
}

async function loadDailyUpdateNotice() {
  try {
    renderDailyUpdateNotice(await getJson("/api/update-notifications"));
  } catch (err) {
    console.warn("Update notifications unavailable", err);
  }
}

async function loadDailyAgentStatus() {
  const stateEl = $("dailyAgentState");
  const inlineStateEl = $("dailyAgentStateInline");
  try {
    const status = await getJson("/api/daily-agent/status");
    if (stateEl) {
      const finished = status.finishedAt ? String(status.finishedAt).replace("T", " ").slice(0, 16) : "";
      stateEl.textContent = `حالة الوكيل: ${status.status || "غير معروف"}${finished ? ` · ${finished}` : ""}`;
    }
    if (inlineStateEl) {
      const finished = status.finishedAt ? String(status.finishedAt).replace("T", " ").slice(0, 16) : "";
      inlineStateEl.textContent = `آخر تشغيل: ${finished || "لم يعمل بعد"} · الحالة: ${status.status || "غير معروف"} · التحديث المجدول 6:00 صباحًا.`;
    }
    renderDailyAgentOfficialSources(status);
  } catch (err) {
    if (stateEl) stateEl.textContent = "تعذر قراءة حالة الوكيل";
    if (inlineStateEl) inlineStateEl.textContent = "تعذر قراءة حالة الوكيل من الباك إند.";
  }
}

async function runDailyAgentNow() {
  const buttons = ["runDailyAgentBtn", "runDailyAgentBtnInline"].map((id) => $(id)).filter(Boolean);
  const btn = buttons[0] || null;
  const stateEl = $("dailyAgentState");
  const inlineStateEl = $("dailyAgentStateInline");
  const originals = buttons.map((button) => button.textContent);
  buttons.forEach((button) => {
    button.disabled = true;
    button.textContent = "جاري تشغيل الوكيل...";
  });
  if (stateEl) stateEl.textContent = "يتم تحديث المصادر والفرص الآن...";
  if (inlineStateEl) inlineStateEl.textContent = "يتم تحديث المصادر والفرص الآن...";
  try {
    const response = await fetch(apiUrl("/api/daily-agent/run"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ includeExternal: true }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.detail || "فشل تشغيل الوكيل");
    if (stateEl) stateEl.textContent = `اكتمل التشغيل: ${result.status}`;
    if (inlineStateEl) inlineStateEl.textContent = `اكتمل التشغيل: ${result.status}`;
    await loadDailyUpdateNotice();
    await loadDailyAgentStatus();
    await loadOpportunities(false);
  } catch (err) {
    if (stateEl) stateEl.textContent = `فشل التشغيل: ${err.message}`;
    if (inlineStateEl) inlineStateEl.textContent = `فشل التشغيل: ${err.message}`;
  } finally {
    buttons.forEach((button, index) => {
      button.disabled = false;
      button.textContent = originals[index];
    });
  }
}

async function importOfficialTransactions() {
  const input = $("officialImportFile");
  const status = $("officialImportStatus");
  const btn = $("officialImportBtn");
  const file = input && input.files ? input.files[0] : null;
  if (!file) {
    if (status) status.textContent = "اختر ملف CSV أو JSON أولًا.";
    return;
  }
  const original = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "جاري الاستيراد...";
  }
  if (status) status.textContent = "يتم قراءة الملف وحفظه في قاعدة البيانات...";
  try {
    const content = await file.text();
    const result = await postJson("/api/official-transactions/import", {
      filename: file.name,
      content,
    });
    if (status) {
      status.textContent = `تم استيراد ${result.imported || 0} صفقة | Supabase: ${result.supabase || "-"} | الإجمالي المحلي: ${result.localTotal || 0}`;
    }
    await runDailyAgentNow();
  } catch (err) {
    if (status) status.textContent = `فشل الاستيراد: ${err.message}`;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = original;
    }
  }
}

async function loadOpportunities(forceRefresh = false) {
  const root = $("oppList");
  if (!root) return;
  root.innerHTML = '<div class="empty">جاري تحميل أفضل الفرص...</div>';
  try {
    oppState.data = await getJson(`/api/opportunities${forceRefresh ? "?refresh=1" : ""}`);

    const allItems = Object.values(oppState.data.tiers || {}).flatMap((tier) => tier.items || []);
    fillOppSelect("oppGovFilter", allItems.map((item) => item.governorate));
    fillOppSelect("oppAreaFilter", allItems.map((item) => item.area));
    fillOppSelect("oppTypeFilter", allItems.map((item) => item.propertyType));

    renderOppMeta();
    loadDailyUpdateNotice();
    loadDailyAgentStatus();
    renderOppTier();
  } catch (err) {
    console.error(err);
    root.innerHTML = `<div class="empty">تعذر تحميل الفرص: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadOpportunityTab(tier) {
  const root = $("oppList");
  if (!root) return;
  oppState.tier = tier;
  root.innerHTML = '<div class="empty">جاري التحميل...</div>';
  try {
    if (tier === "clients") {
      const payload = await getJson("/api/clients");
      oppState.clients = payload.clients || [];
      renderClientsTab(root);
    } else if (tier === "alerts") {
      const payload = await getJson("/api/whatsapp-alerts");
      oppState.alerts = payload.alerts || [];
      oppState.alertsNote = payload.note || "";
      renderAlertsTab(root);
    } else if (tier === "digest") {
      oppState.digest = await getJson("/api/weekly-digest");
      renderDigestTab(root);
    } else if (tier === "history") {
      const [historyRes, outreachRes] = await Promise.all([
        getJson("/api/opportunities/history"),
        getJson("/api/outreach/stats").catch(() => null),
      ]);
      oppState.history = historyRes;
      oppState.outreach = outreachRes;
      renderHistoryTab(root);
    } else if (tier === "matching") {
      oppState.matching = await getJson("/api/market-matching");
      renderMatchingTab(root);
    } else if (tier === "delta") {
      oppState.delta = await getJson("/api/opportunity-delta");
      renderDeltaTab(root);
    }
  } catch (err) {
    console.error(err);
    root.innerHTML = `<div class="empty">تعذر التحميل: ${escapeHtml(err.message)}</div>`;
  }
}

function bindOppEvents() {
  const tabs = document.querySelectorAll(".opp-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      oppState.tier = tab.dataset.tier;
      if (["clients", "alerts", "digest", "history", "matching", "delta"].includes(oppState.tier)) {
        loadOpportunityTab(oppState.tier);
      } else {
        renderOppTier();
      }
    });
  });
  const refreshBtn = $("oppRefreshBtn");
  if (refreshBtn) refreshBtn.addEventListener("click", () => loadOpportunities(true));
  ["oppGovFilter", "oppAreaFilter", "oppTypeFilter", "oppTransactionFilter", "oppMinPrice", "oppMaxPrice", "oppMinScore"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("change", () => { collectOppFilters(); renderOppTier(); });
  });
  // مرشّح المصدر (الكل / مواقع خارجية / الفريج فقط) — أزرار شرائح بعدّادات لكل فئة
  document.querySelectorAll(".opp-source-chip[data-source]").forEach((chip) => {
    chip.addEventListener("click", () => {
      oppState.source = chip.dataset.source || "";
      renderOppTier();
    });
  });
  // مرشّح نوع الإعلان (كل الأنواع / مباشر / مكتب)
  document.querySelectorAll(".opp-source-chip[data-kind]").forEach((chip) => {
    chip.addEventListener("click", () => {
      oppState.kind = chip.dataset.kind || "";
      renderOppTier();
    });
  });
}

function bind() {
  // ربط آمن: يتخطى أي زر غير موجود في الصفحة الحالية
  const on = (id, fn) => {
    const el = $(id);
    if (el) el.addEventListener("click", fn);
  };
  document.addEventListener("click", (ev) => {
    const target = ev.target;
    if (target && target.closest && target.closest("#sendChatBtn")) {
      ev.preventDefault();
      sendChat();
    }
  }, true);
  on("clearChatBtn", clearChat);
  on("downloadReportBtn", downloadReport);
  on("downloadReportBtnTop", downloadReport);
  on("downloadPdfBtn", () => downloadPdfReport("downloadPdfBtn"));
  on("downloadPdfBtnTop", () => downloadPdfReport("downloadPdfBtnTop"));
  on("officialImportBtn", importOfficialTransactions);
  on("runDailyAgentBtnInline", runDailyAgentNow);
  on("toggleCustomSearchBtn", () => {
    const panel = $("customSearchPanel");
    if (!panel) return;
    panel.hidden = !panel.hidden;
    if (!panel.hidden) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  on("boardRunSearchBtn", () => runBoardAnalysis());
  on("boardClearFiltersBtn", () => {
    ["boardMetricFilter", "boardGovernorateFilter", "boardTransactionFilter", "boardPropertyTypeFilter", "boardListingModeFilter", "boardAreaFilter"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.value = id === "boardMetricFilter" ? "movement" : "";
    });
    const platformInputs = [...document.querySelectorAll('input[name="boardPlatform"]')];
    if (platformInputs.length) {
      for (const input of platformInputs) input.checked = input.value === "__all";
    }
    boardState.activeMetric = "movement";
    loadDashboardBoard();
  });
  on("openEvidenceQuick", () => {
    const target = document.querySelector(".sources-panel");
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  ["boardMetricFilter", "boardGovernorateFilter", "boardTransactionFilter", "boardPropertyTypeFilter", "boardListingModeFilter", "boardAreaFilter"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      if (id === "boardMetricFilter") boardState.activeMetric = el.value || "movement";
      if (id === "boardAreaFilter" && el.value.trim()) rememberRecentArea(el.value.trim());
      renderBoard();
    });
    el.addEventListener("change", () => {
      if (id === "boardMetricFilter") boardState.activeMetric = el.value || "movement";
      if (id === "boardAreaFilter" && el.value.trim()) rememberRecentArea(el.value.trim());
      renderBoard();
    });
  });
  document.querySelectorAll('input[name="boardPlatform"]').forEach((input) => {
    input.addEventListener("change", () => {
      syncPlatformSelect();
      loadDashboardBoard();
    });
  });
  document.addEventListener("click", (ev) => {
    const adBtn = ev.target.closest?.("[data-board-ad-code]");
    if (adBtn) {
      const area = adBtn.dataset.boardAdArea || "";
      const propertyType = adBtn.dataset.boardAdType || "";
      const areaFilter = $("boardAreaFilter");
      const typeFilter = $("boardPropertyTypeFilter");
      if (areaFilter) areaFilter.value = area;
      if (typeFilter) typeFilter.value = propertyType;
      renderBoard();
      runBoardAnalysis({ area, propertyType });
      return;
    }
    const metricCard = ev.target.closest?.("[data-board-metric]");
    if (metricCard) {
      const metric = metricCard.dataset.boardMetric || "movement";
      const metricFilter = $("boardMetricFilter");
      if (metricFilter) metricFilter.value = metric;
      boardState.activeMetric = metric;
      renderBoard();
      return;
    }
    const toggle = ev.target.closest?.("[data-board-toggle-gov]");
    if (toggle) {
      const gov = toggle.dataset.boardToggleGov || "";
      if (boardState.expandedGovernorates.has(gov)) boardState.expandedGovernorates.delete(gov);
      else boardState.expandedGovernorates.add(gov);
      renderBoard();
      return;
    }
    const runBtn = ev.target.closest?.("[data-board-metric-run]");
    if (runBtn) {
      const metric = runBtn.dataset.boardMetricRun || "movement";
      const gov = runBtn.dataset.boardGov || "";
      const area = runBtn.dataset.boardAreaRun || "";
      const metricFilter = $("boardMetricFilter");
      const govFilter = $("boardGovernorateFilter");
      const areaFilter = $("boardAreaFilter");
      if (metricFilter) metricFilter.value = metric;
      if (govFilter) govFilter.value = gov;
      if (areaFilter) areaFilter.value = area;
      boardState.activeMetric = metric;
      renderBoard();
      runBoardAnalysis({ metric, governorate: gov, area });
    }
  });
  const sourceMode = $("sourceModeField");
  const selectedSource = $("selectedSourceField");
  const syncSourceSelect = () => {
    if (selectedSource) selectedSource.disabled = (sourceMode?.value || "local") !== "source";
    const includeExternal = $("includeExternal");
    if (includeExternal) includeExternal.disabled = (sourceMode?.value || "local") === "local";
  };
  if (sourceMode) sourceMode.addEventListener("change", syncSourceSelect);
  syncSourceSelect();

  const chatInput = $("chatInput");
  if (chatInput) {
    chatInput.addEventListener("keypress", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        sendChat();
      }
    });
  }
}

// تحديث يومي موثّق: يعيد بناء الفرص (بالمصادر الحية) عند الساعة 6:00 صباحًا مرة واحدة يوميًا
let lastDailyAutoRefreshDate = "";
function scheduleDailySixAM() {
  setInterval(() => {
    const now = new Date();
    if (now.getHours() === 6 && now.getMinutes() === 0) {
      const today = now.toDateString();
      if (lastDailyAutoRefreshDate !== today) {
        lastDailyAutoRefreshDate = today;
        loadOpportunities(true);
      }
    }
  }, 30 * 1000);
}

async function boot() {
  bind();
  bindOppEvents();
  loadDashboardBoard();
  loadOpportunities();
  scheduleDailySixAM();
  // تحديث أول بأول: أول تحميل يدمج المصادر الحية (لأن الكاش فارغ)، ثم تحديث محلي سريع كل 5 دقائق
  // (الفحص الحي المتكرر كل دقائق قد يُحظر من المواقع الخارجية — لذلك يكون صريحًا فقط)
  setInterval(() => {
    if (!document.hidden) loadOpportunities(false);
  }, 5 * 60 * 1000);
  try {
    const health = await getJson("/api/health");
    const aiStatus = health.aiAnalysis ? "التحليل الذكي متاح" : "تحليل محلي";
    setStatus(`البيانات: ${health.records} إعلان | قاعدة البيانات: ${health.supabase ? "متصلة" : "غير مضبوطة"} | ${aiStatus}`);
  } catch {
    setStatus("تعذر فحص البيانات");
  }
}

boot();

