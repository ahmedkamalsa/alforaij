/* ===== دخول متدرج لبطاقات النتائج والفرص عند التمرير =====
   يضيف .reveal-card للبطاقات ويراقب ظهورها (IntersectionObserver)، ويعيد
   المراقبة عند إعادة رسم القوائم (MutationObserver). يُعطّل تلقائيًا عند
   تفضيل تقليل الحركة أو غياب IntersectionObserver — البطاقات تبقى ظاهرة.
   البطاقات الظاهرة وقت التحميل تُعلَّم فورًا بلا انتظار تمرير. */
function initCardReveal() {
  if (!("IntersectionObserver" in window)) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("in-view");
        observer.unobserve(entry.target);
      }
    }
  }, { rootMargin: "0px 0px -40px 0px", threshold: 0.05 });

  const watch = () => {
    document.querySelectorAll(".result-card:not(.reveal-card)").forEach((card) => {
      card.classList.add("reveal-card");
      observer.observe(card);
    });
  };
  watch();
  const mo = new MutationObserver(watch);
  mo.observe(document.body, { childList: true, subtree: true });
}

/* ===== تبديل الوضع الفاتح/الداكن ===== */
const THEME_KEY = "alforaij_theme";

function applyTheme(theme) {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "light" ? "#eef2f9" : "#0F172A");
  const btn = document.getElementById("themeToggle");
  if (btn) {
    const isLight = theme === "light";
    const moon = '<svg class="hero-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg> ';
    const sun = '<svg class="hero-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg> ';
    btn.innerHTML = (isLight ? moon : sun) + (isLight ? "الوضع الداكن" : "الوضع الفاتح");
    btn.setAttribute("aria-label", isLight ? "التبديل إلى الوضع الداكن" : "التبديل إلى الوضع الفاتح");
  }
}

function initTheme() {
  let theme = localStorage.getItem(THEME_KEY);
  if (!theme) {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  applyTheme(theme);
  const btn = document.getElementById("themeToggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      localStorage.setItem(THEME_KEY, next);
      applyTheme(next);
    });
  }
}

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
  selectedCell: null, // { governorate, area, metric } — الخلية المختارة في جدول المحافظات
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
const watchedAreasKey = "alforaij_watched_areas_v1";

// ── المناطق المراقبة (احجز منطقة لمراقبة تغيّر فجوتها مقابل وسيط المحافظة) ──
function readWatchedAreas() {
  try {
    const parsed = JSON.parse(localStorage.getItem(watchedAreasKey) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => item && item.area) : [];
  } catch {
    return [];
  }
}

function saveWatchedAreas(list) {
  try {
    localStorage.setItem(watchedAreasKey, JSON.stringify(list));
  } catch {
    // التخزين ممتلئ/محظور — نتجاهل بصمت
  }
}

function isWatchedArea(area) {
  const clean = String(area || "").trim();
  return readWatchedAreas().some((item) => normalizeArabic(item.area) === normalizeArabic(clean));
}

function toggleWatchedArea(area, governorate, gapPct) {
  const clean = String(area || "").trim();
  if (!clean) return;
  let list = readWatchedAreas();
  const existing = list.find((item) => normalizeArabic(item.area) === normalizeArabic(clean));
  if (existing) {
    list = list.filter((item) => normalizeArabic(item.area) !== normalizeArabic(clean));
  } else {
    list.unshift({
      area: clean,
      governorate: governorate || "",
      savedAt: new Date().toISOString(),
      gapAtBooking: gapPct ?? null,
    });
  }
  saveWatchedAreas(list);
  return !existing;
}

const $ = (id) => document.getElementById(id);
const API_BASE = String(window.ALFORAIJ_API_BASE || localStorage.getItem("ALFORAIJ_API_BASE") || "").replace(/\/$/, "");
// الوضع الثابت يُفعَّل فقط عندما لا يوجد API حقيقي: لا رابط مضبوط وخارج الجهاز المحلي.
// على الجهاز المحلي (127.0.0.1/localhost) يعمل الخادم الحي، لذا تُستخدم روابط نسبية لنفس الأصل.
const isLocalHost = /^(localhost|127\.0\.0\.1|::1|0\.0\.0\.0)(:\d+)?$/i.test(window.location.hostname);
const STATIC_SNAPSHOT_MODE = !API_BASE && !isLocalHost;
const STATIC_DATA_MAP = {
  "/api/health": "health.json",
  "/api/sources": "sources.json",
  "/api/dashboard/summary": "dashboard-summary.json",
  "/api/opportunities": "opportunities.json",
  "/api/opportunities/history": "opportunities-history.json",
  "/api/price-trends": "price-trends.json",
  "/api/market-matching": "market-matching.json",
  "/api/opportunity-delta": "opportunity-delta.json",
  "/api/weekly-digest": "weekly-digest.json",
  "/api/whatsapp-alerts": "whatsapp-alerts.json",
  "/api/outreach/stats": "outreach-stats.json",
  "/api/clients": "clients.json",
  "/api/update-notifications": "update-notifications.json",
  "/api/daily-agent/status": "daily-agent-status.json",
  "/api/official-reference-sources": "official-reference-sources.json",
  "/api/search-options": "search-options.json",
  "/api/live-db": "live-db.json",
  "/api/market-insights": "market-insights.json",
  "/api/developments": "developments.json",
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

// تحليل استجابة JSON بأمان: بعض المضيفين (GitHub Pages، خادم ثابت) يرجعون
// صفحة HTML عند نقطة غير موجودة فيفشل response.json() بخطأ «Unexpected token <»
// الغامض — هنا نفحص نوع الرد ونعطي رسالة واضحة بالعربية مع سياق حقيقي.
async function readJsonResponse(response, context = "") {
  const text = await response.text();
  if (!text.trim()) {
    throw new Error(`الخادم أعاد ردًا فارغًا${context ? ` (${context})` : ""}.`);
  }
  const trimmed = text.trim();
  const isJson = trimmed.startsWith("{") || trimmed.startsWith("[");
  if (!isJson) {
    const snippet = trimmed.replace(/\s+/g, " ").slice(0, 120);
    throw new Error(
      `تعذر الاتصال بالخادم${context ? ` (${context})` : ""}: استجاب بصفحة ${response.status || ""} بدل JSON (${snippet}). ` +
      (STATIC_SNAPSHOT_MODE
        ? "هذه النسخة المنشورة لا تستضيف خادم API — الميزة تتطلب تشغيل الخادم المحلي."
        : "تأكد أن الخادم يعمل وأن النقطة صحيحة.")
    );
  }
  try {
    return JSON.parse(trimmed);
  } catch (err) {
    throw new Error(`استجابة JSON غير صالحة من الخادم${context ? ` (${context})` : ""}.`);
  }
}

async function getJson(path) {
  if (STATIC_SNAPSHOT_MODE) return fetchStaticJson(path);
  try {
    const response = await fetch(apiUrl(path));
    if (!response.ok) throw new Error(await response.text());
    return await readJsonResponse(response);
  } catch (err) {
    const fallback = staticDataUrl(path);
    if (!fallback) throw err;
    return fetchStaticJson(path);
  }
}

// كل الأرقام المعروضة بالإنجليزية (0-9) مهما حمل النص أرقامًا عربية هندية (٠-٩)
// من المصادر أو القاعدة — تحويل عند العرض كطبقة أمان فوق تحويل الواجهة الخلفية.
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
function latinDigits(value) {
  return String(value ?? "")
    .replace(/[٠-٩]/g, (d) => String(ARABIC_DIGITS.indexOf(d)))
    .replace(/٫/g, ".")
    .replace(/٬/g, ",");
}

function escapeHtml(value) {
  return latinDigits(value)
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

// توحيد اسم المحافظة (الهمزات والتاء المربوطة) حتى لا تتكرر «محافظة الأحمدي» و«محافظة الاحمدي» كصفين
const GOVERNORATE_CANONICAL = {
  "الاحمدي": "محافظة الأحمدي",
  "حولي": "محافظة حولي",
  "الجهراء": "محافظة الجهراء",
  "العاصمة": "محافظة العاصمة",
  "الفروانية": "محافظة الفروانية",
  "مبارك الكبير": "محافظة مبارك الكبير",
};

function canonicalGovernorate(value) {
  const clean = String(value || "").trim();
  if (!clean) return "";
  let key = clean;
  if (key.startsWith("محافظة ")) key = key.slice("محافظة ".length);
  key = key.replace(/[إأآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").trim();
  // «غير محددة»/«غير محدده» تمثّل نفس التصنيف — توحيدها يمنع انكسار مقارنات جدول المحافظات
  if (key === "غير محدده" || key === "غير محددة") return "غير محددة";
  return GOVERNORATE_CANONICAL[key] || clean;
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
  if (!ignoreGovernorate && filters.governorate && (canonicalGovernorate(row.governorate) || "غير محددة") !== (canonicalGovernorate(filters.governorate) || "غير محددة")) return false;
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

function boardDrillRunFromFilters() {
  const filters = boardFilterValues();
  return {
    metric: filters.metric || "movement",
    governorate: filters.governorate || "",
    area: filters.area || "",
  };
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
  if (areasField) setAreasFromString(filters.area || "");
  if (chatInput) chatInput.value = boardTextFromFilters({ ...filters, transaction });
  if (filters.area) rememberRecentArea(filters.area);
}

async function runBoardAnalysis(overrides = {}) {
  syncBoardToSearch(overrides);
  await sendChat();
  switchMainTab("search");
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

// الموقع المنشور (وضع ثابت): قراءة مباشرة من قاعدة البيانات الحية عبر مفتاح anon العام
// وجداول RLS العامة — فيعرض الترويسة أرقامًا حية فعلًا بدل أرقام اللقطة، مع سقوط آمن.
async function liveDbConfig() {
  try {
    const cfg = await fetchStaticJson("/api/live-db");
    return cfg && cfg.url && cfg.anonKey ? cfg : null;
  } catch {
    return null;
  }
}

// قراءة اتجاهات الأسعار حيًا من جدول price_trends عبر REST (موقع منشور بلا باك إند)
// — جدول عام بسياسة RLS للقراءة العامة، لذا يعمل مباشرة من المتصفح مثل market_listings.
async function fetchLivePriceTrends() {
  const cfg = await liveDbConfig();
  if (!cfg) return null;
  try {
    const headers = { apikey: cfg.anonKey, Authorization: `Bearer ${cfg.anonKey}` };
    const res = await fetch(`${cfg.url.replace(/\/$/, "")}/rest/v1/price_trends?select=area,property_type,month,transaction,median_price,median_price_per_m2,sample_count&order=month.desc&limit=2000`, { headers });
    const rows = await res.json();
    if (!Array.isArray(rows)) return null;
    return { rows, tableOk: true, live: true };
  } catch {
    return null;
  }
}

async function applyLiveDbCounts(statusEl) {
  try {
    const cfg = await fetchStaticJson("/api/live-db");
    if (!cfg || !cfg.url || !cfg.anonKey) return;
    const headers = { apikey: cfg.anonKey, Authorization: `Bearer ${cfg.anonKey}` };
    const base = cfg.url.replace(/\/$/, "");
    const [market, opps] = await Promise.all([
      fetch(`${base}/rest/v1/market_listings?select=count`, { headers }).then((r) => r.json()),
      fetch(`${base}/rest/v1/opportunities?select=count`, { headers }).then((r) => r.json()),
    ]);
    const marketN = Number((market[0] || {}).count || 0);
    const oppsN = Number((opps[0] || {}).count || 0);
    if (!marketN) return;
    const el = statusEl || $("healthStatus");
    if (!el) return;
    // إعلانات الفريج المحلية من اللقطة (مصدرها ملف محلي لا جدول القاعدة)
    const localN = Number(el.dataset.snapshotLocal || 0);
    const breakdown = [`الفريج ${localN}`, `المواقع الخارجية ${marketN}`].join(" + ");
    el.textContent = `البيانات: ${localN + marketN} إعلان مباشر من القاعدة (${breakdown}) | القاعدة: متصلة | ${oppsN} فرصة`;
    el.title = `قراءة حية من قاعدة البيانات — ${breakdown}`;
    el.dataset.live = "1";
  } catch {
    // لا نتصل؟ تبقى أرقام اللقطة المحدَّثة يوميًا كما هي.
  }
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

// محلل نص الاستعلام داخل المتصفح — يستخرج المنطقة/العملية/النوع/المساحة/الميزانية
// من جملة الشات الحرّة (مثل «بيع بيت في النهضة 400م») عند غياب فلاتر النموذج أو الـ API.
function parseQueryFilters(text) {
  const norm = normalizeArabic(text);
  const parsed = { area: "", transaction: "", propertyType: "", minArea: 0, maxArea: 0, budget: 0 };
  if (norm.includes("بدل")) parsed.transaction = "بدل";
  else if (norm.includes("للبيع") || norm.includes("بيع")) parsed.transaction = "للبيع";
  else if (norm.includes("للايجار") || norm.includes("ايجار") || norm.includes("استاجر")) parsed.transaction = "للإيجار";
  else if (norm.includes("مطلوب") || norm.includes("شراء") || norm.includes("ابي") || norm.includes("ابغى")) parsed.transaction = "مطلوب للشراء";
  if (/بيت|منزل|فيلا|قسيم/.test(norm)) parsed.propertyType = "بيت";
  else if (/شقه|شقة|دوبلكس|apartment|flat/.test(norm)) parsed.propertyType = "شقة";
  else if (/ارض|أرض|land|plot/.test(norm)) parsed.propertyType = "أرض";
  else if (/عماره|عمارة|بنايه|building/.test(norm)) parsed.propertyType = "عمارة";
  // المنطقة: أطول اسم منطقة موجود في بيانات اللوحة ويظهر داخل نص الاستعلام
  let best = "";
  for (const area of uniqueValues((boardState.records || []).map((row) => row.area))) {
    const a = normalizeArabic(area);
    if (a && norm.includes(a) && a.length > best.length) best = area;
  }
  parsed.area = best;
  const spaceMatch = norm.match(/(\d+(?:\.\d+)?)\s*م/);
  if (spaceMatch) {
    parsed.minArea = Number(spaceMatch[1]);
    parsed.maxArea = Number(spaceMatch[1]);
  }
  const moneyMatch = norm.match(/(?:ميزانيه|ميزانية|حدود|سعر|بحدود|مطلوب)\s*(\d+(?:\.\d+)?)\s*(الف|ألف)?/);
  if (moneyMatch) {
    let value = Number(moneyMatch[1]);
    if (moneyMatch[2]) value *= 1000;
    parsed.budget = value;
  }
  if (!parsed.budget) {
    const kw = norm.match(/(\d+(?:\.\d+)?)\s*(الف|ألف)?\s*دينار/);
    if (kw) {
      let value = Number(kw[1]);
      if (kw[2]) value *= 1000;
      parsed.budget = value;
    }
  }
  return parsed;
}

// استخراج الدخل الإيجاري من نص إعلان/طلب في المتصفح («مؤجر ب 1200 شهرياً»، «دخله 20 الف»)
// — مطابق لمنطق extract_rental_income في الباك إند للوضع الثابت بلا خادم
function clientExtractRentalIncome(text) {
  let normalized = String(text || "").replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[إأآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/ـ/g, "")
    .replace(/\s+/g, " ").trim();
  const patterns = [
    // مؤجر/مؤجره (ب) X (فترة) — الافتراضي شهري
    { re: /مؤجره?\s+(?:ب)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:دينار|د\.ك|ك\s*د)?\s*(شهريا?|سنويا?|بالشهر|بالسنه|في الشهر|فى الشهر|للشهر|كل شهر)?/, defaultPeriod: "monthly" },
    // دخلها/دخله/ايجارها/قيمه ايجارها X (فترة) — الافتراضي سنوي
    { re: /(?:دخل(?:ها|ه)?|الدخل|مدخولها|ايجارها|قيمه ايجارها|قيمه ايجاره)\s*(?:ب)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:دينار|د\.ك|ك\s*د)?\s*(?:الف|ألف)?\s*(شهريا?|سنويا?|بالشهر|بالسنه|في الشهر|فى الشهر|للشهر|كل شهر)?/, defaultPeriod: "annual" },
  ];
  for (const { re, defaultPeriod } of patterns) {
    const m = normalized.match(re);
    if (!m) continue;
    let amount = parseFloat(m[1]);
    if (m[0].includes("الف") || m[0].includes("ألف")) amount *= 1000;
    else if (amount < 100) amount *= 1000;
    const periodRaw = m[2] || "";
    let period = defaultPeriod;
    if (periodRaw.includes("شهري") || periodRaw.includes("الشهر") || periodRaw.includes("كل شهر")) period = "monthly";
    else if (periodRaw.includes("سنوي") || periodRaw.includes("السنه")) period = "annual";
    return { amount, period };
  }
  return null;
}

function staticAnalyzeReport(payload) {
  const filters = payload.filters || {};
  const text = String(payload.text || "");
  const parsed = parseQueryFilters(text);
  const area = String(filters.areas || filters.area || parsed.area || "").trim();
  const propertyType = String(filters.propertyType || parsed.propertyType || "").trim();
  const transaction = String(filters.transaction || parsed.transaction || "").trim();
  const minArea = Number(filters.minArea || parsed.minArea || 0);
  const maxArea = Number(filters.maxArea || parsed.maxArea || 0);
  const budget = Number(filters.budget || filters.rentBudget || parsed.budget || 0);
  // الدخل الإيجاري من نص الطلب («مؤجر ب 1200 شهرياً») — لحساب العائد في الوضع الثابت
  const requestIncome = clientExtractRentalIncome(text);
  const sourceScope = selectedBoardPlatforms();
  let rows = (boardState.allRecords || boardState.records || []).slice();

  if (area) rows = rows.filter((row) => {
    const rowArea = normalizeArabic(row.area);
    // لا تُطابق السجلات الخالية من المنطقة أي استعلام منطقة (تجنب تطابق «النص.includes(«)» الفارغ)
    return rowArea && (rowArea.includes(normalizeArabic(area)) || normalizeArabic(area).includes(rowArea));
  });
  if (propertyType) rows = rows.filter((row) => {
    const rowType = normalizeArabic(row.propertyType);
    return rowType && rowType.includes(normalizeArabic(propertyType));
  });
  if (transaction) rows = rows.filter((row) => {
    const rowTxn = normalizeArabic(row.transaction);
    return rowTxn && rowTxn.includes(normalizeArabic(transaction));
  });
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
    const isRentalRow = normalizeArabic(row.transaction).includes("إيجار");
    const annualRent = !isRentalRow && requestIncome && price ? (requestIncome.period === "monthly" ? requestIncome.amount * 12 : requestIncome.amount) : null;
    const rentalYieldPercent = annualRent && price ? Math.round(annualRent / price * 1000) / 10 : null;
    const rentalYieldVerdict = rentalYieldPercent != null ? (rentalYieldPercent >= 6 ? "قوي" : rentalYieldPercent >= 4 ? "متوسط" : "ضعيف") : "";
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
      phone: row.phone || "",
      annualRent,
      rentalYieldPercent,
      rentalYieldVerdict,
      summary: row.summary || row.features || "",
      features: row.features || "",
      recommendationScore: Math.round(score),
      matchScore: Math.round(priceScore || score),
      marketMedian: median,
      priceRatio: median && price ? price / median : null,
      priceGapPct: median && price ? Math.round((price / median - 1) * 1000) / 10 : null,
      priceGapLabel: median && price ? (price / median <= 0.92 ? "أرخص من السوق" : price / median >= 1.08 ? "أغلى من السوق" : "قريب من السوق") : null,
      valuationLabel: row.opportunityLabel || (score >= 75 ? "فرصة قوية" : score >= 60 ? "مناسبة" : "تحتاج مراجعة"),
      valuationReason: row.opportunityReason || "تقييم من أحدث بيانات السوق المنشورة: مطابقة الفلاتر، السعر، وجود المقارنات، ومصدر الإعلان.",
      decisionLine: "يعتمد التقييم على أحدث بيانات السوق المتاحة من جميع المصادر، وتُحدَّث يوميًا تلقائيًا.",
      reasons: [
        area ? `مطابق للمنطقة: ${area}` : "مطابق لنطاق البحث",
        propertyType ? `نوع العقار: ${propertyType}` : "نوع العقار من بيانات الإعلان",
        comps.length ? `يوجد ${comps.length} مقارنات من نفس النطاق` : "المقارنات المتاحة ضمن نطاق البحث الحالي",
      ],
      warnings: [],
      comparables: comps,
      numberSources: {
        price: { value: row.priceText || price, source: row.source, note: "من بيانات الإعلان" },
        space: { value: row.space || null, source: row.source, note: row.space ? "من بيانات الإعلان" : "غير مذكورة" },
        marketMedian: { value: median || null, source: "بيانات السوق المنشورة", note: `${priced.length} إعلان بسعر معلن` },
        comparablesCount: { value: comps.length, source: "بيانات السوق المنشورة", note: "نفس النطاق المتاح" },
        confidence: { value: Math.round(score), source: "التقييم الآلي", note: "السعر + الفلاتر + الأدلة المتاحة" },
      },
      matchBreakdown: [
        { name: "مطابقة الفلاتر", points: area || propertyType ? 40 : 20, value: "حسب المدخلات", weight: "40%" },
        { name: "السعر", points: Math.round(priceScore || 0), value: row.priceText || price || "غير معلن", weight: "35%" },
        { name: "الأدلة", points: comps.length * 10, value: `${comps.length} مقارنات`, weight: "25%" },
      ],
      recommendationBreakdown: [
        { name: "درجة الفرصة", points: Math.round(score), value: row.opportunityReason || "وفق بيانات السوق", weight: "100%" },
      ],
    };
  }).sort((a, b) => b.recommendationScore - a.recommendationScore).slice(0, 20);

  return {
    generatedAt: new Date().toLocaleString("ar-KW-u-nu-latn"),
    analysisMethod: "local",
    summary: results.length
      ? `تم تحليل ${results.length} نتيجة من أحدث بيانات السوق. أفضل نتيجة ${results[0].code} بدرجة ${results[0].recommendationScore}/100.`
      : "لا توجد نتائج مطابقة ضمن النطاق الحالي. جرّب توسيع المنطقة أو المنصة.",
    request: { rawText: text, areas: area ? [area] : [], propertyType, transaction },
    extractedFilters: [
      { label: "المنطقة", value: area, source: "الفلاتر" },
      { label: "نوع العقار", value: propertyType, source: "الفلاتر" },
      { label: "العملية", value: transaction, source: "الفلاتر" },
    ],
    searchScope: { note: "تحليل شامل لأحدث بيانات السوق المنشورة من جميع المصادر، تُحدَّث يوميًا تلقائيًا." },
    rankingMethod: {
      title: "ترتيب الفرص",
      description: "الترتيب حسب درجة الفرصة، مطابقة الفلاتر، السعر، وعدد المقارنات المتاحة في بيانات السوق.",
      weights: [
        { label: "مطابقة الطلب", value: "40%" },
        { label: "جاذبية السعر", value: "35%" },
        { label: "الأدلة", value: "25%" },
      ],
    },
    sourceStatus: [{ name: "بيانات السوق المنشورة", status: "success", records: rows.length }],
    similarExternal: (() => {
      // قسم «إعلانات مشابهة من المواقع الأخرى»: تُفضَّل المصادر غير الفريج إن وُجدت
      const nonLocal = results.filter((row) => normalizeArabic(row.source) !== normalizeArabic("الفريج"));
      const pool = nonLocal.length ? nonLocal : results;
      return { items: pool.slice(0, 6), sources: Array.from(new Set(pool.map((r) => r.source).filter(Boolean))) };
    })(),
    profitOpportunities: { items: [] },
    results,
    persistence: { status: "static" },
  };
}

async function postJson(path, payload) {
  if (STATIC_SNAPSHOT_MODE && path === "/api/analyze") return staticAnalyzeReport(payload);
  try {
    const response = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    return await readJsonResponse(response, path);
  } catch (err) {
    // أي مضيف بلا API (خادم ثابت محلي، رابط مضبوط غير متاح): التحليل يعمل داخل المتصفح على اللقطة
    if (path === "/api/analyze") return staticAnalyzeReport(payload);
    throw err;
  }
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
  resetSearchTabProgress();
  setTabCount("tabCountSearch", 0);
}

function filteredBoardRows() {
  let rows = boardState.records.filter((row) => rowMatchesBoardFilters(row));
  return rows;
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
        <small>اضغط لعرض الإعلانات</small>
      </button>
    `;
  }).join("");
}

function boardStatRows(rows, stat) {
  if (stat === "opportunities") return rows.filter((row) => Number(row.opportunityScore) > 0);
  if (stat === "scored") return rows.filter((row) => row.opportunityScore != null);
  if (stat === "evidence") return rows.filter((row) => Number(row.opportunityEvidenceCount || 0) > 0 || Number(row.opportunityComparablesCount || 0) > 0);
  if (stat === "priced") return rows.filter((row) => Number(row.price) > 0);
  if (stat === "withSpace") return rows.filter((row) => Number(row.space) > 0);
  if (stat === "direct") return rows.filter((row) => normalizeArabic(row.listingMode).includes("مباشر"));
  if (stat === "office") return rows.filter((row) => normalizeArabic(row.listingMode).includes("مكتب"));
  return rows;
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
    ["إجمالي الاختيار", rows.length, "total"],
    ["فرص ظاهرة", opportunities, "opportunities"],
    ["دخلت التقييم", totalScored, "scored"],
    ["أدلة ومقارنات", evidence, "evidence"],
    ["أسعار معلنة", priced, "priced"],
    ["مساحات موثقة", withSpace, "withSpace"],
    ["مباشر", direct, "direct"],
    ["مكتب", office, "office"],
  ].map(([label, value, stat]) => `
    <button class="board-stat${Number(value) ? "" : " empty"}" type="button" data-board-stat="${escapeHtml(stat)}" title="اضغط لعرض الإعلانات الفعلية خلف هذا الرقم">
      <span>${escapeHtml(label)}</span>
      <strong>${Number(value).toLocaleString("en-US")}</strong>
      <small>عرض الإعلانات ←</small>
    </button>
  `).join("");
}

function renderCompanionAds(rows) {
  const root = $("boardCompanionAds");
  if (!root) return;
  const all = rows
    .filter((row) => row.code || row.summary || row.originalUrl)
    .sort((a, b) => (Number(b.opportunityScore || 0) - Number(a.opportunityScore || 0)) || String(b.publishedDate || "").localeCompare(String(a.publishedDate || "")));
  const items = all.slice(0, 8);
  if (!items.length) {
    root.innerHTML = '<div class="empty compact-empty">لا توجد إعلانات مرافقة حسب الاختيارات الحالية.</div>';
    return;
  }
  root.innerHTML = items.map((item) => `
    <article class="companion-ad" data-board-listing>
      <div class="companion-head">
        <strong>${escapeHtml(item.code || "إعلان")}</strong>
        <button type="button" class="source-badge" data-board-source="${escapeHtml(item.source || "مصدر غير محدد")}" title="عرض كل إعلانات هذا المصدر">${escapeHtml(item.source || "مصدر غير محدد")}</button>
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
        ${item.phone ? `<a class="wa-contact" href="${escapeHtml(waLink(item.phone))}?text=${encodeURIComponent(`السلام عليكم، أستفسر عن الإعلان: ${item.code || ""} (${item.area || ""}) ${item.priceText || ""} — وجدته عبر منصة الفريج العقارية`)}" target="_blank" rel="noreferrer">تواصل واتساب</a>` : ""}
      </div>
      <span class="card-detail-hint">اضغط البطاقة للتفاصيل الكاملة ←</span>
    </article>
  `).join("");
  root.querySelectorAll("[data-board-listing]").forEach((el, index) => {
    el._row = items[index];
  });
}

// بطاقة ملخص «فرص الربط» في اللوحة — البيانات الكاملة تعيش في تبويب «العرض والطلب» داخل أفضل الفرص،
// وهذه البطاقة تلخصها فقط مع زر تنقّل ذكي يفتح التبويب في نفس الصفحة.
function renderBoardMatchingLink(rows) {
  const root = $("boardMatchingLink");
  if (!root) return;
  const data = boardState.matching;
  if (!data) {
    root.innerHTML = '<div class="empty compact-empty">جاري تحميل ملخص العرض والطلب...</div>';
    return;
  }
  const byKind = data.byKind || {};
  const stats = [
    { label: "طلبات شراء", value: byKind.buy || 0 },
    { label: "طلبات إيجار", value: byKind.rent || 0 },
    { label: "طلبات لها فرص مطابقة", value: data.matchedDemandCount || 0 },
    { label: "فرص متاحة مقيّمة", value: data.supplyCount || 0 },
  ];
  root.innerHTML = `
    <div class="section-title compact-title companion-title">
      <h3>فرص الربط والعرض والطلب</h3>
      <span>البيانات الكاملة لكل طلب وفرصه المطابقة بتقييمها ومصادرها في تبويب «العرض والطلب» — هذه بطاقة ملخص فقط.</span>
    </div>
    <article class="matching-nav-card">
      <div class="matching-nav-stats">${stats.map((s) => `
        <div class="matching-nav-stat">
          <b>${s.value}</b>
          <span>${escapeHtml(s.label)}</span>
        </div>`).join("")}
      </div>
      <button type="button" id="openMatchingTabBtn" class="primary matching-nav-btn">${DEV_SVG('<path d="M5 12h14"/><path d="M13 5l7 7-7 7"/>')} فتح تفاصيل العرض والطلب</button>
    </article>`;
  const btn = $("openMatchingTabBtn");
  if (btn && !btn.dataset.bound) {
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => goToMatchingTab());
  }
}

// تنقّل ذكي: لوحة السوق ← أفضل الفرص ← تبويب «العرض والطلب» (يحتفظ بفلتر المصدر المحدد في اللوحة)
function goToMatchingTab() {
  switchMainTab("opportunities");
  const tabs = document.querySelectorAll(".opp-tab");
  tabs.forEach((t) => t.classList.toggle("active", t.dataset.tier === "matching"));
  oppState.tier = "matching";
  loadOpportunityTab("matching");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function metricCells(rows, governorate = "", area = "") {
  const scope = rows.filter((row) => {
    const rowGov = canonicalGovernorate(row.governorate) || "غير محددة";
    const targetGov = canonicalGovernorate(governorate) || "غير محددة";
    if (governorate && rowGov !== targetGov) return false;
    if (area && normalizeArabic(row.area) !== normalizeArabic(area)) return false;
    return true;
  });
  return ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"].map((metric) => ({
    metric,
    count: countMetric(scope, metric),
  }));
}

function renderGovernorateCards(rows) {
  const root = $("governorateCards");
  if (!root) return;
  const governorates = uniqueValues(rows.map((row) => canonicalGovernorate(row.governorate) || "غير محددة"));
  const activeMetric = boardState.activeMetric || "movement";
  const axisPill = $("govAxisPill");
  if (axisPill) axisPill.textContent = `المحور: ${boardMetricLabels[activeMetric] || "حركة الدلال"}`;
  if (!governorates.length) {
    root.innerHTML = '<div class="gov-empty">لا توجد بيانات حسب الفلاتر الحالية.</div>';
    return;
  }
  const metrics = ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"];
  const totals = metrics.map((metric) => ({ metric, count: countMetric(rows, metric) }));
  const metricPill = (cell, extraCls) => `
    <button class="metric-pill${extraCls}" type="button" data-board-gov="${escapeHtml(cell.gov)}" ${cell.area ? `data-board-area-run="${escapeHtml(cell.area)}"` : ""} data-board-metric-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"} title="${escapeHtml(boardMetricLabels[cell.metric] || "")}">
      <span>${escapeHtml(boardMetricLabels[cell.metric] || "")}</span>
      <b>${cell.count.toLocaleString("en-US")}</b>
    </button>`;
  const html = [];
  for (const governorate of governorates) {
    const govRows = rows.filter((row) => (canonicalGovernorate(row.governorate) || "غير محددة") === governorate);
    const cells = metricCells(rows, governorate);
    const expanded = boardState.expandedGovernorates.has(governorate);
    const sel = boardState.selectedCell;
    const areaCount = uniqueValues(govRows.map((row) => row.area).filter(Boolean)).length;
    const axisCell = cells.find((c) => c.metric === activeMetric) || cells[0] || { metric: "movement", count: 0 };
    html.push(`
      <section class="gov-card${expanded ? " expanded" : ""}" data-board-governorate="${escapeHtml(governorate)}">
        <header class="gov-card-head">
          <button class="gov-toggle" type="button" data-board-toggle-gov="${escapeHtml(governorate)}" aria-label="${expanded ? "طي" : "فتح"} مناطق ${escapeHtml(governorate)}">${expanded ? "▲" : "▼"}</button>
          <strong class="gov-card-name">${escapeHtml(governorate)}</strong>
          <button class="gov-areas-badge" type="button" data-board-toggle-gov="${escapeHtml(governorate)}" title="${areaCount} منطقة — ${govRows.length} إعلان">
            <b>${areaCount}</b>
            <b>${govRows.length.toLocaleString("en-US")}</b>
            <small>مناطق</small>
          </button>
          <button class="count-button gov-axis-total${activeMetric ? " axis" : ""}" type="button" data-board-gov="${escapeHtml(governorate)}" data-board-metric-run="${escapeHtml(activeMetric)}" ${axisCell.count ? "" : "disabled"} title="المحور: ${escapeHtml(boardMetricLabels[activeMetric] || "")}">${axisCell.count.toLocaleString("en-US")}</button>
        </header>
        <div class="gov-card-metrics">
          ${cells.map((cell) => metricPill({ ...cell, gov: governorate }, `${activeMetric === cell.metric ? " axis" : ""}${sel && sel.governorate === governorate && !sel.area && sel.metric === cell.metric ? " selected" : ""}`)).join("")}
        </div>
        ${expanded ? renderGovAreaCards(rows, governorate, govRows, sel, activeMetric, metricPill) : ""}
      </section>
    `);
  }
  // كارت الإجمالي
  html.push(`
    <section class="gov-card gov-total-card">
      <header class="gov-card-head">
        <strong class="gov-card-name">الإجمالي</strong>
        <button class="count-button gov-axis-total${activeMetric ? " axis" : ""}" type="button" data-board-total-run="${escapeHtml(activeMetric)}" ${(totals.find((t) => t.metric === activeMetric) || { count: 0 }).count ? "" : "disabled"}>${(totals.find((t) => t.metric === activeMetric) || { count: 0 }).count.toLocaleString("en-US")}</button>
      </header>
      <div class="gov-card-metrics">
        ${totals.map((cell) => `<button class="metric-pill total-count${activeMetric === cell.metric ? " axis" : ""}" type="button" data-board-total-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"} title="${escapeHtml(boardMetricLabels[cell.metric] || "")}"><span>${escapeHtml(boardMetricLabels[cell.metric] || "")}</span><b>${cell.count.toLocaleString("en-US")}</b></button>`).join("")}
      </div>
    </section>
  `);
  root.innerHTML = html.join("");
}

function renderGovAreaCards(rows, governorate, govRows, sel, activeMetric, metricPill) {
  const areaGroups = {};
  for (const row of govRows) {
    if (!row.area) continue;
    const key = normalizeArabic(row.area);
    if (!(key in areaGroups)) areaGroups[key] = row.area;
  }
  return `
    <div class="gov-card-areas">
      ${Object.values(areaGroups).sort((a, b) => String(a).localeCompare(String(b), "ar")).map((area) => {
        const areaCells = metricCells(rows, governorate, area);
        return `
          <div class="area-card" data-board-area="${escapeHtml(area)}">
            <span class="area-name">${escapeHtml(area)}</span>
            <div class="area-pills">
              ${areaCells.map((cell) => metricPill({ ...cell, gov: governorate, area }, `${activeMetric === cell.metric ? " axis" : ""}${sel && sel.governorate === governorate && sel.area === area && sel.metric === cell.metric ? " selected" : ""}`)).join("")}
            </div>
          </div>`;
      }).join("")}
    </div>`;
}

// ─── درج التفاصيل: أي رقم في اللوحة يفتح الإعلانات الفعلية خلفه بالأدلة والمصادر ───
let boardDrilldown = null; // { rows, run }

function openBoardDrilldown({ title, sub, rows, run }) {
  boardDrilldown = { rows: rows || [], run: run || {} };
  const overlay = $("boardDrilldown");
  if (!overlay) return;
  const titleEl = $("drillTitle");
  const subEl = $("drillSub");
  if (titleEl) titleEl.textContent = title || "التفاصيل";
  if (subEl) subEl.textContent = sub || "";
  renderDrillRows(boardDrilldown.rows);
  overlay.hidden = false;
  document.body.classList.add("drill-open");
  const closeBtn = overlay.querySelector("[data-drill-close]");
  if (closeBtn) closeBtn.focus();
}

function closeBoardDrilldown() {
  const overlay = $("boardDrilldown");
  if (!overlay) return;
  overlay.hidden = true;
  document.body.classList.remove("drill-open");
  boardDrilldown = null;
}

// ─── بوكس تفاصيل الإعلان: أي بطاقة إعلان في اللوحة تفتح تفاصيلها داخل نفس الصفحة ───
// يحمل كل عنصر [data-board-listing] بيانات صفه كاملًا في `_row` (لا بحث ولا حالة عامة)،
// والنقر على جسم البطاقة (لا على أزرارها الداخلية) يفتح التفاصيل الكاملة.
let listingDetails = null;

function openListingDetails(item) {
  const overlay = $("boardListingModal");
  if (!overlay) return;
  const titleEl = $("listingTitle");
  const subEl = $("listingSub");
  if (titleEl) titleEl.textContent = (item && item.code) ? String(item.code) : "تفاصيل الإعلان";
  if (subEl) subEl.textContent = item ? [item.area, item.propertyType].filter(Boolean).join(" · ") : "";
  renderListingDetails(item);
  overlay.hidden = false;
  document.body.classList.add("drill-open");
  const closeBtn = overlay.querySelector("[data-listing-close]");
  if (closeBtn) closeBtn.focus();
}

function closeListingDetails() {
  const overlay = $("boardListingModal");
  if (!overlay) return;
  overlay.hidden = true;
  document.body.classList.remove("drill-open");
  listingDetails = null;
}

function renderListingDetails(item) {
  const body = $("listingBody");
  if (!body) return;
  listingDetails = item || null;
  if (!item) {
    body.innerHTML = '<div class="empty">تعذر تحميل تفاصيل الإعلان.</div>';
    return;
  }
  const score = Number(item.opportunityScore) > 0 ? Math.round(Number(item.opportunityScore)) : null;
  const tx = item.transaction || "";
  const facts = [
    ["السعر", item.priceText || (item.price ? formatMoney(item.price) : "غير معلن")],
    ["المساحة", item.space ? `${item.space} م²` : "غير مذكورة"],
    ["نوع العقار", item.propertyType || "غير محدد"],
    ["المحافظة", item.governorate || "غير محددة"],
    ["المنطقة", item.area || "غير محددة"],
    ["نمط الإدراج", item.listingMode || "غير محدد"],
    ["تاريخ الإعلان", item.publishedDate || "غير متاح"],
    ["رمز الإعلان", item.code || "—"],
  ];
  const sections = [];
  if (item.summary || item.features) {
    sections.push(`
      <section class="listing-section">
        <h5>الوصف</h5>
        ${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}
        ${item.features ? `<p class="listing-features">${escapeHtml(item.features)}</p>` : ""}
      </section>`);
  }
  if (item.opportunityReason) {
    sections.push(`
      <section class="listing-section">
        <h5>سبب الفرصة</h5>
        <p>${escapeHtml(item.opportunityReason)}</p>
      </section>`);
  }
  const evidence = [];
  if (Number(item.opportunityComparablesCount) > 0) evidence.push(`${item.opportunityComparablesCount} مقارنة`);
  if (Number(item.opportunityEvidenceCount) > 0) evidence.push(`${item.opportunityEvidenceCount} دليل`);
  if (Number(item.opportunityClientsCount) > 0) evidence.push(`${item.opportunityClientsCount} عميل مطابق`);
  body.innerHTML = `
    <div class="listing-hero">
      ${score ? `<span class="drill-score">فرصة ${score} / 100</span>` : ""}
      ${tx ? `<span class="drill-tx">${escapeHtml(tx)}</span>` : ""}
      <button type="button" class="source-badge" data-board-source="${escapeHtml(item.source || "")}" title="عرض كل إعلانات هذا المصدر">${escapeHtml(item.source || "مصدر غير محدد")}</button>
    </div>
    <h3 class="listing-title">${escapeHtml([item.area, item.propertyType].filter(Boolean).join(" - ") || "عقار")}</h3>
    <div class="listing-facts">
      ${facts.map(([label, value]) => `<div><b>${escapeHtml(label)}</b><span>${escapeHtml(String(value))}</span></div>`).join("")}
    </div>
    ${evidence.length ? `<div class="listing-evidence">${evidence.map((e) => `<span>${escapeHtml(e)}</span>`).join("")}</div>` : ""}
    ${sections.join("")}
    <div class="listing-actions">
      ${item.originalUrl ? `<a class="primary" href="${escapeHtml(item.originalUrl)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي</a>` : ""}
      ${item.phone ? `<a class="wa-contact" href="${escapeHtml(waLink(item.phone))}?text=${encodeURIComponent(`السلام عليكم، أستفسر عن الإعلان: ${item.code || ""} (${item.area || ""}) ${item.priceText || ""} — وجدته عبر منصة الفريج العقارية`)}" target="_blank" rel="noreferrer">تواصل واتساب</a>` : ""}
      ${item.area ? `<button type="button" data-listing-similar="${escapeHtml(item.area)}|${escapeHtml(item.propertyType || "")}">عرض مشابهات في اللوحة</button>` : ""}
    </div>`;
}

// كل إعلانات مصدر واحد ضمن فلاتر اللوحة الحالية — بدل صندوق الإعلان، افتح درجًا مركّزًا
function openSourceDrilldown(sourceName) {
  const source = String(sourceName || "").trim();
  if (!source) return;
  closeListingDetails();
  closeBoardDrilldown();
  const rows = boardState.records.filter((row) => rowMatchesBoardFilters(row) && (row.source || "").trim() === source);
  openBoardDrilldown({
    title: `كل إعلانات ${source}`,
    sub: `${rows.length} إعلان من هذا المصدر ضمن فلاتر اللوحة الحالية — كل إعلان يحمل رابطه وأدلته.`,
    rows,
    run: boardDrillRunFromFilters(),
  });
}

// مسح اختيارات اللوحة كاملًا: كل الفلاتر + المحور + الخلية المحددة + المحافظات المفتوحة
function clearBoardSelections() {
  const resetFields = [
    ["boardMetricFilter", "movement"],
    ["boardGovernorateFilter", ""],
    ["boardTransactionFilter", ""],
    ["boardPropertyTypeFilter", ""],
    ["boardListingModeFilter", ""],
    ["boardAreaFilter", ""],
  ];
  for (const [id, fallback] of resetFields) {
    const el = $(id);
    if (!el) continue;
    el.value = fallback;
  }
  const platformInputs = [...document.querySelectorAll('input[name="boardPlatform"]')];
  if (platformInputs.length) {
    for (const input of platformInputs) input.checked = input.value === "__all";
  }
  boardState.activeMetric = "movement";
  boardState.selectedCell = null;
  if (boardState.expandedGovernorates && boardState.expandedGovernorates.clear) boardState.expandedGovernorates.clear();
  closeBoardDrilldown();
  closeListingDetails();
  loadDashboardBoard();
}

function renderDrillRows(rows) {
  const body = $("drillBody");
  if (!body) return;
  if (!rows || !rows.length) {
    body.innerHTML = '<div class="empty">لا توجد إعلانات ضمن هذا النطاق.</div>';
    return;
  }
  const visible = rows.slice(0, 80);
  body.innerHTML = visible.map((item) => {
    const score = Number(item.opportunityScore) > 0 ? Math.round(Number(item.opportunityScore)) : null;
    const tx = item.transaction || "";
    const txBadge = tx ? `<span class="drill-tx">${escapeHtml(tx)}</span>` : "";
    const sourceLabel = item.source || "مصدر غير محدد";
    return `
      <article class="drill-card" data-board-listing>
        <div class="drill-head">
          <strong>${escapeHtml(item.code || "إعلان")}</strong>
          ${score ? `<span class="drill-score">فرصة ${score} / 100</span>` : ""}
          ${txBadge}
        </div>
        <h5>${escapeHtml([item.area, item.propertyType].filter(Boolean).join(" - ") || "عقار")}</h5>
        <div class="drill-facts">
          <span><b>السعر</b>${escapeHtml(item.priceText || (item.price ? formatMoney(item.price) : "غير معلن"))}</span>
          <span><b>المساحة</b>${item.space ? `${escapeHtml(item.space)} م²` : "غير مذكورة"}</span>
          <span><b>المصدر</b><button type="button" class="source-badge" data-board-source="${escapeHtml(sourceLabel)}">${escapeHtml(sourceLabel)}</button></span>
        </div>
        ${item.opportunityReason ? `<p class="drill-reason">${escapeHtml(item.opportunityReason)}</p>` : ""}
        <div class="drill-evidence">
          ${Number(item.opportunityComparablesCount) > 0 ? `<span>${escapeHtml(item.opportunityComparablesCount)} مقارنة</span>` : ""}
          ${Number(item.opportunityEvidenceCount) > 0 ? `<span>${escapeHtml(item.opportunityEvidenceCount)} دليل</span>` : ""}
          ${Number(item.opportunityClientsCount) > 0 ? `<span>${escapeHtml(item.opportunityClientsCount)} عميل مطابق</span>` : ""}
        </div>
        <div class="drill-actions">
          ${item.originalUrl ? `<a href="${escapeHtml(item.originalUrl)}" target="_blank" rel="noreferrer">فتح على ${escapeHtml(sourceLabel)}</a>` : ""}
          ${item.phone ? `<a class="wa-contact" href="${escapeHtml(waLink(item.phone))}?text=${encodeURIComponent(`السلام عليكم، أستفسر عن الإعلان: ${item.code || ""} (${item.area || ""}) ${item.priceText || ""} — وجدته عبر منصة الفريج العقارية`)}" target="_blank" rel="noreferrer">تواصل واتساب</a>` : ""}
          <span class="card-detail-hint">اضغط البطاقة للتفاصيل الكاملة ←</span>
        </div>
      </article>
    `;
  }).join("");
  body.querySelectorAll("[data-board-listing]").forEach((el, index) => {
    el._row = visible[index];
  });
  if (rows.length > visible.length) {
    const more = document.createElement("div");
    more.className = "empty compact-empty";
    more.textContent = `و ${rows.length - visible.length} إعلان آخر بنفس النطاق — اضبط الفلاتر للتركيز أكثر.`;
    body.appendChild(more);
  }
}

// ─── تحليلات السوق (الموجة 1): عائد الإيجار + اتجاه سعر المتر لكل منطقة ───
const insightsState = { data: null, loaded: false };

function formatKd(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!isFinite(n)) return "—";
  if (n >= 1000000) return `${(n / 1000000).toLocaleString("ar-KW-u-nu-latn", { maximumFractionDigits: 1 })} مليون`;
  if (n >= 1000) return `${(n / 1000).toLocaleString("ar-KW-u-nu-latn", { maximumFractionDigits: 1 })} ألف`;
  return n.toLocaleString("ar-KW-u-nu-latn", { maximumFractionDigits: 0 });
}

function renderInsights() {
  const root = $("insightsRoot");
  if (!root) return;
  const data = insightsState.data;
  const meta = $("insightsMeta");
  // الخريطة الحرارية في أعلى التبويب — نفس الخلايا القابلة للنقر (تعمل حتى قبل بقية التحليلات)
  renderInsightsHeatmap(data);
  if (!data || !data.tableOk) {
    if (meta) meta.textContent = "";
    root.innerHTML = `<div class="empty">لا توجد بيانات تحليلات بعد — شغّل الوكيل اليومي لتراكم حصاد المواقع في market_listings.</div>`;
    return;
  }
  const areas = data.areas || [];
  const withYield = areas.filter((a) => a.rentalYield != null);
  const priced = areas.filter((a) => a.medianSalePerM2 != null);
  const samples = data.sampleTotals || {};
  const fetched = data.fetchedAt ? String(data.fetchedAt).replace("T", " ").slice(0, 16) : "";
  if (meta) meta.textContent = `آخر تحديث: ${fetched} · ${areas.length} منطقة · ${samples.sale || 0} بيع + ${samples.rent || 0} إيجار · ${samples.buyRequests || 0} طلب شراء + ${samples.rentRequests || 0} طلب إيجار · ${withYield.length} بعائد محسوب`;

  // 0) بطاقات المؤشرات الرئيسية (KPI)
  const market = data.market || {};
  const dirClass = market.direction === "صاعد" ? "kpi-up" : market.direction === "هابط" ? "kpi-down" : "kpi-flat";
  const kpis = `
    <div class="insight-kpis">
      <div class="kpi-card"><span class="kpi-label">مناطق محللة</span><strong>${areas.length}</strong><small>من الحصاد المتراكم</small></div>
      <div class="kpi-card"><span class="kpi-label">عينات بيع</span><strong>${samples.sale || 0}</strong><small>إعلان بيع</small></div>
      <div class="kpi-card"><span class="kpi-label">عينات إيجار</span><strong>${samples.rent || 0}</strong><small>إعلان إيجار</small></div>
      <div class="kpi-card kpi-demand"><span class="kpi-label">طلبات شراء</span><strong>${samples.buyRequests || 0}</strong><small>مطلوب للشراء — من الفريج المحلي</small></div>
      <div class="kpi-card kpi-demand"><span class="kpi-label">طلبات إيجار</span><strong>${samples.rentRequests || 0}</strong><small>مطلوب للإيجار — من الفريج المحلي</small></div>
      <div class="kpi-card"><span class="kpi-label">عائد محسوب</span><strong>${withYield.length}</strong><small>منطقة بيع + إيجار معًا</small></div>
      <div class="kpi-card"><span class="kpi-label">اتجاه السوق</span><strong class="${dirClass}">${escapeHtml(market.direction || "—")}</strong><small>${market.changePct != null ? `${market.changePct > 0 ? "+" : ""}${market.changePct}% سعر المتر العام` : "يُبنى مع تراكم الأشهر"}</small></div>
    </div>`;

  // 1) عائد الإيجار — أشرطة أفقية مع شارة موثوقية (أعلى المناطق أولًا)
  const maxYield = Math.max(...withYield.slice(0, 8).map((a) => Number(a.rentalYield) || 0), 1);
  const yieldRows = withYield.slice(0, 8).map((a) => {
    const pct = Number(a.rentalYield) || 0;
    const tier = pct >= 6 ? "yield-high" : pct >= 4 ? "yield-mid" : "yield-low";
    const reliable = a.yieldNote === "high";
    return `
      <div class="yield-row">
        <div class="yield-row-head">
          <span class="yield-area">${escapeHtml(a.area)}<small>${escapeHtml(a.governorate || "")}</small></span>
          <span class="yield-badges">${reliable ? '<i class="rel-badge rel-high">ثقة عالية</i>' : '<i class="rel-badge rel-low">تقديري</i>'}<b class="yield-val ${tier}">${pct.toLocaleString("ar-KW-u-nu-latn", { maximumFractionDigits: 1 })}%</b></span>
        </div>
        <div class="yield-bar"><i class="yield-bar-fill ${tier}" style="width:${((pct / maxYield) * 100).toFixed(1)}%"></i></div>
        <div class="yield-row-meta">بيع ${formatKd(a.medianSalePrice)} <small>(${a.saleCount})</small> · إيجار ${formatKd(a.medianRent)}/شهر <small>(${a.rentCount})</small>${a.medianSalePerM2 != null ? ` · سعر المتر ${formatKd(a.medianSalePerM2)}` : ""}${a.outliersRemoved ? ` · استُبعد ${a.outliersRemoved} قيمة شاذة` : ""}</div>
      </div>`;
  }).join("");

  // 2) سعر المتر حسب المحافظات — أشرطة أفقية
  const govs = data.governorates || [];
  const govMax = Math.max(...govs.map((g) => g.medianSalePerM2 || 0), 1);
  const govRows = govs.map((g) => `
    <div class="gov-row">
      <span class="gov-name">${escapeHtml(g.governorate)}</span>
      <div class="gov-bar"><i style="width:${(((g.medianSalePerM2 || 0) / govMax) * 100).toFixed(1)}%"></i></div>
      <b class="gov-val">${formatKd(g.medianSalePerM2)} د.ك/م²</b>
    </div>`).join("") || '<div class="empty">لا توجد محافظات ببيانات سعر متر بعد.</div>';

  // 3) الرسم الزمني لسعر المتر (سلسلة market-insights) — يسقط لبيانات price_trends الأعمق
  let trendHtml = "";
  if (data.series && data.series.length >= 2) {
    trendHtml = renderInsightsTrendSvg(data);
  } else if (oppState.priceTrends && oppState.priceTrends.rows && oppState.priceTrends.rows.length) {
    trendHtml = renderPriceTrendsChart(root, true);
  } else {
    trendHtml = '<div class="empty">سلسلة سعر المتر تُبنى مع تراكم الأشهر — عدّ بعد التحديث اليومي التالي.</div>';
  }

  // 4) مصادر هذا التحليل — أي المواقع غذّت الأرقام وبكم
  const sources = data.sources || [];
  const srcMax = Math.max(...sources.map((s) => s.count), 1);
  const srcRows = sources.slice(0, 10).map((s) => `
    <div class="src-row">
      <span class="src-name">${escapeHtml(s.source)}</span>
      <div class="src-bar"><i style="width:${((s.count / srcMax) * 100).toFixed(1)}%"></i></div>
      <b class="src-count">${s.count}</b>
      <small class="src-share">${s.sharePct}%</small>
    </div>`).join("");

  const demandHtml = renderDemandIndicators(insightsState.demand);
  root.innerHTML = `
    ${kpis}
    <p class="scope-note insights-note">${escapeHtml(data.note || "")}</p>
    <div class="insights-section">
      <div class="section-title compact-title">
        <h3>مؤشرات الطلب</h3>
        <span>طلبات الشراء والإيجار من إعلانات «مطلوب» المحلية والخارجية (مثل قسم «مطلوب» في 4Sale) — عدّ لكل منطقة ومحافظة ومنصة مع الاتجاه الشهري. كل طلب عميل محتمل، وميزانيته لا تدخل وسيطات أسعار العرض.</span>
      </div>
      ${demandHtml}
    </div>
    <div class="insights-section">
      <div class="section-title compact-title">
        <h3>أعلى عائد إيجار</h3>
        <span>العائد السنوي = (وسيط الإيجار × 12) ÷ وسيط سعر البيع — بعد استبعاد القيم الشاذة واشتراط عينتين على الأقل لكل جانب.</span>
      </div>
      ${withYield.length ? `<div class="yield-list">${yieldRows}</div>` : '<div class="empty">لا توجد مناطق بمقارنة بيع/إيجار موثوقة بعد.</div>'}
    </div>
    <div class="insights-section">
      <div class="section-title compact-title">
        <h3>وسيط سعر المتر حسب المحافظات</h3>
        <span>من إعلانات البيع المحصودة (حيثما وُجدت المساحة) بعد التنظيف من الشواذ.</span>
      </div>
      <div class="gov-list">${govRows}</div>
    </div>
    <div class="insights-section">
      <div class="section-title compact-title">
        <h3>اتجاه سعر المتر عبر الأشهر</h3>
        <span>سعر المتر (د.ك/م²) لكل منطقة عبر الزمن من الحصاد المتراكم — الخط المتقطع هو وسيط السوق العام.</span>
      </div>
      ${trendHtml}
    </div>
    <div class="insights-section">
      <div class="section-title compact-title">
        <h3>مصادر بيانات هذا التحليل</h3>
        <span>كل رقم أعلاه مبني على الحصاد المتراكم من هذه المنصات — كل إعلان يحمل رابطه الأصلي في لوحة السوق.</span>
      </div>
      ${sources.length ? `<div class="src-list">${srcRows}</div>` : '<div class="empty">لا توجد بيانات مصادر بعد.</div>'}
    </div>
  `;
  setTabCount("tabCountInsights", withYield.length || priced.length);
}

function renderDemandIndicators(data) {
  if (!data || !data.tableOk) {
    return '<div class="empty">لا توجد طلبات شراء/إيجار محلية بعد — تظهر طلبات الفريج («مطلوب للشراء/للإيجار») عند توفرها.</div>';
  }
  const totals = data.totals || {};
  const chips = `
    <div class="insight-kpis">
      <div class="kpi-card kpi-demand"><span class="kpi-label">إجمالي الطلبات</span><strong>${totals.total || 0}</strong><small>شراء + إيجار معًا</small></div>
      <div class="kpi-card kpi-demand"><span class="kpi-label">طلبات شراء</span><strong>${totals.buyRequests || 0}</strong><small>أشخاص يبحثون عن شراء</small></div>
      <div class="kpi-card kpi-demand"><span class="kpi-label">طلبات إيجار</span><strong>${totals.rentRequests || 0}</strong><small>أشخاص يبحثون عن إيجار</small></div>
    </div>
    <p class="demand-clarify">طلبات «مطلوب للشراء/للإيجار» منشورة في الفريج وفي قسم «مطلوب عقار» في 4Sale — بقية المنصات الخارجية تنشر عروضًا فقط. التوزيع حسب المنصة أدناه يوضح مصدر كل طلب بشفافية.</p>`;
  const areas = (data.areas || []).slice(0, 15);
  const areaTable = areas.length ? `
    <div style="overflow-x:auto">
      <table class="minitable">
        <thead><tr><th>المنطقة</th><th>المحافظة</th><th>طلبات شراء</th><th>طلبات إيجار</th><th>الإجمالي</th></tr></thead>
        <tbody>${areas.map((a) => `<tr>
          <td>${escapeHtml(a.area)}</td>
          <td>${escapeHtml(a.governorate)}</td>
          <td>${a.buy || 0}</td>
          <td>${a.rent || 0}</td>
          <td><b>${a.total || 0}</b></td>
        </tr>`).join("")}</tbody>
      </table>
    </div>` : '<div class="empty">لا توجد مناطق بطلبات بعد.</div>';
  const govs = data.governorates || [];
  const govMax = Math.max(...govs.map((g) => g.total || 0), 1);
  const govRows = govs.slice(0, 8).map((g) => `
    <div class="gov-row">
      <span class="gov-name">${escapeHtml(g.governorate)}</span>
      <div class="gov-bar"><i style="width:${(((g.total || 0) / govMax) * 100).toFixed(1)}%"></i></div>
      <b class="gov-val">${g.buy || 0} ش / ${g.rent || 0} إج</b>
    </div>`).join("") || '<div class="empty">لا توجد محافظات بطلبات بعد.</div>';
  const platforms = data.platforms || [];
  const platMax = Math.max(...platforms.map((p) => p.total || 0), 1);
  const platformRows = platforms.map((p) => `
    <div class="gov-row">
      <span class="gov-name">${escapeHtml(p.source)}</span>
      <div class="gov-bar"><i style="width:${(((p.total || 0) / platMax) * 100).toFixed(1)}%"></i></div>
      <b class="gov-val">${p.buy || 0} ش / ${p.rent || 0} إج</b>
      <small class="gov-share">${p.total || 0} · ${p.sharePct || 0}%</small>
    </div>`).join("") || '<div class="empty">لا توجد منصات بطلبات بعد.</div>';
  return `${chips}
    <div class="demand-trend-block">
      <h4 class="demand-subhead">اتجاه الطلب شهريًا</h4>
      ${renderDemandTrendSvg(data.series || [])}
    </div>
    <div class="demand-cols">
      <div>
        <h4 class="demand-subhead">أعلى مناطق طلبًا</h4>
        ${areaTable}
      </div>
      <div>
        <h4 class="demand-subhead">حسب المحافظة</h4>
        <div class="gov-list">${govRows}</div>
      </div>
      <div>
        <h4 class="demand-subhead">توزيع الطلبات حسب المنصة</h4>
        <div class="gov-list">${platformRows}</div>
      </div>
    </div>`;
}

function renderDemandTrendSvg(series) {
  if (!series.length) return '<div class="empty">الاتجاه يُبنى مع تراكم الأشهر — عدّ بعد التحديث التالي.</div>';
  const width = 760;
  const height = 200;
  const padL = 40;
  const padR = 12;
  const padT = 12;
  const padB = 26;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const maxV = Math.max(...series.flatMap((s) => [s.buy, s.rent]), 1);
  const slot = innerW / series.length;
  const barW = Math.min(26, slot * 0.32);
  const yFor = (v) => padT + innerH - (v / maxV) * innerH;
  const grid = [];
  for (let t = 0; t <= 4; t++) {
    const v = Math.round((maxV * t) / 4);
    const y = yFor(v);
    grid.push(`<line x1="${padL}" y1="${y.toFixed(1)}" x2="${width - padR}" y2="${y.toFixed(1)}" class="grid-line"/>`);
    grid.push(`<text x="${padL - 8}" y="${(y + 3).toFixed(1)}" text-anchor="end" class="axis-label">${v}</text>`);
  }
  const bars = series.map((s, i) => {
    const cx = padL + slot * i + slot / 2;
    const buyH = (s.buy / maxV) * innerH;
    const rentH = (s.rent / maxV) * innerH;
    return `
      <rect x="${(cx - barW - 1.5).toFixed(1)}" y="${yFor(s.buy).toFixed(1)}" width="${barW}" height="${Math.max(buyH, 1).toFixed(1)}" rx="3" fill="#e2c968"><title>${escapeHtml(s.month)} · طلبات شراء: ${s.buy}</title></rect>
      <rect x="${(cx + 1.5).toFixed(1)}" y="${yFor(s.rent).toFixed(1)}" width="${barW}" height="${Math.max(rentH, 1).toFixed(1)}" rx="3" fill="#2b6cb0"><title>${escapeHtml(s.month)} · طلبات إيجار: ${s.rent}</title></rect>`;
  }).join("");
  const labels = series.map((s, i) => `<text x="${(padL + slot * i + slot / 2).toFixed(1)}" y="${height - 6}" text-anchor="middle" class="hist-date">${escapeHtml(s.month.slice(5))}</text>`).join("");
  return `
    <div class="trends-block">
      <div class="hist-chart">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="اتجاه طلبات الشراء والإيجار عبر الأشهر">
          ${grid.join("")}${bars}${labels}
        </svg>
      </div>
      <div class="hist-legend">
        <span class="hist-legend-item"><i style="background:#e2c968"></i>طلبات شراء</span>
        <span class="hist-legend-item"><i style="background:#2b6cb0"></i>طلبات إيجار</span>
      </div>
    </div>`;
}

function renderInsightsTrendSvg(data) {
  const months = data.months || [];
  const series = (data.series || []).slice(0, 6);
  const marketSeries = (data.market && data.market.series) || [];
  const colors = ["#1a7f4f", "#2b6cb0", "#c05621", "#6b46c1", "#b83280", "#2c7a7b"];
  const width = 760;
  const height = 280;
  const padL = 54;
  const padR = 16;
  const padT = 16;
  const padB = 26;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const xFor = (i) => padL + (months.length <= 1 ? innerW / 2 : (i / (months.length - 1)) * innerW);
  const allVals = [...series.flatMap((s) => s.points.map((p) => p.perM2)), ...marketSeries.map((p) => p.perM2)].filter((v) => v != null);
  if (!allVals.length) return '<div class="empty">لا توجد بيانات سلسلة زمنية بعد.</div>';
  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const pad = (max - min) * 0.08 || 1;
  const lo = Math.max(0, min - pad);
  const hi = max + pad;
  const span = hi - lo || 1;
  const yFor = (v) => padT + (1 - (v - lo) / span) * innerH;
  const nice = (v) => (v >= 1000 ? `${(v / 1000).toLocaleString("en-US", { maximumFractionDigits: 1 })}k` : Math.round(v).toLocaleString("en-US"));

  // شبكة أفقية + محور قيم على اليسار
  const grid = [];
  for (let t = 0; t <= 4; t++) {
    const v = hi - (span * t) / 4;
    const y = yFor(v);
    grid.push(`<line x1="${padL}" y1="${y.toFixed(1)}" x2="${width - padR}" y2="${y.toFixed(1)}" class="grid-line"/>`);
    grid.push(`<text x="${padL - 8}" y="${(y + 3).toFixed(1)}" text-anchor="end" class="axis-label">${nice(v)}</text>`);
  }
  const monthLabels = months.map((m, i) => `<text x="${xFor(i).toFixed(1)}" y="${height - 6}" text-anchor="middle" class="hist-date">${escapeHtml(m.slice(5))}</text>`).join("");

  const lines = series.map((s, idx) => {
    const color = colors[idx % colors.length];
    // النقاط الصالحة فقط — شهر بلا سعر متر لا يُرسم كصفر
    const valid = s.points.filter((p) => p.perM2 != null);
    const pts = valid.map((p) => `${xFor(months.indexOf(p.month)).toFixed(1)},${yFor(p.perM2).toFixed(1)}`);
    const poly = `<polyline fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" points="${pts.join(" ")}"/>`;
    const dots = valid.map((p, i) => {
      const [x, y] = pts[i].split(",");
      return `<circle cx="${x}" cy="${y}" r="3.5" fill="${color}"><title>${escapeHtml(s.area)} · ${p.month} · ${nice(p.perM2)} د.ك/م²</title></circle>`;
    }).join("");
    return poly + dots;
  }).join("");

  // خط وسيط السوق العام المتقطع + تعبئة متدرجة تحته
  let marketArea = "";
  let marketLine = "";
  let marketLegend = "";
  if (marketSeries.length >= 2) {
    const pts = marketSeries.map((p) => `${xFor(months.indexOf(p.month)).toFixed(1)},${yFor(p.perM2).toFixed(1)}`);
    marketArea = `<polyline fill="url(#mktGrad)" stroke="none" points="${padL},${padT + innerH} ${pts.join(" ")} ${width - padR},${padT + innerH}"/>`;
    marketLine = `<polyline fill="none" stroke="#2d3748" stroke-width="2" stroke-dasharray="6 4" stroke-linejoin="round" points="${pts.join(" ")}"/>`;
    marketLegend = '<span class="hist-legend-item market-legend"><i></i>وسيط السوق العام</span>';
  }
  const legend = [...series.map((s, idx) => `<span class="hist-legend-item"><i style="background:${colors[idx % colors.length]}"></i>${escapeHtml(s.area)}</span>`), marketLegend].join("");
  return `
    <div class="trends-block">
      <div class="hist-chart">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="اتجاهات أسعار المتر عبر الأشهر">
          <defs><linearGradient id="mktGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2d3748" stop-opacity=".12"/><stop offset="100%" stop-color="#2d3748" stop-opacity="0"/></linearGradient></defs>
          ${grid.join("")}${marketArea}${lines}${marketLine}${monthLabels}
        </svg>
      </div>
      <div class="hist-legend">${legend}</div>
    </div>`;
}

async function loadInsights() {
  if (insightsState.loaded) return;
  const root = $("insightsRoot");
  if (root) root.innerHTML = '<div class="empty">جاري تحميل تحليلات السوق...</div>';
  try {
    insightsState.data = await getJson("/api/market-insights");
    insightsState.loaded = true;
    if (oppState.priceTrends == null) {
      oppState.priceTrends = await getJson("/api/price-trends").catch(() => null);
    }
    insightsState.demand = await getJson("/api/market-demand").catch(() => null);
    renderInsights();
  } catch (err) {
    console.error(err);
    if (root) root.innerHTML = `<div class="empty">تعذر تحميل تحليلات السوق: ${escapeHtml(err.message)}</div>`;
  }
}

// وضع تلوين الخريطة: «فجوة السعر» (افتراضي) أو «عائد الإيجار» — يُحفظ في المتصفح
const heatmapModeKey = "alforaij_heatmap_mode_v1";
let heatmapMode = (() => {
  try {
    return localStorage.getItem(heatmapModeKey) === "yield" ? "yield" : "gap";
  } catch {
    return "gap";
  }
})();

function setHeatmapMode(mode) {
  heatmapMode = mode === "yield" ? "yield" : "gap";
  try {
    localStorage.setItem(heatmapModeKey, heatmapMode);
  } catch {
    // تجاهل بصمت
  }
  document.querySelectorAll(".heatmap-mode-switch .mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.heatMode === heatmapMode);
  });
  syncHeatmapLegends();
  renderInsightsHeatmap(insightsState.data);
}

function syncHeatmapLegends() {
  const isYield = heatmapMode === "yield";
  const html = isYield
    ? '<i class="legend-swatch" style="background:hsl(120 62% 26% / .92)"></i>عائد مرتفع (فرصة)<i class="legend-swatch" style="background:hsl(60 62% 26% / .92)"></i>عائد متوسط<i class="legend-swatch" style="background:hsl(0 62% 26% / .92)"></i>عائد منخفض'
    : '<i class="legend-swatch legend-cheap"></i>أرخص من وسيط المحافظة (فرصة)<i class="legend-swatch legend-neutral"></i>قريب من الوسيط<i class="legend-swatch legend-expensive"></i>أعلى من الوسيط (مضخم)';
  const insightsLegend = $("insightsHeatmapLegend");
  if (insightsLegend) insightsLegend.innerHTML = html;
}

// لون متدرج من الأخضر (فرصة) عبر الكهرماني إلى الأحمر (مضخم) حسب فجوة ±30%
// الإضاءة 26% حتى يبقى النص الأبيض فوق الخلايا مقروءًا (WCAG AA ≥4.5:1)
function heatColor(gapPct) {
  const t = Math.max(0, Math.min(1, (gapPct + 30) / 60)); // 0 عند -30% ... 1 عند +30%
  const hue = Math.round(120 * (1 - t)); // 120 أخضر → 0 أحمر
  return `hsl(${hue} 62% 26% / .92)`;
}

// لون حسب العائد السنوي: أخضر عند ≥6% (فرصة استثمارية) عبر الكهرماني إلى أحمر عند ≤2%
// الإضاءة 26% حتى يبقى النص الأبيض فوق الخلايا مقروءًا (WCAG AA ≥4.5:1)
function yieldColor(yieldPct) {
  if (yieldPct == null) return "hsl(220 18% 26% / .85)";
  const t = Math.max(0, Math.min(1, (yieldPct - 2) / 4)); // 0 عند 2% ... 1 عند 6%
  const hue = Math.round(120 * t); // 0 أحمر → 120 أخضر
  return `hsl(${hue} 62% 26% / .92)`;
}

function heatmapCellsHtml(areas) {
  const isYield = heatmapMode === "yield";
  return areas.map((a) => {
    // كل خلية تحمل القيمتين (الفجوة والعائد) — اللون والنص حسب الوضع المختار
    const value = isYield ? a.yieldPct : a.gapPct;
    const color = isYield ? yieldColor(value) : heatColor(value);
    const cls = isYield
      ? value >= 6 ? "heat-cheap" : value <= 2 ? "heat-expensive" : "heat-fair"
      : a.gapPct <= -8 ? "heat-cheap" : a.gapPct >= 8 ? "heat-expensive" : "heat-fair";
    const sign = !isYield && value > 0 ? "+" : "";
    const unit = isYield ? "% عائد سنوي" : "% فجوة";
    const title = isYield
      ? `${escapeHtml(a.area)} — عائد إيجار سنوي ${value != null ? value.toLocaleString("en-US", { maximumFractionDigits: 1 }) : "—"}% (بيع ${a.saleCount ?? a.count ?? 0} + إيجار ${a.rentCount ?? 0})`
      : `${escapeHtml(a.area)} — وسيط ${a.perM2.toLocaleString("en-US")} د.ك/م² مقابل وسيط ${escapeHtml(a.governorate || "" )}: ${sign}${value}% (${a.count} إعلان بيع)`;
    const watched = isWatchedArea(a.area);
    return `
      <div class="heat-cell-wrap">
        <button type="button" class="heat-cell ${cls}" data-heat-area="${escapeHtml(a.area)}" data-heat-gov="${escapeHtml(a.governorate)}"
          style="--heat:${color}" title="${title}">
          <b>${escapeHtml(a.area)}</b>
          <span>${value != null ? `${sign}${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%` : "—"}</span>
        </button>
        <button type="button" class="heat-watch-btn${watched ? " watched" : ""}" data-watch-area="${escapeHtml(a.area)}" data-watch-gov="${escapeHtml(a.governorate)}" data-watch-gap="${a.gapPct}" data-watch-yield="${a.yieldPct ?? ""}" title="${watched ? "إلغاء مراقبة المنطقة" : "احجز هذه المنطقة لمراقبة تغيّر فجوتها"}">${watched ? "★ مراقَبة" : "☆ احجز"}</button>
      </div>`;
  }).join("");
}

// خريطة حرارية تبويب التحليلات: تُبنى من /api/market-insights (مناطق بوسيط سعر المتر والمحافظة)
function computeInsightsHeatmap(data) {
  const areas = (data && data.areas) || [];
  const govBucket = {};
  for (const a of areas) {
    if (a.medianSalePerM2 == null || !a.governorate) continue;
    (govBucket[a.governorate] ||= []).push(Number(a.medianSalePerM2));
  }
  const medianOf = (arr) => {
    if (!arr || !arr.length) return null;
    const sorted = arr.slice().sort((x, y) => x - y);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  };
  const govMedian = {};
  for (const [gov, arr] of Object.entries(govBucket)) govMedian[gov] = medianOf(arr);
  const out = [];
  for (const a of areas) {
    const med = a.medianSalePerM2 == null ? null : Number(a.medianSalePerM2);
    const base = govMedian[a.governorate];
    if (med == null || !base || !a.governorate) continue;
    const yieldPct = a.rentalYield != null ? Math.round(Number(a.rentalYield) * 10) / 10 : null;
    out.push({
      area: a.area,
      governorate: a.governorate,
      count: Number(a.saleCount) || 0,
      rentCount: Number(a.rentCount) || 0,
      perM2: med,
      gapPct: Math.round(((med / base) - 1) * 1000) / 10,
      yieldPct,
    });
  }
  return out.sort((x, y) => x.gapPct - y.gapPct);
}

function renderInsightsHeatmap(data) {
  const root = $("insightsHeatmap");
  if (!root) return;
  const areas = computeInsightsHeatmap(data);
  if (!areas.length) {
    root.innerHTML = '<div class="empty">لا توجد بيانات سعر/مساحة كافية للرسم الحراري — تتراكم مع الحصاد اليومي.</div>';
    return;
  }
  root.innerHTML = heatmapCellsHtml(areas);
  renderWatchedAreas($("watchedAreasInsights"), areas);
}

// قائمة «المناطق المراقبة»: تعرض فجوة كل منطقة محجوزة وتحدّث تلقائيًا عند تغيّر الحصاد
function renderWatchedAreas(root, currentAreas) {
  if (!root) return;
  const watched = readWatchedAreas();
  if (!watched.length) {
    root.innerHTML = '<div class="empty compact-empty">لا مناطق محجوزة بعد — اضغط «☆ احجز» على أي خلية خريطة لمتابعة تغيّر فجوتها.</div>';
    return;
  }
  const byArea = {};
  for (const area of currentAreas || []) byArea[normalizeArabic(area.area)] = area;
  const isYield = heatmapMode === "yield";
  root.innerHTML = watched.map((item) => {
    const current = byArea[normalizeArabic(item.area)];
    const value = current ? (isYield ? current.yieldPct : current.gapPct) : (isYield ? null : item.gapAtBooking);
    const sign = value != null && value > 0 && !isYield ? "+" : "";
    const color = value != null ? (isYield ? yieldColor(value) : heatColor(value)) : "hsl(220 20% 45% / .7)";
    const changed = current && item.gapAtBooking != null && Math.abs(current.gapPct - item.gapAtBooking) > 0.5;
    const delta = changed
      ? `تغيّرت فجوتها من ${signOld(item.gapAtBooking)} إلى ${signOld(current.gapPct)}`
      : "";
    return `
      <div class="watched-area" style="--heat:${color}">
        <span class="watched-dot"></span>
        <b>${escapeHtml(item.area)}</b>
        <small>${escapeHtml(item.governorate || "غير محددة")}</small>
        <strong>${value != null ? `${sign}${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%` : "—"}</strong>
        ${changed ? `<span class="watched-delta">${escapeHtml(delta)}</span>` : ""}
        <span class="watched-date">منذ ${dateText(item.savedAt ? item.savedAt.slice(0, 10) : "")}</span>
        <button type="button" class="heat-watch-btn watched-remove" data-watch-area="${escapeHtml(item.area)}" data-watch-gov="${escapeHtml(item.governorate || "")}" title="إلغاء مراقبة ${escapeHtml(item.area)}">✕ إلغاء</button>
      </div>`;
  }).join("");
}

function signOld(value) {
  if (value == null) return "—";
  const v = Number(value);
  return `${v > 0 ? "+" : ""}${v.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
}

function renderBoard() {
  const rows = sortBoardRows(filteredBoardRows());
  updateBoardSummary(rows);
  renderBoardMetricCards(boardState.records.filter((row) => rowMatchesBoardFilters(row, false, false, true)));
  renderBoardStats(rows);
  renderCompanionAds(rows);
  renderBoardMatchingLink(rows);
  renderGovernorateCards(rows);
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
    setTabCount("tabCountBoard", boardState.allRecords.length);
    // تلميح يشرح ماذا يعدّ عدّاد اللوحة: الفريج المحلي + حصاد المواقع الخارجية الموثق
    const boardEl = $("tabCountBoard");
    if (boardEl) {
      const localCount = boardState.allRecords.filter((row) => (row.source || "").includes("الفريج")).length;
      const externalCount = boardState.allRecords.length - localCount;
      boardEl.title = `لوحة السوق: ${boardState.allRecords.length} سجلًا (الفريج ${localCount} + المواقع الخارجية ${externalCount}) — كل رقم برابطه الأصلي ووقت جليه`;
    }
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
    populateAdvancedOptions();
    const modeSelect = $("boardListingModeFilter");
    if (modeSelect) {
      modeSelect.innerHTML = '<option value="">كل الأنماط</option>' + uniqueValues(boardState.records.map((row) => row.listingMode))
        .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
        .join("");
    }
    if (governorates[0]) boardState.expandedGovernorates.add(governorates[0]);
    renderBoard();
  } catch (err) {
    const root = $("governorateCards");
    if (root) root.innerHTML = `<div class="gov-empty">تعذر تحميل لوحة المحافظات: ${escapeHtml(err.message)}</div>`;
  }
}

function collectAdvancedFilters() {
  return {
    transaction: $("transactionField")?.value.trim() || "",
    propertyType: $("typeField")?.value.trim() || "",
    governorate: $("boardGovernorateFilter")?.value.trim() || "",
    areas: selectedAreas.join("، "),
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

// ---- بثّ تقدم البحث الحي: فقاعة تعرض المراحل والمصادر لحظيًا بدل «جاري البحث» الثابتة ----
// قوائم الاختيار لحقول «اكتب أو اختر» في الخيارات المتقدمة — سقوط آمن عند غياب الباك إند
const ADV_FALLBACK_TYPES = ["بيت", "شقة", "أرض", "عمارة", "تجاري", "مكتب", "دور", "مخزن", "قسيمة"];
const ADV_FALLBACK_TRANSACTIONS = ["للبيع", "للإيجار", "مطلوب للشراء", "مطلوب للإيجار"];
const ADV_FALLBACK_AREAS = [
  "الديرة", "القبلة", "الشرق", "المرقاب", "الصوابر", "دسمان", "بنيد القار", "كيفان", "الدسمة", "الروضة",
  "الخالدية", "الفيحاء", "اليرموك", "القادسية", "النهضة", "الأندلس", "الشويخ", "السرة", "الرابية", "الفردوس",
  "حولي", "السالمية", "الجابرية", "مشرف", "بيان", "الراس", "الشهداء", "البدع", "النقرة", "الجابرية",
  "الفروانية", "الرقعي", "حطين", "جليب الشيوخ", "العارضية", "صباح السالم", "ابو فطيرة", "الري", "الأندلس", "العمرية",
  "القرين", "صباح الناصر", "المنقف", "فهد الاحمد", "الظهر", "الفحيحيل", "المهبولة", "ابو حليفة", "الصليبيخات", "الشدادية",
  "السالمي", "النعيم", "الجهراء", "القصر", "الواحة", "تيماء", "النسيم", "العيون", "القيروان", "امغرة",
];

// قوائم «اكتب أو اختر» في الخيارات المتقدمة: تُملأ من الباك إند (قوائم المحلل الرسمية)
// مع سقوط آمن للقوائم الثابتة وبيانات اللوحة — تعمل في الوضع الحي والثابت على حد سواء.
// ---- شرائح المناطق المتعددة: اختيار عدة مناطق من حقل «المناطق» كشرائح قابلة للإزالة ----
let selectedAreas = [];

function renderAreaChips() {
  const wrap = $("areasChips");
  if (!wrap) return;
  wrap.innerHTML = selectedAreas
    .map((area) => `<span class="area-chip" data-area="${escapeHtml(area)}">${escapeHtml(area)}<button type="button" class="area-chip-x" title="إزالة ${escapeHtml(area)}" aria-label="إزالة ${escapeHtml(area)}">×</button></span>`)
    .join("");
  wrap.querySelectorAll(".area-chip-x").forEach((btn) => {
    btn.addEventListener("click", () => removeAreaChip(btn.closest(".area-chip")?.dataset.area || ""));
  });
}

function addAreaChip(name) {
  const area = String(name || "").trim();
  if (!area) return;
  if (!selectedAreas.some((a) => a === area)) selectedAreas.push(area);
  const field = $("areasField");
  if (field) field.value = "";
  renderAreaChips();
}

function removeAreaChip(area) {
  selectedAreas = selectedAreas.filter((a) => a !== area);
  renderAreaChips();
}

function setAreasFromString(value) {
  const list = String(value || "")
    .split(/[،,|\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  selectedAreas = list;
  renderAreaChips();
}

// ---- قائمة اقتراحات مخصصة بحوّبات لوحة المفاتيح (أسهم + Enter + تمييز مرئي) ----
// بديل أنيق عن الـ datalist الأصلي: تنقّل بأسهم الأعلى/الأسفل مع تمييز العنصر النشط،
// Enter للاختيار، Escape للإغلاق، مع دعم كامل بالماوس.
function attachTypeahead(inputId, optionsSource, onSelect) {
  const input = $(inputId);
  if (!input) return;
  const box = document.createElement("div");
  box.className = "typeahead";
  box.setAttribute("role", "listbox");
  box.hidden = true;
  document.body.appendChild(box);
  let items = [];
  let active = -1;

  const options = () => {
    const dl = $(optionsSource);
    return dl ? [...dl.options].map((o) => o.value).filter(Boolean) : [];
  };

  function position() {
    const r = input.getBoundingClientRect();
    box.style.top = `${r.bottom + 4}px`;
    box.style.left = `${r.left}px`;
    box.style.width = `${Math.max(r.width, 180)}px`;
  }

  function render() {
    const q = normalizeArabic(input.value.trim());
    items = q ? options().filter((o) => normalizeArabic(o).includes(q)) : options();
    items = items.slice(0, 50);
    if (!items.length) {
      box.hidden = true;
      return;
    }
    if (active < 0) active = 0;
    if (active >= items.length) active = items.length - 1;
    box.innerHTML = items
      .map((it, i) => `<div class="typeahead-item${i === active ? " active" : ""}" role="option" aria-selected="${i === active}" data-i="${i}">${escapeHtml(it)}</div>`)
      .join("");
    position();
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function close() {
    box.hidden = true;
    items = [];
    active = -1;
    input.removeAttribute("aria-expanded");
  }

  function move(dir) {
    if (box.hidden) render();
    if (!items.length) return;
    active = (active + dir + items.length) % items.length;
    [...box.children].forEach((el, i) => {
      el.classList.toggle("active", i === active);
      el.setAttribute("aria-selected", String(i === active));
    });
    box.children[active]?.scrollIntoView({ block: "nearest" });
  }

  function choose(i) {
    const value = items[i];
    if (value) onSelect(value, input);
    close();
  }

  input.addEventListener("focus", () => { active = 0; render(); });
  input.addEventListener("input", () => { active = 0; render(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") {
      if (!box.hidden && items.length) {
        e.preventDefault();
        e.typeaheadConsumed = true;
        choose(active >= 0 ? active : 0);
      }
    }
    else if (e.key === "Escape") { close(); }
  });
  box.addEventListener("mousedown", (e) => e.preventDefault());
  box.addEventListener("click", (e) => {
    const item = e.target.closest(".typeahead-item");
    if (item) choose(Number(item.dataset.i));
  });
  box.addEventListener("mouseover", (e) => {
    const item = e.target.closest(".typeahead-item");
    if (item) {
      active = Number(item.dataset.i);
      [...box.children].forEach((el, i) => {
        el.classList.toggle("active", i === active);
        el.setAttribute("aria-selected", String(i === active));
      });
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 160));
  window.addEventListener("scroll", close, true);
  window.addEventListener("resize", close);
  return { close };
}

function initAreaChips() {
  const field = $("areasField");
  if (!field) return;
  attachTypeahead("areasField", "advAreas", (value) => addAreaChip(value));
  attachTypeahead("transactionField", "advTransactions", (value, input) => { input.value = value; input.dispatchEvent(new Event("change")); });
  attachTypeahead("typeField", "advTypes", (value, input) => { input.value = value; input.dispatchEvent(new Event("change")); });
  // فلاتر اللوحة بنفس نمط «اكتب أو اختر» مع القوائم الرسمية (تُعبَّأ في populateAdvancedOptions)
  const boardSelect = (value, input) => {
    input.value = value;
    input.dispatchEvent(new Event("change"));
    if (input.id === "boardAreaFilter") rememberRecentArea(value);
  };
  attachTypeahead("boardGovernorateFilter", "boardGovernorates", boardSelect);
  attachTypeahead("boardTransactionFilter", "boardTransactions", boardSelect);
  attachTypeahead("boardPropertyTypeFilter", "boardPropertyTypes", boardSelect);
  attachTypeahead("boardAreaFilter", "boardAreas", boardSelect);
  field.addEventListener("change", () => addAreaChip(field.value));
  field.addEventListener("keydown", (e) => {
    if (e.typeaheadConsumed) return;
    if (e.key === "Enter" || e.key === "," || e.key === "،") {
      e.preventDefault();
      addAreaChip(field.value);
    }
  });
  field.addEventListener("blur", () => {
    if (field.value.trim()) addAreaChip(field.value);
  });
}

// القوائم الرسمية من /api/search-options — مصدر الحقيقة لحقول «اكتب أو اختر»
// (الخيارات المتقدمة + فلاتر اللوحة) حتى يطابق الاختيار المكتوب نية المحلل بالضبط.
let officialSearchOptions = null;

function fillAdvancedLists(boardAreas, boardTypes, boardTx, boardGovernorates) {
  setOptions("advTypes", uniqueValues([...ADV_FALLBACK_TYPES, ...boardTypes]));
  setOptions("advTransactions", uniqueValues([...ADV_FALLBACK_TRANSACTIONS, ...boardTx]));
  setOptions("advAreas", uniqueValues([...boardAreas, ...ADV_FALLBACK_AREAS]));
  // فلاتر اللوحة: القوائم الرسمية أولًا ثم ما يظهر في البيانات (لا نكتفي بالمشتق من البيانات)
  setOptions("boardGovernorates", uniqueValues([...boardGovernorates, ...(officialSearchOptions?.governorates || [])]));
  setOptions("boardAreas", uniqueValues([...(officialSearchOptions?.areas || []), ...boardAreas]));
  setOptions("boardTransactions", uniqueValues([...(officialSearchOptions?.transactions || []), ...boardTx]));
  setOptions("boardPropertyTypes", uniqueValues([...(officialSearchOptions?.propertyTypes || []), ...boardTypes]));
  if (officialSearchOptions) {
    setOptions("advAreas", uniqueValues([...officialSearchOptions.areas, ...ADV_FALLBACK_AREAS]));
    setOptions("advTypes", uniqueValues([...officialSearchOptions.propertyTypes, ...ADV_FALLBACK_TYPES]));
    setOptions("advTransactions", uniqueValues([...officialSearchOptions.transactions, ...ADV_FALLBACK_TRANSACTIONS]));
  }
}

function populateAdvancedOptions() {
  const boardRows = (boardState.records || []).map((r) => r).filter(Boolean);
  const boardAreas = uniqueValues([...readRecentAreas(), ...boardRows.map((r) => r.area).filter(Boolean)]);
  const boardTypes = uniqueValues(boardRows.map((r) => r.propertyType).filter(Boolean));
  const boardTx = uniqueValues(boardRows.map((r) => r.transaction).filter(Boolean));
  const boardGovernorates = uniqueValues(boardRows.map((r) => r.governorate).filter(Boolean));
  fillAdvancedLists(boardAreas, boardTypes, boardTx, boardGovernorates);
  getJson("/api/search-options")
    .then((opts) => {
      if (opts && (Array.isArray(opts.areas) || Array.isArray(opts.propertyTypes) || Array.isArray(opts.transactions) || Array.isArray(opts.governorates))) {
        officialSearchOptions = opts;
        fillAdvancedLists(boardAreas, boardTypes, boardTx, boardGovernorates);
      }
    })
    .catch(() => {
      // الوضع الثابت بلا باك إند: تبقى قوائم اللوحة + القوائم الثابتة — كافية للاختيار
    });
}

const PROGRESS_STAGE_LABELS = {
  parse: "تحليل الطلب وفهم النية",
  local: "تحميل الإعلانات المحلية",
  external: "فحص المصادر الخارجية",
  score: "تقييم المطابقة والترتيب",
  report: "بناء التقرير والتحليل الاحترافي",
  done: "اكتمل التقرير",
};
const PROGRESS_SOURCE_LABELS = {
  running: "جارٍ البحث",
  success: "نجح",
  fallback: "عبر بديل",
  failed: "فشل",
  no_results: "لا نتائج",
  no_data: "لا بيانات",
  page_reachable: "الصفحة متاحة",
};

// هل يوجد بحث جارٍ الآن؟ — يعرض نسبة الإنجاز في زر تبويب «البحث والتقييم»
let liveSearchActive = false;

function updateSearchTabProgress(total, done, isDone) {
  const el = $("tabCountSearch");
  if (!el) return;
  if (isDone) {
    // انتهى البحث — يزول التمييز الحي ويُترك العدّاد لعدد النتائج النهائية (renderReport)
    el.classList.remove("live");
    el.title = "";
    return;
  }
  if (!liveSearchActive || total <= 0) return;
  const pct = Math.min(100, Math.round((done / total) * 100));
  el.textContent = pct + "%";
  el.title = `جاري البحث: ${done}/${total} مصدر · ${pct}%`;
  el.classList.add("live");
}

function finishSearchTabProgress() {
  liveSearchActive = false;
  const el = $("tabCountSearch");
  if (!el) return;
  el.classList.remove("live");
  el.title = "";
}

function resetSearchTabProgress() {
  finishSearchTabProgress();
  const el = $("tabCountSearch");
  if (el) el.textContent = "";
}

function progressBubbleHtml(jobId) {
  return `<div class="bubble assistant live-progress" data-job="${escapeHtml(jobId)}">
    <div class="lp-head"><span class="lp-spinner" aria-hidden="true"></span> <strong class="lp-stage">جاري البحث والتقييم...</strong> <span class="lp-elapsed" title="الوقت المنقضي">0ث</span></div>
    <div class="lp-bar-wrap" hidden><div class="lp-bar"><div class="lp-bar-fill"></div></div><span class="lp-bar-label"></span></div>
    <div class="lp-detail">تحضير الطلب...</div>
    <div class="lp-sources"></div>
    <div class="meta">(${new Date().toLocaleTimeString("ar-KW-u-nu-latn")})</div>
  </div>`;
}

// يحدّث فقاعة التقدم الحية من استجابة /api/analyze/progress
function renderLiveProgress(bubbleEl, data, startedAt) {
  const total = Number(data.totalSources || 0);
  const done = Number(data.doneSources || 0);
  // حتى لو انتقل المستخدم لقسم آخر، زر التبويب يعرض النسبة أثناء التشغيل
  updateSearchTabProgress(total, done, Boolean(data.done));
  if (!bubbleEl || !bubbleEl.isConnected) return false;
  const stageKey = data.stage || "";
  const stageEl = bubbleEl.querySelector(".lp-stage");
  if (stageEl && stageEl.textContent.indexOf("اكتمل") === -1) {
    stageEl.textContent = (PROGRESS_STAGE_LABELS[stageKey] || stageKey || "جاري البحث والتقييم") + "...";
  }
  const elapsedEl = bubbleEl.querySelector(".lp-elapsed");
  if (elapsedEl) elapsedEl.textContent = Math.max(1, Math.round((Date.now() - startedAt) / 1000)) + "ث";
  const events = data.events || [];
  const detailEl = bubbleEl.querySelector(".lp-detail");
  if (detailEl) {
    const last = [...events].reverse().find((e) => e.stage !== "source");
    if (last && last.message) detailEl.textContent = last.message;
  }
  // شريط الإنجاز الكلي: المصادر المنتهية / إجمالي المصادر
  const barWrap = bubbleEl.querySelector(".lp-bar-wrap");
  if (barWrap) {
    if (total > 0) {
      barWrap.hidden = false;
      const pct = Math.min(100, Math.round((done / total) * 100));
      const fill = barWrap.querySelector(".lp-bar-fill");
      if (fill) fill.style.width = pct + "%";
      const label = barWrap.querySelector(".lp-bar-label");
      const collected = Number(data.collectedRecords || 0);
      if (label) label.textContent = `${done}/${total} مصدر · ${pct}%` + (collected > 0 ? ` · ${collected} إعلان` : "");
    } else {
      barWrap.hidden = true;
    }
  }
  const listEl = bubbleEl.querySelector(".lp-sources");
  if (listEl) {
    // أحدث حدث فقط لكل مصدر (بدل تراكم صفوف «جارٍ البحث» + النهائي للمصدر نفسه)
    const latestPerSource = new Map();
    for (const e of events) {
      if (e.stage === "source" && e.name) latestPerSource.set(e.name, e);
    }
    const rows = [...latestPerSource.values()].map((e) => {
      const status = e.status || "";
      const label = PROGRESS_SOURCE_LABELS[status] || status || "";
      const cls = status === "success" || status === "fallback" ? "ok" : status === "running" ? "run" : status === "failed" ? "bad" : "mid";
      return `<div class="lp-row ${cls}"><span class="lp-dot"></span><span class="lp-name">${escapeHtml(e.name)}</span><span class="lp-count">${label}${Number(e.records) ? " · " + e.records + " إعلان" : ""}</span></div>`;
    });
    if (rows) listEl.innerHTML = rows;
  }
  return true;
}

// اقتراع دوري خفيف أثناء تشغيل البحث؛ يتوقف عند اكتمال الوظيفة أو انتهاء الطلب
function startProgressPolling(jobId, bubbleEl, isFinished) {
  if (STATIC_SNAPSHOT_MODE) return null;
  const startedAt = Date.now();
  const timer = setInterval(async () => {
    if (isFinished() || !bubbleEl.isConnected) {
      clearInterval(timer);
      return;
    }
    try {
      const res = await fetch(apiUrl("/api/analyze/progress?job=" + encodeURIComponent(jobId)), { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      if (!renderLiveProgress(bubbleEl, data, startedAt)) {
        clearInterval(timer);
        return;
      }
      if (data.done) clearInterval(timer);
    } catch (err) {
      // أخطاء اقتراع عابرة (فقدان اتصال) تُتجاهل — النتيجة النهائية تأتي من الطلب نفسه
    }
  }, 700);
  return timer;
}

async function sendChat() {
  if (state.chatSubmitting) return;
  const input = $("chatInput");
  if (!input) return;
  const filters = collectAdvancedFilters();
  const typed = (input.value && input.value.trim()) || "";
  const text = typed || buildTextFromFilters(filters);
  if (!text) return;
  // النص المكتوب يدويًا في الشات هو مصدر الحقيقة: لا تدع قيم حقول الفلاتر القديمة
  // (الباقية من نقر سابق على اللوحة/نموذج البحث) تتجاوز المنطقة/العملية/النوع المكتوبة.
  if (typed && typed !== buildTextFromFilters(filters)) {
    const parsed = parseQueryFilters(typed);
    filters.areas = parsed.area;
    filters.governorate = "";
    filters.transaction = parsed.transaction;
    filters.propertyType = parsed.propertyType;
  }
  state.chatSubmitting = true;
  const platformScope = selectedBoardPlatforms();
  const sourceMode = platformScope.sourceMode;
  const selectedSource = platformScope.selectedSource;
  const selectedSources = platformScope.selectedSources;
  const includeExternal = platformScope.includeExternal;
  const includeLocal = platformScope.includeLocal;
  const scope = platformScope.label;
  const jobId = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());

  addChatMessage('user', `<div class="bubble user">${escapeHtml(text)}<div class="meta">نطاق: ${escapeHtml(scope)} | مصادر خارجية: ${includeExternal ? 'نعم' : 'لا'}</div></div>`);
  input.value = "";
  liveSearchActive = true;
  const win = $("chatWindow");
  if (win) {
    addChatMessage('assistant', progressBubbleHtml(jobId));
    const bubbleEl = win.querySelector('.chat-message.assistant:last-child .live-progress');
    startProgressPolling(jobId, bubbleEl, () => !state.chatSubmitting);
  } else {
    addChatMessage('assistant', `<div class="bubble assistant">جاري البحث والتقييم... <div class="meta">(${new Date().toLocaleTimeString("ar-KW-u-nu-latn")})</div></div>`);
  }

  try {
    const payload = { text, mode: state.mode, includeExternal, includeLocal, sourceMode, selectedSource, selectedSources, filters, jobId };
    const report = await postJson('/api/analyze', payload);
    state.report = report;
    finishSearchTabProgress();  // عدّاد التبويب يعود لعدد النتائج النهائية (setTabCount في renderReport)

    // استبدال آخر فقاعة مساعد بالملخص
    const win = $("chatWindow");
    if (win) {
      const last = win.querySelector('.chat-message.assistant:last-child');
      if (last) {
        const scopeText = report.searchScope && report.searchScope.note
          ? `<p class="scope-note">${escapeHtml(report.searchScope.note)}</p>`
          : "";
        const detectedAreas = requestedAreas(report).join("، ") || "غير محددة";
        const generatedAt = report.generatedAt || new Date().toLocaleString("ar-KW-u-nu-latn");
        last.innerHTML = `<div class="bubble assistant">
          <strong>النتيجة:</strong>
          <p class="scope-note">منطقة البحث المكتشفة: ${escapeHtml(detectedAreas)} | تاريخ التحليل: ${escapeHtml(generatedAt)}</p>
          ${extractedFiltersHtml(report.extractedFilters)}
          ${scopeText}
          <p>${formatSummary(summaryLead(report.summary || ''))}</p>
          <div class="chat-results-preview">${report.results && report.results.length ? `<strong>عدد النتائج:</strong> ${report.results.length} — أفضل توصية: ${Math.round(report.results[0].recommendationScore || 0)}/100` : 'لا توجد نتائج.'}</div>
          <div class="meta">${new Date().toLocaleTimeString("ar-KW-u-nu-latn")}</div>
        </div>`;
      }
    }

    renderReport(report);
    state.chatMessages.push({ role: 'assistant', text: report.summary || '', report });
    state.chatSubmitting = false;
  } catch (err) {
    state.chatSubmitting = false;
    resetSearchTabProgress();
    console.error(err);
    addChatMessage('assistant', `<div class="bubble assistant error">تعذر الحصول على النتائج: ${escapeHtml(err.message)}</div>`);
  }
}

// تسمية عربية مفهومة لحالات المصادر بدل الكود الإنجليزي الخام
function toneClass(tone) {
  if (tone === "strong") return "strong";
  if (tone === "medium") return "medium";
  return "weak";
}

function renderResultsSources(report) {
  // شريط «مصادر هذه النتائج» فوق النتائج المرتبة: كل منصة ساهمت بعدّاد إعلاناتها
  // ورابط مباشر للموقع المفحوص — الدليل بنقرة واحدة دون مغادرة صفحة النتائج.
  const root = $("resultsSources");
  if (!root) return;
  const statuses = report.sourceStatus || [];
  // الوكلاء الداخليون (إكمال التفاصيل وغيرها) ليسوا مصادر — لا يظهرون في الشريط
  const contributed = statuses.filter((s) => Number(s.records || 0) > 0 && s.kind !== "internal");
  if (!contributed.length) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  root.innerHTML = `
    <span class="results-sources-label">مصادر هذه النتائج:</span>
    ${contributed.map((s) => {
      const name = escapeHtml(s.name || s.source || "مصدر");
      const count = Number(s.records || 0);
      // مؤشر جودة المصدر: ثقة % بلون أخضر/كهرماني/أحمر (يظهر بالتفصيل عند التمرير)
      const trust = s.trust || {};
      const tone = trust.tone || (s.status === "success" ? "strong" : s.status === "fallback" ? "medium" : "weak");
      const score = trust.score != null ? Number(trust.score) : null;
      const trustLine = score != null
        ? `ثقة المصدر: ${score}% — ${trust.label || ""}`
        : (trust.label ? `ثقة المصدر: ${trust.label}` : "");
      const inner = `<span class="results-source-dot ${toneClass(tone)}" aria-hidden="true"></span>${name} <b>${count}</b>`;
      const trustAttr = score != null ? `data-trust-score="${score}" data-trust-tone="${toneClass(tone)}" data-trust-label="${escapeHtml(trust.label || "")}"` : "";
      const mechLine = s.fetchMethod ? ` | آلية الجلب: ${escapeHtml(s.fetchMethod)}` : "";
      const title = [trustLine, s.url ? `فتح المصدر المفحوص` : "", mechLine].filter(Boolean).join(" ");
      return s.url
        ? `<a class="results-source-chip results-source-link" href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer" title="${title}" ${trustAttr}>${inner}</a>`
        : `<span class="results-source-chip" title="${title}" ${trustAttr}>${inner}</span>`;
    }).join("")}
    <button type="button" class="results-copy-sources" data-copy-source-links title="نسخ قائمة المنصات وروابطها المفحوصة للمشاركة">نسخ روابط المصادر</button>
  `;
  root.hidden = false;
  bindSourceTrustTip(root);
  // زر «نسخ روابط المصادر»: قائمة المنصات وروابطها المفحوصة جاهزة للمشاركة
  root.querySelectorAll("[data-copy-source-links]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lines = statuses
        .filter((s) => Number(s.records || 0) > 0 && s.kind !== "internal")
        .map((s) => {
          const name = s.name || s.source || "مصدر";
          const count = Number(s.records || 0);
          const trust = s.trust || {};
          const trustPart = trust.score != null ? ` (ثقة ${trust.score}%)` : "";
          return s.url ? `${name} — ${count} إعلان${trustPart} — ${s.url}` : `${name} — ${count} إعلان${trustPart}`;
        });
      const text = [`مصادر نتائج التحليل العقاري (منصة الفريج):`, ...lines].join("\n");
      copyText(text, btn);
    });
  });
}

function renderDemandIndicator(report) {
  // مؤشر الطلب بجانب النتائج: من يبحث عن شراء/إيجار في نفس منطقة التقييم
  const root = $("demandIndicatorBox");
  if (!root) return;
  const demand = report.demandIndicators;
  if (!demand || !demand.count) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  const scope = demand.scope ? `: ${demand.scope}` : "";
  const parts = [];
  if (demand.buyRequests) parts.push(`<b>${demand.buyRequests}</b> طلب شراء`);
  if (demand.rentRequests) parts.push(`<b>${demand.rentRequests}</b> طلب إيجار`);
  const cards = (demand.items || []).map((d) => {
    const isBuy = String(d.transaction || "").includes("شراء");
    return `
      <article class="demand-card">
        <div class="demand-card-head">
          <span class="pill tx-pill ${isBuy ? "tx-buy" : "tx-rent"}">${escapeHtml(d.transaction || "طلب")}</span>
          <span class="demand-card-area">${escapeHtml(d.area || "")}${d.governorate ? ` · ${escapeHtml(d.governorate)}` : ""}</span>
        </div>
        <p class="demand-card-summary">${escapeHtml(d.summary || "")}</p>
        <div class="demand-card-foot">
          ${d.phone ? `<span class="demand-card-phone">📞 ${escapeHtml(d.phone)}</span>` : ""}
          ${d.publishedDate ? `<span>${escapeHtml(d.publishedDate)}</span>` : ""}
          ${d.originalUrl ? `<a href="${escapeHtml(d.originalUrl)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي ←</a>` : ""}
        </div>
      </article>`;
  }).join("");
  root.innerHTML = `
    <div class="demand-indicator">
      <div class="demand-indicator-head">
        <strong>مؤشر الطلب في المنطقة${escapeHtml(scope)}</strong>
        <span>${parts.join(" · ") || "لا طلبات"} — من إعلانات «مطلوب» المحلية والخارجية، كل رقم عميل محتمل.</span>
      </div>
      <div class="demand-cards">${cards}</div>
    </div>`;
  root.hidden = false;
}

// تلميح «ثقة المصدر» المخصص عند التمرير على شريحة مصدر (أخضر/كهرماني/أحمر)
function bindSourceTrustTip(scope) {
  const tip = $("sourceTrustTip");
  if (!tip) return;
  const root = scope || document;
  root.querySelectorAll("[data-trust-score]").forEach((chip) => {
    chip.addEventListener("mouseenter", (ev) => {
      const score = Number(chip.dataset.trustScore);
      const tone = chip.dataset.trustTone || "weak";
      const label = chip.dataset.trustLabel || "";
      tip.querySelector(".source-trust-tone").className = `source-trust-tone ${tone}`;
      tip.querySelector(".source-trust-line").textContent = `${score}% — ${label}`;
      tip.hidden = false;
      positionTrustTip(tip, chip);
    });
    chip.addEventListener("mouseleave", () => {
      tip.hidden = true;
    });
    chip.addEventListener("focus", (ev) => {
      const score = Number(chip.dataset.trustScore);
      const tone = chip.dataset.trustTone || "weak";
      const label = chip.dataset.trustLabel || "";
      tip.querySelector(".source-trust-tone").className = `source-trust-tone ${tone}`;
      tip.querySelector(".source-trust-line").textContent = `${score}% — ${label}`;
      tip.hidden = false;
      positionTrustTip(tip, chip);
    });
    chip.addEventListener("blur", () => {
      tip.hidden = true;
    });
  });
}

function positionTrustTip(tip, chip) {
  const rect = chip.getBoundingClientRect();
  tip.style.left = `${Math.min(rect.left + rect.width / 2, window.innerWidth - 220)}px`;
  tip.style.top = `${Math.max(8, rect.top - 52)}px`;
}

function renderSources(report) {
  // تبويب «المصادر والتشغيل» أُزيل من الواجهة؛ يبقى من هذه الدالة عداد المصادر
  // المتصلة في لوحة البحث (connectedSources) فقط.
  const statuses = report.sourceStatus || [];
  let connected = 0;
  for (const source of statuses) {
    // «نجح عبر بديل» يعوّض المصدر المتعذر بنتائج فعلية، لذا يُحتسب ضمن المتصل
    if (source.status === "success" || (source.status === "fallback" && source.records > 0)) connected += 1;
  }
  const connectedEl = $("connectedSources");
  if (connectedEl) connectedEl.textContent = connected || "-";
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

// حكم استثماري للعائد الإيجاري السنوي: قوي (≥6%) / متوسط (4-6%) / ضعيف (<4%)
function yieldVerdictLabel(verdict) {
  if (verdict === "قوي") return "استثماري قوي";
  if (verdict === "متوسط") return "استثماري متوسط";
  if (verdict === "ضعيف") return "استثماري ضعيف";
  return "";
}

function yieldVerdictTone(verdict) {
  if (verdict === "قوي") return "yield-strong";
  if (verdict === "متوسط") return "yield-mid";
  if (verdict === "ضعيف") return "yield-weak";
  return "";
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

function gapText(item) {
  const gap = item.priceGapPct;
  if (gap === null || gap === undefined || Number.isNaN(Number(gap))) return "غير كافية";
  const value = Number(gap);
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%${value <= -8 ? " ⬅ أرخص" : value >= 8 ? " ⬅ أغلى" : " ≈ السوق"}`;
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
    const published = dateText(item.publishedDate);
    const views = viewsText(item);
    const reasons = (item.reasons || []).slice(0, 5).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
    const link = item.originalUrl
      ? `<a href="${escapeHtml(item.originalUrl)}" target="_blank" rel="noreferrer">فتح المصدر</a>`
      : "";
    // صفوف الفروق تُعرض فقط عندما تكون محسوبة فعلًا — لا «غير محسوب» بلا فائدة
    const deltas = [
      item.priceDelta != null ? `<span><b>فرق السعر</b>${escapeHtml(signedNumber(item.priceDelta, " د.ك"))}</span>` : "",
      item.spaceDelta != null ? `<span><b>فرق المساحة</b>${escapeHtml(signedNumber(item.spaceDelta, " م²"))}</span>` : "",
    ].join("");
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
          ${deltas}
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
  renderResultsSources(report);
  renderDemandIndicator(report);
  renderProfitOpportunities(report);
  renderSimilarExternal(report);
  renderMethod(report);    const results = report.results || [];
  setTabCount("tabCountSearch", results.length);
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
    // شارات التصنيف: مكتب/مباشر (نمط الإدراج) + نوع المعاملة + المصدر
    const modeEl = node.querySelector(".mode-pill");
    if (modeEl) {
      const mode = String(item.listingMode || "").trim();
      if (mode) {
        const isOffice = normalizeArabic(mode).includes("مكتب");
        modeEl.textContent = mode;
        modeEl.className = `pill mode-pill ${isOffice ? "mode-office" : "mode-direct"}`;
        modeEl.hidden = false;
      }
    }
    const txEl = node.querySelector(".tx-pill");
    if (txEl) {
      const tx = String(item.transaction || "").trim();
      if (tx) {
        txEl.textContent = tx;
        txEl.className = `pill tx-pill ${normalizeArabic(tx).includes("إيجار") ? "tx-rent" : "tx-sale"}`;
        txEl.hidden = false;
      }
    }
    const srcEl = node.querySelector(".src-pill");
    if (srcEl) {
      srcEl.textContent = latinDigits(item.fallbackFor ? `${item.source || "مصدر"} ← ${item.fallbackFor}` : (item.source || "مصدر غير محدد"));
    }
    const sourceLabel = item.fallbackFor
      ? `${item.source || "مصدر غير محدد"} (عبر بديل ${item.fallbackFor})`
      : (item.source || "مصدر غير محدد");
    node.querySelector(".meta").textContent = latinDigits(`${sourceLabel} | ${item.governorate || ""} | ${item.propertyType || item.detailClass || ""}`);
    // شبكة الحقائق: صف أول (كود/محافظة/منطقة/نوع) + صف ثانٍ (سعر/مساحة/تاريخ/مشاهدات)
    const factsEl = node.querySelector(".card-facts");
    if (factsEl) {
      factsEl.innerHTML = [
        ["كود الإعلان", item.code || "—"],
        ["المحافظة", item.governorate || "—"],
        ["المنطقة", item.area || "—"],
        ["نوع العقار", item.propertyType || item.detailClass || "—"],
        ["السعر", item.priceText || (item.price ? formatMoney(item.price) : "غير معلن")],
        ["المساحة", item.space ? `${item.space} م²` : "غير محدد"],
        ["تاريخ النشر", dateText(item.publishedDate)],
        ["المشاهدات", viewsText(item)],
      ].map(([label, value]) => `
        <div class="fact-cell">
          <span class="fact-label">${escapeHtml(label)}</span>
          <strong class="fact-value">${escapeHtml(value)}</strong>
        </div>
      `).join("");
    }
    const outsideBadge = node.querySelector(".outside-area");
    if (outsideBadge) {
      const labels = (item.warnings || []).filter((w) => String(w).includes("خارج المنطقة المطلوبة"));
      outsideBadge.textContent = labels[0] || "";
      outsideBadge.hidden = !labels.length;
    }
    // شارة «أرخص/أغلى من السوق» + مؤشر فجوة السعر (السعر المطلوب ÷ وسيط المنطقة)
    const gapBadge = node.querySelector(".price-gap-badge");
    if (gapBadge) {
      const gap = item.priceGapPct;
      const label = item.priceGapLabel;
      if (label && typeof gap === "number" && !Number.isNaN(gap)) {
        gapBadge.textContent = `${label} ${gap >= 0 ? "+" : ""}${gap.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
        gapBadge.className = `price-gap-badge ${gap <= -8 ? "gap-cheap" : gap >= 8 ? "gap-expensive" : "gap-fair"}`;
        gapBadge.title = `فجوة السعر = السعر المطلوب ÷ وسيط المنطقة (${formatMoney(item.marketMedian)}). القيمة: ${gap >= 0 ? "+" : ""}${gap}%`;
        gapBadge.hidden = false;
      }
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
      scoreItem("المشاهدات", viewsText(item)),    scoreItem("وسيط المقارنات", formatMoney(item.marketMedian)),
    scoreItem("فجوة السعر (سعر ÷ وسيط المنطقة)", gapText(item)),
    item.rentalYieldPercent != null ? scoreItem("العائد الإيجاري السنوي", `${item.rentalYieldPercent}% — ${yieldVerdictLabel(item.rentalYieldVerdict)}`, yieldVerdictTone(item.rentalYieldVerdict)) : "",
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
    if (decisionEl) decisionEl.textContent = latinDigits(item.decisionLine || "");
    // قصّ النصوص الطويلة مع زر «عرض المزيد» عند النقر — لا كلام مكرر ظاهر بلا فائدة
    const reasonEl = node.querySelector(".valuation-reason");
    reasonEl.textContent = latinDigits(item.valuationReason || "لا يوجد سبب تقييم كاف.");
    attachClampToggle(reasonEl);
    const descEl = node.querySelector(".description");
    descEl.textContent = latinDigits(item.summary || item.features || "");
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

    const detailsBox = node.querySelector(".result-details");
    const detailsBtn = node.querySelector(".details-btn");
    if (detailsBox && detailsBtn) {
      const toggleDetails = () => {
        detailsBox.open = !detailsBox.open;
        detailsBtn.textContent = detailsBox.open ? "إخفاء التفاصيل" : "عرض التفاصيل";
      };
      detailsBtn.addEventListener("click", toggleDetails);
      // «التفاصيل والأدلة» في الدليل الداخلي يفتح البطاقة نفسها
      const summary = detailsBox.querySelector("summary");
      if (summary) summary.addEventListener("click", (ev) => { ev.preventDefault(); toggleDetails(); });
    }
    const pubDate = node.querySelector(".pub-date");
    if (pubDate) pubDate.textContent = `تاريخ النشر: ${dateText(item.publishedDate)}`;
    const link = node.querySelector(".open-link");
    link.href = item.originalUrl || "#";
    link.hidden = !item.originalUrl;
    // اسم المصدر في زر الفتح — يعرف المستخدم أين يذهب قبل النقر
    link.textContent = item.source ? `فتح على ${item.source}` : "فتح الإعلان الأصلي";
    // زر «تواصل مع المعلن» عبر واتساب: يظهر عندما يحمل الإعلان رقم هاتف المعلن
    // (يُستخرج من صفحة تفاصيل الإعلان — Q8Aqar/Mourjan/4Sale…) برسالة جاهزة مخصصة
    if (item.phone) {
      const contactLink = document.createElement("a");
      contactLink.className = "wa-contact chat-wa-contact";
      contactLink.href = `${waLink(item.phone)}?text=${encodeURIComponent(oppWhatsAppSummary(item))}`;
      contactLink.target = "_blank";
      contactLink.rel = "noreferrer";
      contactLink.textContent = "تواصل مع المعلن";
      contactLink.title = `واتساب المعلن: ${latinDigits(item.phone)}`;
      contactLink.addEventListener("click", () => trackOutreach({ action: "contact", channel: "chat_result", opportunityCode: item.code || "" }));
      link.after(contactLink);
    }
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

// تقرير PDF داخل المتصفح للوضع الثابت: يبني HTML مطبوعًا بأقسام التقرير ويفتح نافذة الطباعة (حفظ PDF)
function staticDownloadPdf() {
  const report = state.report;
  if (!report) return;
  const results = (report.results || []).slice(0, 20);
  const rowsHtml = results.map((item, index) => `
    <tr>
      <td>${index + 1}</td>
      <td>${escapeHtml(item.code || "")}</td>
      <td>${escapeHtml(item.area || "")}</td>
      <td>${escapeHtml(item.priceText || (item.price ? formatMoney(item.price) : "غير معلن"))}</td>
      <td>${item.space ? `${escapeHtml(String(item.space))} م²` : "غير مذكورة"}</td>
      <td>${escapeHtml(item.source || "")}</td>
      <td>${Math.round(item.recommendationScore || 0)}/100</td>
      <td>${escapeHtml(item.valuationLabel || "")}</td>
    </tr>`).join("");
  const top = results[0];
  const compsRows = top && top.comparables && top.comparables.length
    ? top.comparables.map((comp) => `
        <tr>
          <td>${escapeHtml(comp.code || "")}</td>
          <td>${escapeHtml(comp.area || "")}</td>
          <td>${escapeHtml(comp.priceText || (comp.price ? formatMoney(comp.price) : "غير معلن"))}</td>
          <td>${comp.space ? `${escapeHtml(String(comp.space))} م²` : "غير مذكورة"}</td>
          <td>${escapeHtml(comp.source || "")}</td>
          <td>${comp.url ? `<a href="${escapeHtml(comp.url)}">فتح الإعلان</a>` : "—"}</td>
        </tr>`).join("")
    : '<tr><td colspan="6" style="text-align:center">لا توجد مقارنات سعرية ضمن النطاق الحالي.</td></tr>';
  const reasons = top && top.reasons && top.reasons.length
    ? top.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")
    : "";
  // مؤشر الطلب: طلبات «مطلوب للشراء/للإيجار» المنافسة في نفس المنطقة — بجانب ملخص التقييم
  const demand = report.demandIndicators;
  const demandSection = demand && demand.count
    ? `
  <h2>مؤشر الطلب — طلبات المنطقة المنافسة</h2>
  <p class="meta">${escapeHtml(demand.scope || "كل الكويت")} · ${demand.count} طلبًا من «مطلوب للشراء/للإيجار» — من يبحث في نفس المنطقة التي قُيّم فيها العقار</p>
  <table>
    <thead><tr><th>النطاق</th><th>إجمالي الطلبات</th><th>طلبات شراء</th><th>طلبات إيجار</th></tr></thead>
    <tbody><tr><td>${escapeHtml(demand.scope || "كل الكويت")}</td><td>${demand.count}</td><td>${demand.buyRequests || 0}</td><td>${demand.rentRequests || 0}</td></tr></tbody>
  </table>
  ${(demand.items && demand.items.length) ? `
  <table>
    <thead><tr><th>#</th><th>الكود</th><th>نوع الطلب</th><th>المنطقة</th><th>المحافظة</th><th>نوع العقار</th><th>تاريخ النشر</th></tr></thead>
    <tbody>${demand.items.map((item, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${escapeHtml(item.code || "—")}</td>
        <td>${escapeHtml(item.transaction || "—")}</td>
        <td>${escapeHtml(item.area || "—")}</td>
        <td>${escapeHtml(item.governorate || "—")}</td>
        <td>${escapeHtml(item.propertyType || "—")}</td>
        <td>${escapeHtml(String(item.publishedDate || "—").slice(0, 10))}</td>
      </tr>`).join("")}</tbody>
  </table>` : ""}`
    : "";
  const win = window.open("", "_blank", "width=900,height=700");
  if (!win) {
    alert("اسمح بالنوافذ المنبثقة لتوليد تقرير PDF داخل المتصفح.");
    return;
  }
  win.document.write(`<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>تقرير تقييم عقاري — النسخة الثابتة</title>
<style>
  body{font-family:"Segoe UI",Tahoma,Arial,sans-serif;color:#0F172A;margin:24px;line-height:1.6}
  h1{color:#1457A8;font-size:20px;margin:0 0 4px}
  .meta{color:#64748B;font-size:12px;margin-bottom:16px}
  h2{color:#1457A8;font-size:15px;border-bottom:2px solid #1457A8;padding-bottom:4px;margin:20px 0 8px}
  table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px}
  th{background:#0F172A;color:#fff;padding:6px 8px;text-align:right}
  td{border:1px solid #CBD5E1;padding:6px 8px}
  .badge{display:inline-block;background:#EFF6FF;color:#1457A8;border:1px solid #BFDBFE;border-radius:999px;padding:2px 10px;font-size:12px}
  ul{margin:4px 0}
  .note{background:#FFF7ED;border:1px solid #FDBA74;border-radius:8px;padding:8px 12px;font-size:12px;color:#7C2D12}
  @media print{body{margin:12mm}}
</style>
</head>
<body>
  <h1>تقرير تقييم عقاري</h1>
  <p class="meta">${escapeHtml(report.generatedAt || new Date().toLocaleString("ar-KW-u-nu-latn"))} · تحليل من أحدث بيانات السوق المنشورة · احفظ الصفحة PDF من نافذة الطباعة</p>
  <div class="note">${escapeHtml((report.searchScope && report.searchScope.note) || "يعتمد التحليل على أحدث بيانات السوق المنشورة من جميع المصادر.")}</div>
  <h2>النتائج المرتبة حسب درجة التوصية</h2>
  <table>
    <thead><tr><th>#</th><th>الإعلان</th><th>المنطقة</th><th>السعر</th><th>المساحة</th><th>المصدر</th><th>التوصية</th><th>الحكم</th></tr></thead>
    <tbody>${rowsHtml}</tbody>
  </table>
  ${top ? `
  <h2>التفاصيل التحليلية لأفضل نتيجة: ${escapeHtml(top.code)} — ${escapeHtml(top.area || "")}</h2>
  <table>
    <tbody>
      <tr><td>حكم السعر</td><td>${escapeHtml(top.valuationLabel || "")}</td></tr>
      <tr><td>درجة التوصية</td><td>${Math.round(top.recommendationScore || 0)} / 100</td></tr>
      <tr><td>الثقة</td><td>${top.numberSources && top.numberSources.confidence ? `${Math.round(top.numberSources.confidence.value || 0)}%` : "—"}</td></tr>
      <tr><td>السبب</td><td>${escapeHtml(top.valuationReason || "")}</td></tr>
      ${top.originalUrl ? `<tr><td>رابط الإعلان</td><td><a href="${escapeHtml(top.originalUrl)}">${escapeHtml(top.originalUrl)}</a></td></tr>` : ""}
      ${top.numberSources && top.numberSources.marketMedian && top.numberSources.marketMedian.value ? `<tr><td>وسيط سعر المنطقة</td><td>${escapeHtml(formatMoney(top.numberSources.marketMedian.value))} (${escapeHtml(top.numberSources.marketMedian.note || "")})</td></tr>` : ""}
    </tbody>
  </table>
  ${reasons ? `<p><strong>أسباب التوصية:</strong></p><ul>${reasons}</ul>` : ""}
  <h2>المقارنات السعرية الداخلة في التقييم</h2>
  <table>
    <thead><tr><th>الكود</th><th>المنطقة</th><th>السعر</th><th>المساحة</th><th>المصدر</th><th>الرابط</th></tr></thead>
    <tbody>${compsRows}</tbody>
  </table>` : ""}
  ${demandSection}
  <p class="meta">تقرير مولّد داخل المتصفح من أحدث بيانات السوق المنشورة من جميع المصادر.</p>
</body>
</html>`);
  win.document.close();
  setTimeout(() => win.print(), 250);
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
    if (STATIC_SNAPSHOT_MODE) {
      staticDownloadPdf();
      return;
    }
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
    // على مضيف بلا API (خادم ثابت محلي مثلًا): توليد التقرير داخل المتصفح
    console.warn("live PDF failed, falling back to in-browser print report:", err);
    staticDownloadPdf();
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
  platform: "", // فلتر منصة دقيق: اسم المصدر (الفريج/Mourjan/OpenSooq/…) أو "" الكل
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
    if (oppState.platform && (item.source || "") !== oppState.platform) return false;
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

// شريط «مصادر هذه النتائج» فوق بطاقات الفرص: كل منصة ساهمت بعدّاد فرصها،
// والنقر على أي منصة يفلتر البطاقات إليها فورًا (مثل شريط مصادر نتائج البحث).
function renderOppPlatformBar(items) {
  const root = $("oppSourcesBar");
  if (!root) return;
  const list = items || [];
  if (!list.length) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  const counts = {};
  const confidences = {};
  for (const item of list) {
    const source = (item.source || "غير محدد").trim() || "غير محدد";
    counts[source] = (counts[source] || 0) + 1;
    const conf = Number(item.confidence);
    if (isFinite(conf) && conf > 0) {
      confidences[source] = (confidences[source] || []).concat(conf);
    }
  }
  const trustToneOf = (avg) => (avg >= 0.8 ? "strong" : avg >= 0.55 ? "medium" : "weak");
  const chips = [
    `<button type="button" class="results-source-chip opp-platform-chip${oppState.platform ? "" : " active"}" data-opp-platform="" title="عرض فرص كل المنصات">الكل <b>${list.length}</b></button>`,
  ];
  for (const [source, count] of Object.entries(counts).sort((a, b) => b[1] - a[1])) {
    const confs = confidences[source] || [];
    const avg = confs.length ? confs.reduce((a, b) => a + b, 0) / confs.length : null;
    const trustAttr = avg != null
      ? `data-trust-score="${Math.round(avg * 100)}" data-trust-tone="${trustToneOf(avg)}" data-trust-label="متوسط ثقة الفرص"`
      : "";
    chips.push(`<button type="button" class="results-source-chip opp-platform-chip${oppState.platform === source ? " active" : ""}" data-opp-platform="${escapeHtml(source)}" title="عرض فرص ${escapeHtml(source)} فقط" ${trustAttr}>${avg != null ? `<span class="results-source-dot ${trustToneOf(avg)}" aria-hidden="true"></span>` : ""}${escapeHtml(source)} <b>${count}</b></button>`);
  }
  root.innerHTML = `<span class="results-sources-label">مصادر هذه النتائج:</span>${chips.join("")}`;
  root.hidden = false;
  bindSourceTrustTip(root);
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
  if (!isRental && item.rentalYieldPercent != null) {
    const verdict = item.rentalYieldVerdict ? ` (${item.rentalYieldVerdict})` : "";
    lines.push(`📈 العائد الإيجاري: ${item.rentalYieldPercent}% سنويًا${verdict}`);
  }
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
    item.rentalYieldPercent != null ? scoreItem("العائد الإيجاري السنوي", `${item.rentalYieldPercent}% — ${yieldVerdictLabel(item.rentalYieldVerdict)}`, yieldVerdictTone(item.rentalYieldVerdict)) : "",
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
        ${item.url ? `<a class="open-link" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">فتح على ${escapeHtml(item.source || "الإعلان الأصلي")}</a>` : ""}
        ${item.phone ? `<a class="wa-contact" href="${escapeHtml(waLink(item.phone))}?text=${encodeURIComponent(oppWhatsAppSummary(item))}" target="_blank" rel="noreferrer">تواصل مع المعلن (واتساب)</a>` : ""}
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

// رسم اتجاهات الأسعار الشهرية من جدول price_trends (يُملأ يوميًا من الحصاد)
// — وسيط سعر المتر لكل منطقة/نوع عبر الأشهر: خط لكل منطقة بأحدث قيمة فقط.
function renderPriceTrendsChart(root, embedded) {
  const data = oppState.priceTrends;
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return "";
  }
  // أحدث 8 أشهر مرتبة تصاعديًا، وخط لكل منطقة (وسيط سعر المتر) إن توفرت نقطتان+
  const months = [...new Set(rows.map((r) => r.month))].sort().slice(-8);
  const byArea = {};
  for (const row of rows) {
    if (!months.includes(row.month)) continue;
    (byArea[row.area] ||= []).push(row);
  }
  const series = Object.entries(byArea)
    .map(([area, pts]) => ({ area, pts: pts.sort((a, b) => a.month.localeCompare(b.month)) }))
    .filter((s) => s.pts.filter((p) => p.median_price_per_m2 != null).length >= 2);
  const heading = `<h3>اتجاهات الأسعار الشهرية (من الحصاد)</h3>
      <p class="scope-note">وسيط سعر المتر (د.ك/م²) لكل منطقة عبر الأشهر — من جدول price_trends المملوء يوميًا بالحصاد. الخط المتقطع = وسيط السوق العام.</p>`;
  if (!series.length) {
    // لا توجد سلسلة سعر متر كافية — نعرض ملخص أحدث الوسيطات بدل رسم فارغ
    const latest = rows.filter((r) => r.month === months[months.length - 1]);
    if (!latest.length) return "";
    const items = latest.slice(0, 12).map((r) => `
      <span class="filter-chip"><b>${escapeHtml(r.area)}</b>${r.median_price_per_m2 != null ? `${r.median_price_per_m2} د.ك/م²` : `${r.median_price ?? "—"} د.ك`} · ${escapeHtml(r.property_type || "عام")} · ${escapeHtml(r.month)}</span>`);
    return `
      <div class="trends-block">
        ${embedded ? "" : heading}
        <div class="similar-external-list">${items.join("")}</div>
      </div>`;
  }
  const colors = ["#1a7f4f", "#2b6cb0", "#c05621", "#6b46c1", "#b83280", "#2c7a7b"];
  // وسيط السوق العام: لكل شهر وسيط قيم كل المناطق
  const marketSeries = months.map((m) => {
    const vals = series.flatMap((s) => s.pts.filter((p) => p.month === m && p.median_price_per_m2 != null).map((p) => p.median_price_per_m2));
    if (!vals.length) return null;
    vals.sort((a, b) => a - b);
    const mid = Math.floor(vals.length / 2);
    return { month: m, perM2: vals.length % 2 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2 };
  }).filter(Boolean);
  // أعلى 6 مناطق بأحدث قيمة + وسيط السوق — يُبقي الرسم مقروءًا بدل 27 خطًا متشابكًا
  const topSeries = series
    .map((s) => ({ ...s, last: s.pts.filter((p) => p.median_price_per_m2 != null).slice(-1)[0]?.median_price_per_m2 }))
    .sort((a, b) => (b.last ?? 0) - (a.last ?? 0))
    .slice(0, 6);
  const width = 760;
  const height = 280;
  const padL = 54;
  const padR = 16;
  const padT = 16;
  const padB = 26;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const xFor = (i) => padL + (months.length <= 1 ? innerW / 2 : (i / (months.length - 1)) * innerW);
  const allVals = [...topSeries.flatMap((s) => s.pts.map((p) => p.median_price_per_m2)), ...marketSeries.map((p) => p.perM2)].filter((v) => v != null);
  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const pad = (max - min) * 0.08 || 1;
  const lo = Math.max(0, min - pad);
  const hi = max + pad;
  const span = hi - lo || 1;
  const yFor = (v) => padT + (1 - (v - lo) / span) * innerH;
  const nice = (v) => (v >= 1000 ? `${(v / 1000).toLocaleString("en-US", { maximumFractionDigits: 1 })}k` : Math.round(v).toLocaleString("en-US"));
  const grid = [];
  for (let t = 0; t <= 4; t++) {
    const v = hi - (span * t) / 4;
    const y = yFor(v);
    grid.push(`<line x1="${padL}" y1="${y.toFixed(1)}" x2="${width - padR}" y2="${y.toFixed(1)}" class="grid-line"/>`);
    grid.push(`<text x="${padL - 8}" y="${(y + 3).toFixed(1)}" text-anchor="end" class="axis-label">${nice(v)}</text>`);
  }
  const monthLabels = months.map((m, i) => `<text x="${xFor(i).toFixed(1)}" y="${height - 6}" text-anchor="middle" class="hist-date">${escapeHtml(m.slice(5))}</text>`).join("");
  const lines = topSeries.map((s, idx) => {
    const color = colors[idx % colors.length];
    // النقاط الصالحة فقط — أي شهر بلا سعر متر لا يُرسم كصفر في القاع
    const valid = s.pts.filter((p) => p.median_price_per_m2 != null);
    const pts = valid.map((p, i) => `${xFor(months.indexOf(p.month)).toFixed(1)},${yFor(p.median_price_per_m2).toFixed(1)}`);
    const poly = `<polyline fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" points="${pts.join(" ")}"/>`;
    const dots = valid.map((p, i) => {
      const [x, y] = pts[i].split(",");
      return `<circle cx="${x}" cy="${y}" r="3.5" fill="${color}"><title>${escapeHtml(s.area)} · ${p.month} · ${nice(p.median_price_per_m2)} د.ك/م²</title></circle>`;
    }).join("");
    return poly + dots;
  }).join("");
  let marketArea = "";
  let marketLine = "";
  let marketLegend = "";
  if (marketSeries.length >= 2) {
    const pts = marketSeries.map((p) => `${xFor(months.indexOf(p.month)).toFixed(1)},${yFor(p.perM2).toFixed(1)}`);
    marketArea = `<polyline fill="url(#ptGrad)" stroke="none" points="${padL},${padT + innerH} ${pts.join(" ")} ${width - padR},${padT + innerH}"/>`;
    marketLine = `<polyline fill="none" stroke="#2d3748" stroke-width="2" stroke-dasharray="6 4" stroke-linejoin="round" points="${pts.join(" ")}"/>`;
    marketLegend = '<span class="hist-legend-item market-legend"><i></i>وسيط السوق العام</span>';
  }
  const legend = [...topSeries.map((s, idx) => `<span class="hist-legend-item"><i style="background:${colors[idx % colors.length]}"></i>${escapeHtml(s.area)}</span>`), marketLegend].join("");
  return `
    <div class="trends-block">
      ${embedded ? "" : heading}
      <div class="hist-chart">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="اتجاهات أسعار المتر عبر الأشهر">
          <defs><linearGradient id="ptGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2d3748" stop-opacity=".12"/><stop offset="100%" stop-color="#2d3748" stop-opacity="0"/></linearGradient></defs>
          ${grid.join("")}${marketArea}${lines}${marketLine}${monthLabels}
        </svg>
      </div>
      <div class="hist-legend">${legend}</div>
    </div>`;
}

function renderHistoryTab(root) {
  const trendsHtml = renderPriceTrendsChart(root);
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
  root.innerHTML = trendsHtml + historyHtml + outreachHtml;
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
          <p class="delta-guidance">${DEV_SVG('<path d="M12 16v-4"/><path d="M12 8h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>')} ${escapeHtml(d.guidance || "")}</p>
          ${d.clients && d.clients.length ? `<div class="opp-clients"><strong>عملاء مطابقون (${d.clients.length}):</strong> ${d.clients.map((c) => `<span>${escapeHtml(c.area || "")} ${escapeHtml(c.type || "")} — تطابق ${c.matchScore}/100</span>`).join(" · ")}</div>` : ""}
          ${d.url ? `<a class="open-link" href="${escapeHtml(d.url)}" target="_blank" rel="noreferrer">فتح على ${escapeHtml(d.source || "الإعلان الأصلي")}</a>` : ""}
        </div>
      </article>`).join("")}` : "";
  const DELTA_ICONS = {
    "🆕": DEV_SVG('<path d="M5 12h14"/><path d="M13 5l7 7-7 7"/>'),
    "🗑️": DEV_SVG('<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6"/><path d="M14 11v6"/>'),
    "📉": DEV_SVG('<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>'),
  };
  root.innerHTML = stats
    + section(DELTA_ICONS["🆕"] + " فرص جديدة دخلت السوق", data.added || [], "delta-new")
    + section(DELTA_ICONS["🗑️"] + " فرص اختفت من السوق", data.removed || [], "delta-removed")
    + section(DELTA_ICONS["📉"] + " انخفاض الأسعار", data.priceDrops || [], "delta-drop");
}

function renderOppTier() {
  const root = $("oppList");
  if (!root || !oppState.data) return;
  // مرشّح المصدر ونوع الإعلان (مباشر/مكتب) خاص بتبويبات الفرص (الأفضل + الفئات الزمنية)
  const cardTiers = ["best", "daily", "weekly", "monthly", "yearly"];
  setOppSourceRowVisible(cardTiers.includes(oppState.tier));
  const bar = $("oppSourcesBar");
  if (bar) bar.hidden = true;
  if (oppState.tier === "clients") { renderClientsTab(root); updateOppTabCount(); return; }
  if (oppState.tier === "alerts") { renderAlertsTab(root); updateOppTabCount(); return; }
  if (oppState.tier === "history") { renderHistoryTab(root); updateOppTabCount(); return; }
  // التبويبات غير البطاقية (العرض والطلب / الجديد والمحذوف / الموجز الأسبوعي): أعد رسمها من
  // الحالة المخزنة. بدون هذا، «تحديث الفرص» أو تغيير أي فلتر أثناء وجودك عليها يُسقطها إلى
  // «لا توجد بيانات.» لأن tiers[] لا يحوي مفاتيحها — وإن لم تُحمل بعد، أعد جلبها من نقطتها.
  if (oppState.tier === "matching" && oppState.matching) { renderMatchingTab(root); updateOppTabCount(); return; }
  if (oppState.tier === "delta" && oppState.delta) { renderDeltaTab(root); updateOppTabCount(); return; }
  if (oppState.tier === "digest" && oppState.digest) { renderDigestTab(root); updateOppTabCount(); return; }
  if (oppState.tier === "matching" || oppState.tier === "delta" || oppState.tier === "digest") { loadOpportunityTab(oppState.tier); return; }
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
    updateOppTabCount();
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
    renderOppPlatformBar(pool);
    items = oppFilteredItems(pool);
    note = `أفضل الفرص على الإطلاق — مدمجة من كل الفئات الزمنية (يعرض ${items.length} من أصل ${pool.length}) مع شارة الفئة الأدق لكل فرصة`;
  } else {
    const tier = (oppState.data.tiers || {})[oppState.tier];
    if (!tier) {
      root.innerHTML = '<div class="empty">لا توجد بيانات.</div>';
      updateOppTabCount();
      return;
    }
    renderOppSourceCounts(tier.items || []);
    renderOppPlatformBar(tier.items || []);
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
  updateOppTabCount();
}

function renderOppMeta() {
  const updated = $("oppUpdated");
  if (updated && oppState.data) {
    const total = Number(oppState.data.totalListings || oppState.data.totalScored || 0);
    const scored = Number(oppState.data.totalScored || 0);
    const noOpp = Math.max(0, total - scored);
    updated.textContent = `آخر تحديث: ${oppState.data.generatedDate || ""} — ${scored} فرصة من أصل ${total} إعلان (${noOpp} بدون فرصة)`;
  }
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

async function loadOpportunities(forceRefresh = false) {
  const root = $("oppList");
  if (!root) return;
  const refreshBtn = $("oppRefreshBtn");
  if (forceRefresh) {
    root.innerHTML = '<div class="empty">جاري إعادة فحص كل المصادر الخارجية (قد يستغرق حتى دقيقة)...</div>';
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "جاري التحديث...";
    }
  } else {
    root.innerHTML = '<div class="empty">جاري تحميل أفضل الفرص...</div>';
  }
  try {
    oppState.data = await getJson(`/api/opportunities${forceRefresh ? "?refresh=1" : ""}`);
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "تحديث الفرص";
    }

    const allItems = Object.values(oppState.data.tiers || {}).flatMap((tier) => tier.items || []);
    fillOppSelect("oppGovFilter", allItems.map((item) => item.governorate));
    fillOppSelect("oppAreaFilter", allItems.map((item) => item.area));
    fillOppSelect("oppTypeFilter", allItems.map((item) => item.propertyType));

    renderOppMeta();
    renderOppTier();
    updateOppTabCount();
    // «تحديث الفرص» على تبويب غير بطاقي: أعد جلب نقطته بعد التحديث حتى لا يبقى
    // العرض والطلب / الجديد والمحذوف / الموجز على نسخة سابقة من الفرص.
    if (["matching", "delta", "digest"].includes(oppState.tier)) {
      loadOpportunityTab(oppState.tier);
    }
  } catch (err) {
    console.error(err);
    const refreshBtn = $("oppRefreshBtn");
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "تحديث الفرص";
    }
    root.innerHTML = `<div class="empty">تعذر تحميل الفرص: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadOpportunityTab(tier) {
  const root = $("oppList");
  if (!root) return;
  oppState.tier = tier;
  // التبويبات غير البطاقية (عملاء/تنبيهات/موجز/…) لا تعرض شريط مصادر الفرص
  const bar = $("oppSourcesBar");
  if (bar) bar.hidden = true;
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
      const [historyRes, outreachRes, priceTrendsRes] = await Promise.all([
        getJson("/api/opportunities/history"),
        getJson("/api/outreach/stats").catch(() => null),
        getJson("/api/price-trends").catch(() => null),
      ]);
      oppState.history = historyRes;
      oppState.outreach = outreachRes;
      // اللقطة بلا اتجاهات؟ الموقع المرفوع فقط (وضع ثابت بلا باك إند) يقرأ الجدول
      // حيًا مباشرة عبر REST — وفي الوضع الحي يعمل /api/price-trends فعلًا فلا نحتاج أي سقوط.
      oppState.priceTrends = (STATIC_SNAPSHOT_MODE && (!priceTrendsRes || !priceTrendsRes.rows || !priceTrendsRes.rows.length))
        ? (await fetchLivePriceTrends()) || priceTrendsRes
        : priceTrendsRes;
      renderHistoryTab(root);
    } else if (tier === "matching") {
      oppState.matching = await getJson("/api/market-matching");
      renderMatchingTab(root);
    } else if (tier === "delta") {
      oppState.delta = await getJson("/api/opportunity-delta");
      renderDeltaTab(root);
    }
    updateOppTabCount();
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
  // شريط «مصادر هذه النتائج»: فلترة البطاقات بالنقر على أي منصة (تفويض — الشرائح تُعاد بناؤها)
  const oppSourcesBar = $("oppSourcesBar");
  if (oppSourcesBar) {
    oppSourcesBar.addEventListener("click", (ev) => {
      const chip = ev.target.closest?.("[data-opp-platform]");
      if (!chip) return;
      oppState.platform = chip.dataset.oppPlatform || "";
      renderOppTier();
    });
  }
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
  on("toggleCustomSearchBtn", () => {
    switchMainTab("search");
    const panel = $("customSearchPanel");
    const input = $("chatInput");
    if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    if (input) setTimeout(() => input.focus(), 400);
  });
  on("boardRunSearchBtn", () => runBoardAnalysis());
  on("drillRunAnalysis", () => {
    const scope = boardDrilldown?.run || {};
    closeBoardDrilldown();
    runBoardAnalysis(scope);
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      const listing = $("boardListingModal");
      if (listing && !listing.hidden) {
        closeListingDetails();
        return;
      }
      const overlay = $("boardDrilldown");
      if (overlay && !overlay.hidden) closeBoardDrilldown();
    }
  });
  on("boardClearFiltersBtn", clearBoardSelections);
  on("govClearSelectionsBtn", clearBoardSelections);
  ["boardMetricFilter", "boardGovernorateFilter", "boardTransactionFilter", "boardPropertyTypeFilter", "boardListingModeFilter", "boardAreaFilter"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      if (id === "boardMetricFilter") {
        boardState.activeMetric = el.value || "movement";
        boardState.selectedCell = null;
      }
      if (id === "boardAreaFilter" && el.value.trim()) rememberRecentArea(el.value.trim());
      renderBoard();
    });
    el.addEventListener("change", () => {
      if (id === "boardMetricFilter") {
        boardState.activeMetric = el.value || "movement";
        boardState.selectedCell = null;
      }
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
      const rows = boardState.records.filter((row) => rowMatchesBoardFilters(row, false, false, true) && metricMatches(row, metric));
      openBoardDrilldown({
        title: `${boardMetricLabels[metric] || "حركة الدلال"}: ${countMetric(boardState.records.filter((row) => rowMatchesBoardFilters(row, false, false, true)), metric).toLocaleString("en-US")} إعلان`,
        sub: `${boardTextFromFilters()} — كل إعلان يحمل مصدره ورابطه الأصلي وأدلته.`,
        rows,
        run: { metric },
      });
      return;
    }
    const statBtn = ev.target.closest?.("[data-board-stat]");
    if (statBtn) {
      const stat = statBtn.dataset.boardStat || "total";
      const rows = boardStatRows(filteredBoardRows(), stat);
      const labels = { total: "إجمالي الاختيار", opportunities: "فرص ظاهرة", scored: "دخلت التقييم", evidence: "أدلة ومقارنات", priced: "أسعار معلنة", withSpace: "مساحات موثقة", direct: "مباشر", office: "مكتب" };
      openBoardDrilldown({
        title: `${labels[stat] || stat}: ${rows.length.toLocaleString("en-US")} إعلان`,
        sub: `${boardTextFromFilters()} — كل إعلان يحمل مصدره ورابطه الأصلي وأدلته.`,
        rows,
        run: boardDrillRunFromFilters(),
      });
      return;
    }
    const drillClose = ev.target.closest?.("[data-drill-close]");
    if (drillClose) {
      closeBoardDrilldown();
      return;
    }
    const modeBtn = ev.target.closest?.("[data-heat-mode]");
    if (modeBtn) {
      ev.preventDefault();
      setHeatmapMode(modeBtn.dataset.heatMode);
      return;
    }
    const watchBtn = ev.target.closest?.("[data-watch-area]");
    if (watchBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      const area = watchBtn.dataset.watchArea || "";
      const gov = watchBtn.dataset.watchGov || "";
      const gap = watchBtn.dataset.watchGap != null && watchBtn.dataset.watchGap !== "" ? Number(watchBtn.dataset.watchGap) : null;
      toggleWatchedArea(area, gov, gap);
      renderInsightsHeatmap(insightsState.data);
      return;
    }
    const heatCell = ev.target.closest?.("[data-heat-area]");
    if (heatCell) {
      const area = heatCell.dataset.heatArea || "";
      const gov = heatCell.dataset.heatGov || "";
      const areaFilter = $("boardAreaFilter");
      const govFilter = $("boardGovernorateFilter");
      if (areaFilter) areaFilter.value = area;
      if (govFilter && gov) govFilter.value = gov;
      boardState.activeMetric = "movement";
      boardState.selectedCell = { governorate: gov, area, metric: "movement" };
      const metricFilter = $("boardMetricFilter");
      if (metricFilter) metricFilter.value = "movement";
      renderBoard();
      runBoardAnalysis({ area, governorate: gov, metric: "movement" });
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
      boardState.activeMetric = metric;
      boardState.selectedCell = { governorate: gov, area: area || "", metric };
      const metricFilter = $("boardMetricFilter");
      const govFilter = $("boardGovernorateFilter");
      const areaFilter = $("boardAreaFilter");
      if (metricFilter) metricFilter.value = metric;
      if (govFilter) govFilter.value = gov;
      if (areaFilter) areaFilter.value = area;
      renderBoard();
      const rows = filteredBoardRows().filter((row) => {
        const rowGov = canonicalGovernorate(row.governorate) || "غير محددة";
        const targetGov = canonicalGovernorate(gov) || "غير محددة";
        if (gov && rowGov !== targetGov) return false;
        if (area && row.area !== area) return false;
        return metricMatches(row, metric);
      });
      const scopeLabel = [gov && gov !== "غير محددة" ? gov : "", area, boardMetricLabels[metric] || "حركة الدلال"].filter(Boolean).join(" · ");
      openBoardDrilldown({
        title: `${scopeLabel}: ${rows.length.toLocaleString("en-US")} إعلان`,
        sub: "كل إعلان يحمل مصدره ورابطه الأصلي وأدلته — اضغط «تشغيل نفس الفلاتر في التقييم» لتحليل النطاق كاملًا.",
        rows,
        run: { metric, governorate: gov, area },
      });
      return;
    }
    const totalBtn = ev.target.closest?.("[data-board-total-run]");
    if (totalBtn) {
      const metric = totalBtn.dataset.boardTotalRun || "movement";
      const rows = filteredBoardRows().filter((row) => metricMatches(row, metric));
      openBoardDrilldown({
        title: `الإجمالي · ${boardMetricLabels[metric] || "حركة الدلال"}: ${rows.length.toLocaleString("en-US")} إعلان`,
        sub: `${boardTextFromFilters()} — كل إعلان يحمل مصدره ورابطه الأصلي وأدلته.`,
        rows,
        run: { metric },
      });
      return;
    }
    const listingSource = ev.target.closest?.("[data-board-source]");
    if (listingSource) {
      ev.preventDefault();
      openSourceDrilldown(listingSource.dataset.boardSource || "");
      return;
    }
    const listingClose = ev.target.closest?.("[data-listing-close]");
    if (listingClose) {
      closeListingDetails();
      return;
    }
    const similarBtn = ev.target.closest?.("[data-listing-similar]");
    if (similarBtn) {
      const [area, propertyType] = String(similarBtn.dataset.listingSimilar || "|").split("|");
      const areaFilter = $("boardAreaFilter");
      const typeFilter = $("boardPropertyTypeFilter");
      if (areaFilter) areaFilter.value = area || "";
      if (typeFilter) typeFilter.value = propertyType || "";
      closeListingDetails();
      renderBoard();
      const rows = filteredBoardRows().filter((row) => (!area || row.area === area) && (!propertyType || row.propertyType === propertyType));
      openBoardDrilldown({
        title: `مشابهات: ${[area, propertyType].filter(Boolean).join(" · ")}`,
        sub: `${rows.length} إعلان بنفس المنطقة والنوع — كل إعلان يحمل مصدره ورابطه.`,
        rows,
        run: boardDrillRunFromFilters(),
      });
      return;
    }
    // أخيرًا: أي بطاقة إعلان (بدون أزرار داخلية) تفتح تفاصيل الإعلان في بوكس داخل الصفحة
    const listingCard = ev.target.closest?.("[data-board-listing]");
    if (listingCard && !ev.target.closest("a, button")) {
      openListingDetails(listingCard._row || null);
      return;
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

// ── عدّادات حجم المحتوى داخل أزرار التبويبات (تظهر قبل الدخول) ──
function setTabCount(id, count) {
  const el = $(id);
  if (!el) return;
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0) {
    el.textContent = "";
    return;
  }
  el.textContent = n > 999 ? "999+" : String(n);
}

function updateOppTabCount() {
  // عدّاد تبويب «أفضل الفرص» = عدد الفرص من إجمالي الإعلانات المفحوصة
  // «208/415» تعني 208 فرصة مقيّمة من أصل 415 إعلانًا — مع تلميح يوضح «بدون فرصة».
  if (!oppState.data) {
    setTabCount("tabCountOpp", 0);
    return;
  }
  const el = $("tabCountOpp");
  if (!el) return;
  const scored = Number(oppState.data.totalScored || 0);
  if (scored <= 0) {
    el.textContent = "";
    return;
  }
  const total = Number(oppState.data.totalListings || scored);
  const noOpp = Math.max(0, total - scored);
  el.textContent = `${scored}/${total}`;
  el.title = `${scored} فرصة من أصل ${total} إعلان (${noOpp} بدون فرصة)`;
}

// ── التبويبات الرئيسية: يعرض قسمًا واحدًا في كل مرة بدل تكديس كل الأقسام تحت بعض ──
function switchMainTab(name) {
  document.querySelectorAll(".main-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mainTab === name);
  });
  document.querySelectorAll("[data-main-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.mainPanel === name);
  });
  if (name === "opportunities") loadOpportunities(false);
  if (name === "board") loadDashboardBoard();
  if (name === "insights") loadInsights();
  if (name === "developments") loadDevelopments();
}

// زر «اسأل المساعد» العائم: يقفز للبحث/الشات ويُركز الحقل فورًا من أي قسم
const chatFab = document.getElementById("chatFab");
if (chatFab) {
  chatFab.addEventListener("click", () => {
    switchMainTab("search");
    const input = document.getElementById("chatInput");
    if (input) input.focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

// ── تطورات السوق العقاري (وكيل الاكتشاف اليومي) ──────────────────────────
const developmentsState = { data: null, loaded: false };

// أيقونات SVG خطية بأسلوب موحد مع باقي الواجهة (بدل الإيموجي)
const DEV_SVG = (paths) =>
  `<svg class="tab-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
const DEVELOPMENT_CATEGORY_ICONS = {
  "سوق عقاري": DEV_SVG('<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>'),
  "مؤشرات رسمية": DEV_SVG('<path d="M3 21h18"/><path d="M5 21V7"/><path d="M9 21V3"/><path d="M13 21v-9"/><path d="M17 21v-5"/>'),
  "تنظيم وقانون": DEV_SVG('<path d="M12 3v18"/><path d="M5 7.5 12 3l7 4.5"/><path d="M7 21h10"/><path d="M8 7.5 12 10l4-2.5"/><path d="M5 7.5v6"/><path d="M19 7.5v6"/>'),
  "تمويل عقاري": DEV_SVG('<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>'),
  "مشاريع وتطوير": DEV_SVG('<path d="M2 20h20"/><path d="M4 20V9l8-5 8 5v11"/><path d="M9 20v-6h6v6"/>'),
};

function developmentDateLabel(published) {
  if (!published) return "";
  const match = String(published).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(published).slice(0, 10);
}

async function loadDevelopments() {
  if (developmentsState.loaded) return;
  const root = $("developmentsRoot");
  if (root) root.innerHTML = '<div class="empty">جاري تحميل تطورات السوق...</div>';
  try {
    developmentsState.data = await getJson("/api/developments");
    developmentsState.loaded = true;
    renderDevelopments();
  } catch (err) {
    console.error(err);
    if (root) root.innerHTML = `<div class="empty">تعذر تحميل تطورات السوق: ${escapeHtml(err.message)}</div>`;
  }
}

function renderDevelopments() {
  const data = developmentsState.data || {};
  const items = data.developments || [];
  const root = $("developmentsRoot");
  if (!root) return;
  const meta = $("developmentsMeta");
  const stateEl = $("developmentsAgentState");
  const sourcesEl = $("developmentsSources");

  if (meta) {
    const generated = data.generatedAt ? ` · آخر اكتشاف: ${String(data.generatedAt).slice(0, 16).replace("T", " ")}` : "";
    meta.textContent = `${items.length} تطور${generated}`;
  }

  if (!items.length) {
    root.innerHTML = '<div class="empty">لا توجد تطورات بعد — يعمل وكيل الاكتشاف تلقائيًا مع التحديث اليومي (06:00) لجمع آخر أخبار السوق.</div>';
  } else {
    const byCategory = {};
    for (const item of items) {
      const cat = item.category || "سوق عقاري";
      (byCategory[cat] ||= []).push(item);
    }
    root.innerHTML = Object.keys(byCategory).map((cat) => `
      <div class="developments-category">
        <h3 class="developments-category-title">${DEVELOPMENT_CATEGORY_ICONS[cat] || DEV_SVG('<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/>')} ${escapeHtml(cat)} <span class="developments-category-count">${byCategory[cat].length}</span></h3>
        <div class="developments-cards">
          ${byCategory[cat].map((item) => `
            <a class="development-card" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">
              <div class="development-card-top">
                <span class="development-source">${escapeHtml(item.source_name || item.source || "")}</span>
                ${developmentDateLabel(item.published) ? `<time class="development-date">${developmentDateLabel(item.published)}</time>` : ""}
              </div>
              <h4>${escapeHtml(item.title)}</h4>
              ${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}
              <span class="development-open">فتح المصدر ↗</span>
            </a>
          `).join("")}
        </div>
      </div>
    `).join("");
  }

  if (stateEl) {
    const note = data.note || "";
    const status = data.status || "";
    if (note) {
      stateEl.className = `source-summary-bar ${status === "success" ? "tone-ok" : "tone-warn"}`;
      stateEl.innerHTML = `${DEV_SVG('<circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 1.9.7 3.7 1.9 5.1L12 22l6.1-6.9A8 8 0 0 0 20 10a8 8 0 0 0-8-8Z"/>')} وكيل الاكتشاف: <strong>${escapeHtml(note)}</strong>`;
    } else {
      stateEl.innerHTML = `${DEV_SVG('<circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 1.9.7 3.7 1.9 5.1L12 22l6.1-6.9A8 8 0 0 0 20 10a8 8 0 0 0-8-8Z"/>')} وكيل الاكتشاف: لم يُشغَّل بعد — يعمل تلقائيًا مع التحديث اليومي (06:00).`;
    }
  }

  if (sourcesEl) {
    const sources = data.sources || [];
    sourcesEl.innerHTML = sources.length
      ? `<div class="source-grid">${sources.map((s) => `
        <div class="source-card ${s.status === "success" ? "source-ok" : "source-muted"}">
          <h4>${escapeHtml(s.name)}</h4>
          <p class="source-meta">${escapeHtml(s.fetchMethod || "")} · ${escapeHtml(s.note || "")}</p>
          <p class="source-meta">${escapeHtml(s.endpoint || "")}</p>
        </div>
      `).join("")}</div>`
      : '<div class="empty small">لا توجد بيانات مصادر في هذه اللقطة.</div>';
  }

  const countEl = $("tabCountDevelopments");
  if (countEl) countEl.textContent = items.length ? String(items.length) : "";
}

function bindMainTabs() {
  document.querySelectorAll(".main-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchMainTab(btn.dataset.mainTab));
  });
}

// ── محاكي صفقة الاستثمار: سعر الشراء + الترميم + الإيجار المتوقع ← العائد وفترة الاسترداد ──
function simNumbers() {
  const buy = Number($("simBuyPrice")?.value || 0);
  const renov = Number($("simRenovCost")?.value || 0);
  const rent = Number($("simRent")?.value || 0);
  const capital = buy + renov;
  const annual = rent * 12;
  return { buy, renov, rent, capital, annual };
}

function updateSimulator() {
  const { capital, annual } = simNumbers();
  const yieldEl = $("simYield");
  const paybackEl = $("simPayback");
  const capitalEl = $("simCapital");
  const incomeEl = $("simIncome");
  const noteEl = $("simNote");
  if (!yieldEl || !paybackEl) return;
  if (capital <= 0 || annual <= 0) {
    yieldEl.textContent = "—";
    paybackEl.textContent = "—";
    capitalEl.textContent = capital > 0 ? formatMoney(capital) : "—";
    incomeEl.textContent = annual > 0 ? formatMoney(annual) : "—";
    if (noteEl) noteEl.textContent = "أدخل سعر الشراء وتكلفة الترميم والإيجار المتوقع شهريًا — يُحسب العائد السنوي وفترة الاسترداد فورًا.";
    return;
  }
  const pct = (annual / capital) * 100;
  const years = capital / annual;
  const yearsInt = Math.floor(years);
  const months = Math.round((years - yearsInt) * 12);
  const paybackText = yearsInt >= 1
    ? `${yearsInt} سنة و ${months} شهر`
    : `${months} شهر`;
  yieldEl.textContent = `${pct.toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  yieldEl.className = `sim-value ${pct >= 6 ? "yield-high" : pct >= 4 ? "yield-mid" : "yield-low"}`;
  paybackEl.textContent = paybackText;
  capitalEl.textContent = formatMoney(capital);
  incomeEl.textContent = formatMoney(annual);
  if (noteEl) {
    const advice = pct >= 6
      ? "عائد جيد يغطي التمويل والرسوم عادةً — فرصة استثمارية قوية."
      : pct >= 4
        ? "عائد مقبول ضمن متوسط السوق الكويتي."
        : "عائد منخفض — راجع سعر الشراء أو الإيجار المتوقع قبل الإقرار.";
    noteEl.textContent = `${advice} الحساب: (${formatMoney(annual)} ÷ ${formatMoney(capital)}) × 100 = ${pct.toLocaleString("en-US", { maximumFractionDigits: 2 })}%.`;
  }
}

function prefillSimulator() {
  const report = state.report;
  if (!report || !(report.results || []).length) {
    const noteEl = $("simNote");
    if (noteEl) noteEl.textContent = "لا توجد نتائج بعد — شغّل بحثًا أولًا ثم عُد لتفعيل «تعبئة من أفضل نتيجة».";
    return;
  }
  // أفضل نتيجة بيع (لأن المحاكي يستثمر في شراء): السعر = سعر الشراء
  const saleTop = (report.results || []).find((item) => !item.rental && item.price);
  const buyField = $("simBuyPrice");
  if (saleTop && buyField) buyField.value = Math.round(Number(saleTop.price));
  // الإيجار المتوقع: وسيط إيجارات نفس منطقة أفضل نتيجة إن وُجدت نتائج إيجار لها
  const topArea = (saleTop || report.results[0] || {}).area;
  const rents = (report.results || [])
    .filter((item) => item.rental && item.price && (!topArea || normalizeArabic(item.area) === normalizeArabic(topArea)))
    .map((item) => Number(item.price));
  const rentField = $("simRent");
  let rentMedian = null;
  if (rents.length) {
    const sorted = rents.slice().sort((a, b) => a - b);
    rentMedian = sorted[Math.floor(sorted.length / 2)];
    rentField.value = Math.round(rentMedian);
  }
  updateSimulator();
  // تُكتب رسالة التعبئة بعد الحساب حتى لا تُستبدل بنص النصيحة
  const noteEl = $("simNote");
  if (noteEl) {
    const current = noteEl.textContent;
    noteEl.textContent = saleTop
      ? `عبّأت من أفضل نتيجة بيع (${saleTop.code}): سعر الشراء ${formatMoney(saleTop.price)}${rentMedian ? ` والإيجار من وسيط إيجارات المنطقة (${formatMoney(rentMedian)}/شهر)` : " — عدّل الإيجار المتوقع يدويًا"}. ${current}`
      : "لا توجد نتيجة بيع بسعر — أدخل الأرقام يدويًا.";
  }
}

function initDealSimulator() {
  for (const id of ["simBuyPrice", "simRenovCost", "simRent"]) {
    const el = $(id);
    if (el) el.addEventListener("input", updateSimulator);
  }
  const prefill = $("simPrefill");
  if (prefill) prefill.addEventListener("click", prefillSimulator);
}

// ترتيب سجلات اللوحة (الأحدث / السعر الأعلى / الأقل / المنطقة أبجديا)
function sortBoardRows(rows) {
  const sort = $("boardSortFilter")?.value || "newest";
  const sorted = [...rows];
  if (sort === "price_desc") sorted.sort((a, b) => (Number(b.price) || 0) - (Number(a.price) || 0));
  else if (sort === "price_asc") sorted.sort((a, b) => (Number(a.price) || 0) - (Number(b.price) || 0));
  else if (sort === "area") sorted.sort((a, b) => String(a.area || "").localeCompare(String(b.area || ""), "ar"));
  else sorted.sort((a, b) => String(b.publishedDate || "").localeCompare(String(a.publishedDate || "")));
  return sorted;
}


async function boot() {
  initTheme();
  initCardReveal();
  bind();
  bindMainTabs();
  switchMainTab("search");
  bindOppEvents();
  populateAdvancedOptions();
  initAreaChips();
  initDealSimulator();
  // تفعيل أزرار تبديل الخريطة الحرارية وحالة الوضع المحفوظ عند الإقلاع
  // (النقر عبر المعالج المفوض [data-heat-mode] في bind)
  document.querySelectorAll(".heatmap-mode-switch .mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.heatMode === heatmapMode);
  });
  syncHeatmapLegends();
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
    // إجمالي كل المصادر: الفريج المحلي + حصاد المواقع الخارجية — لا نكتفي بعدد الفريج وحده.
    const total = Number(health.totalRecords || health.records || 0);
    const local = Number(health.localRecords ?? health.records ?? 0);
    const external = Number(health.externalRecords || 0);
    // القاعدة مضبوطة فعلًا في كل الحالات: المحلي يتصل حيًا، والموقع المنشور
    // يُبنى من القاعدة الحية ويُحدَّث تلقائيًا يوميًا — فلا نعرض «غير مضبوطة» أبدًا.
    const dbState = health.supabase ? "القاعدة: متصلة" : health.staticSnapshot ? "القاعدة: محدثة يوميًا" : "القاعدة: محدثة";
    const statusEl = $("healthStatus");
    if (statusEl) {
      const breakdown = [`الفريج ${local}`, ...(external > 0 ? [`المواقع الخارجية ${external}`] : [])].join(" + ");
      const bySource = (health.bySource || []).map((s) => `${s.source}: ${s.count}`).join(" · ");
      statusEl.title = `تفصيل البيانات — ${breakdown}${bySource ? ` · ${bySource}` : ""}`;
      statusEl.dataset.snapshotLocal = String(local);
      setStatus(`البيانات: ${total} إعلان من كل المصادر (${breakdown}) | ${dbState} | ${aiStatus}`);
    } else {
      setStatus(`البيانات: ${total} إعلان من كل المصادر | ${dbState} | ${aiStatus}`);
    }
    // الموقع المنشور: محاولة قراءة مباشرة من القاعدة الحية (مفتاح anon + RLS للجداول العامة)
    // ليعرض أرقامًا حية فعلًا — مع السقوط الآمن للقطة إن تعذر الاتصال.
    if (STATIC_SNAPSHOT_MODE) applyLiveDbCounts(statusEl);
  } catch {
    setStatus("تعذر فحص البيانات");
  }
}

boot();

