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
  simpleMode: false,
  simpleFilters: {}, // { area: Set, type: Set, tx: Set } — فلاتر النقر السريعة
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
  govView: "grid", // شبكة كروت مكدسة أو جدول مضغوط — محفوظ بين الجلسات
};

// مفتاح موحّد لمبدّل شبكة/جدول: لوحة السوق وأفضل الفرص يشتركان في نفس التفضيل المحفوظ
const viewModeKey = "alforaij_view_mode_v1";
try {
  // ترحيل من المفتاح القديم الخاص بلوحة السوق إن وُجد
  if (!localStorage.getItem(viewModeKey)) {
    const legacy = localStorage.getItem("alforaij_board_gov_view_v1");
    if (legacy === "table" || legacy === "grid") localStorage.setItem(viewModeKey, legacy);
  }
  const savedView = localStorage.getItem(viewModeKey);
  if (savedView === "table" || savedView === "grid") boardState.govView = savedView;
} catch { /* تجاهل — نبقى على الوضع الافتراضي */ }

// تبديل وضع العرض (شبكة/جدول) — يُطبَّق على اللوحة والفرص معًا ويُحفظ في مفتاح واحد
function setViewMode(mode) {
  const next = mode === "table" ? "table" : "grid";
  boardState.govView = next;
  oppState.view = next;
  try {
    localStorage.setItem(viewModeKey, next);
  } catch { /* تجاهل — يبقى وضع الجلسة الحالية */ }
  syncViewModeButtons();
}

// مزامنة أزرار المبدّل في كل الأماكن (لوحة السوق + أفضل الفرص) مع الوضع الحالي
function syncViewModeButtons() {
  const mode = oppState.view;
  document.querySelectorAll("[data-gov-view], [data-opp-view]").forEach((btn) => {
    const mine = btn.dataset.govView || btn.dataset.oppView;
    btn.classList.toggle("active", mine === mode);
  });
}

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
  "/api/platform-dates": "platform-dates.json",
  "/api/platform-intelligence": "platform-intelligence.json",
  "/api/analytics-dashboard": "analytics-dashboard.json",
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

function apiErrorFromText(text, status, context = "") {
  let message = String(text || "").trim();
  const trimmed = message.trim();
  if (trimmed.startsWith("{")) {
    try {
      const data = JSON.parse(trimmed);
      message = data.detail || data.message || data.error || message;
    } catch {
      // Keep raw text below.
    }
  }
  if (!message) message = `HTTP ${status || ""}`.trim();
  const err = new Error(context ? `${message} (${context})` : message);
  err.status = status;
  return err;
}

async function getJson(path) {
  if (STATIC_SNAPSHOT_MODE) return fetchStaticJson(path);
  try {
    const response = await fetch(apiUrl(path));
    if (!response.ok) throw apiErrorFromText(await response.text(), response.status, path);
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

// دلو موقع سجل اللوحة: محافظة معروفة، أو «غير محددة» (تحمل اسم منطقة لكن محافظتها
// غير محددة في البيانات)، أو «بلا موقع» (لا منطقة ولا محافظة — الإعلان لا يذكر موقعًا).
// فصل «بلا موقع» في صف مستقل يمنع خلط السجلات بلا أي معلومة موقع مع «غير محددة»
// التي تعني منطقة معروفة بمحافظة ناقصة.
function boardLocationBucket(row) {
  const gov = canonicalGovernorate(row.governorate);
  if (gov) return gov;
  return row.area ? "غير محددة" : "بلا موقع";
}

// سبب كل دلو — يُعرض في تلميح الصف حتى يفهم الموظف لماذا انفصلت هذه السجلات
const LOCATION_BUCKET_TIPS = {
  "بلا موقع": "«بلا موقع»: إعلانات لا تذكر منطقة ولا محافظة في نصها ولا رابطها (مثل «مطلوب مكاتب للايجار» أو إعلانات بعناوين عامة) — لا يمكن تحديد موقعها بصدق من البيانات المتاحة.",
  "غير محددة": "«غير محددة»: إعلانات تحمل اسم منطقة معروفة لكن محافظتها غير محددة في البيانات المصدر — المنطقة معروفة والمحافظة ناقصة.",
};

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
  if (!ignoreGovernorate && filters.governorate && boardLocationBucket(row) !== canonicalGovernorate(filters.governorate)) return false;
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

function chatGuidanceAnswer(report) {
  return String((report && report.chatGuidance && report.chatGuidance.answer) || "").trim();
}

function setStatus(text) {
  const el = $("healthStatus");
  if (el) el.textContent = text;
}

// الموقع المنشور (وضع ثابت): قراءة مباشرة من قاعدة البيانات الحية عبر مفتاح anon العام
// وجداول RLS العامة — فيعرض الترويسة أرقامًا حية فعلًا بدل أرقام اللقطة، مع سقوط آمن.
async function liveDbConfig() {
  try {
    // getJson: على الخادم الحي تجلب /api/live-db الفعلية (لا 404 في نسخة نظيفة بلا
    // لقطة)، وعلى الموقع المنشور تسقط على اللقطة الثابتة — نفس النمط المحروس.
    const cfg = await getJson("/api/live-db");
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
    const cfg = await getJson("/api/live-db");
    if (!cfg || !cfg.url || !cfg.anonKey) return;
    const headers = { apikey: cfg.anonKey, Authorization: `Bearer ${cfg.anonKey}` };
    const base = cfg.url.replace(/\/$/, "");
    const [market, opps] = await Promise.all([
      fetch(`${base}/rest/v1/market_listings?select=count`, { headers }).then((r) => r.json()),
      // عدد الفرص الحقيقي: آخر لقطة فرص (total_scored) — لا عدد صفوف اللقطات المتراكمة
      fetch(`${base}/rest/v1/opportunities?select=total_scored,total_listings&order=generated_at.desc&limit=1`, { headers }).then((r) => r.json()),
    ]);
    const marketN = Number((market[0] || {}).count || 0);
    const oppRow = Array.isArray(opps) && opps[0] ? opps[0] : null;
    const scoredN = Number((oppRow || {}).total_scored || 0);
    const listedN = Number((oppRow || {}).total_listings || 0);
    if (!marketN) return;
    const el = statusEl || $("healthStatus");
    if (!el) return;
    // إعلانات الفريج المحلية من اللقطة (مصدرها ملف محلي لا جدول القاعدة)
    const localN = Number(el.dataset.snapshotLocal || 0);
    const breakdown = [`الفريج ${localN}`, `المواقع الخارجية ${marketN}`].join(" + ");
    const oppsText = scoredN > 0 ? ` | ${scoredN.toLocaleString("en-US")} فرصة مقيّمة (من ${listedN.toLocaleString("en-US")} مفحوصة)` : "";
    el.textContent = `البيانات: ${localN + marketN} إعلان مباشر من القاعدة (${breakdown}) | القاعدة: متصلة${oppsText}`;
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

const CLIENTS_KEY = "alforaij_clients_v1";

function staticSaveClient(payload) {
  const phone = String(payload.phone || "").trim();
  if (!phone) return { status: "error", detail: "رقم الهاتف مطلوب" };
  let clients = [];
  try {
    clients = JSON.parse(localStorage.getItem(CLIENTS_KEY) || "[]");
  } catch { clients = []; }
  const existing = clients.findIndex((c) => c.phone === phone);
  const code = existing >= 0 ? clients[existing].code : `LEAD-${Date.now().toString(36).slice(-4).toUpperCase()}`;
  const entry = {
    code,
    phone,
    area: payload.area || "",
    type: payload.type || "",
    price: payload.price || "",
    note: payload.note || "",
    createdAt: new Date().toISOString(),
  };
  if (existing >= 0) {
    clients[existing] = { ...clients[existing], ...entry };
  } else {
    clients.unshift(entry);
  }
  localStorage.setItem(CLIENTS_KEY, JSON.stringify(clients.slice(0, 200)));
  return { status: existing >= 0 ? "updated" : "added", code };
}

async function postJson(path, payload) {
  if (STATIC_SNAPSHOT_MODE && path === "/api/analyze") return staticAnalyzeReport(payload);
  // حفظ عميل محتمل في وضع الثابت (localStorage) عند عدم وجود خادم API
  if (STATIC_SNAPSHOT_MODE && path === "/api/clients") return staticSaveClient(payload);
  try {
    const response = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw apiErrorFromText(await response.text(), response.status, path);
    return await readJsonResponse(response, path);
  } catch (err) {
    // التحليل الثابت مسموح فقط في STATIC_SNAPSHOT_MODE أعلاه. إذا رد API فعلي
    // برفض صلاحية أو حد خطة فلا نخفي السبب بتقرير لقطة صفرية.
    if (path === "/api/clients") return staticSaveClient(payload);
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

// التغير اليومي لكل مقياس: آخر 24 ساعة مقابل الـ24 ساعة التي قبلها — من طوابع
// السجلات الفعلية (fetchedAt للمواقع الخارجية، publishedDate للمحلي) بدون أي تخزين.
function metricDailyDelta(rows, metric) {
  const HOUR = 3600 * 1000;
  const now = Date.now();
  let today = 0;
  let prev = 0;
  for (const row of rows || []) {
    if (!metricMatches(row, metric)) continue;
    const raw = String(row.fetchedAt || row.publishedDate || "").trim();
    if (!raw) continue;
    const t = Date.parse(raw);
    if (Number.isNaN(t)) continue;
    const age = now - t;
    if (age <= HOUR * 24) today += 1; // آخر 24 ساعة (أو مستقبلي بفارق توقيت بسيط)
    else if (age <= HOUR * 48) prev += 1; // الـ24 ساعة التي قبلها
  }
  return { delta: today - prev, today, prev };
}

// نص شارة التغير اليومي الموحّد: +N / −N / ±0
function formatDailyDelta(d) {
  return d.delta > 0 ? `+${d.delta}` : d.delta < 0 ? `−${Math.abs(d.delta)}` : "±0";
}

function renderBoardMetricCards(rows) {
  const root = $("boardMetricCards");
  if (!root) return;
  const activeMetric = boardFilterValues().metric || "movement";
  root.innerHTML = Object.entries(boardMetricLabels).map(([key, label]) => {
    const count = countMetric(rows, key);
    const active = key === activeMetric ? " active" : "";
    const d = metricDailyDelta(rows, key);
    const deltaClass = d.delta > 0 ? " up" : d.delta < 0 ? " down" : " flat";
    const deltaText = d.delta > 0 ? `+${d.delta}` : d.delta < 0 ? `−${Math.abs(d.delta)}` : "±0";
    const pct = d.prev > 0 ? ` (${d.delta > 0 ? "+" : ""}${Math.round((d.delta / d.prev) * 100)}%)` : "";
    const tip = `التغير اليومي: ${d.today} إعلان في آخر 24 ساعة مقابل ${d.prev} في الـ24 ساعة قبلها — ${deltaText}${pct}`;
    return `
      <button class="board-metric-card${active}" type="button" data-board-metric="${escapeHtml(key)}" title="${escapeHtml(tip)}">
        <span>${escapeHtml(label)}</span>
        <strong>${count.toLocaleString("en-US")}</strong>
        <em class="board-metric-delta${deltaClass}">${escapeHtml(deltaText)}</em>
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
    const rowGov = boardLocationBucket(row);
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
  const governorates = uniqueValues(rows.map((row) => boardLocationBucket(row)));
  const activeMetric = boardState.activeMetric || "movement";
  const axisPill = $("govAxisPill");
  if (axisPill) axisPill.textContent = `المحور: ${boardMetricLabels[activeMetric] || "حركة الدلال"}`;
  // مزامنة مبدّل شبكة/جدول وحالة العرض المحفوظة (قبل فحص البيانات الفارغة)
  // ملاحظة: لا نضع data-gov-view على حاوية الكروت — سيصطدم بفحص closest("[data-gov-view]")
  // في معالج النقرات ويمنع الأرقام من فتح الدرج التفصيلي.
  syncViewModeButtons();
  // زرا تصدير/نسخ CSV خاصان بالوضع المضغوط (جدول) — يصدّران الأرقام الحالية للمحافظات والمناطق
  const exportBtn = $("govExportCsvBtn");
  if (exportBtn) exportBtn.hidden = boardState.govView !== "table";
  const copyBtn = $("govCopyBtn");
  if (copyBtn) copyBtn.hidden = boardState.govView !== "table";
  if (!governorates.length) {
    root.innerHTML = '<div class="gov-empty">لا توجد بيانات حسب الفلاتر الحالية.</div>';
    return;
  }
  const metrics = ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"];
  const totals = metrics.map((metric) => ({ metric, count: countMetric(rows, metric) }));
  if (boardState.govView === "table") {
    root.innerHTML = renderGovTable(rows, governorates, activeMetric, totals);
    return;
  }
  const metricPill = (cell, extraCls) => `
    <button class="metric-pill${extraCls}" type="button" data-board-gov="${escapeHtml(cell.gov)}" ${cell.area ? `data-board-area-run="${escapeHtml(cell.area)}"` : ""} data-board-metric-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"} title="${escapeHtml(boardMetricLabels[cell.metric] || "")}">
      <span>${escapeHtml(boardMetricLabels[cell.metric] || "")}</span>
      <b>${cell.count.toLocaleString("en-US")}</b>
    </button>`;
  const html = [];
  for (const governorate of governorates) {
    const govRows = rows.filter((row) => boardLocationBucket(row) === governorate);
    const cells = metricCells(rows, governorate);
    const expanded = boardState.expandedGovernorates.has(governorate);
    const sel = boardState.selectedCell;
    const areaCount = uniqueValues(govRows.map((row) => row.area).filter(Boolean)).length;
    const bucketTip = LOCATION_BUCKET_TIPS[governorate] || "";
    const axisCell = cells.find((c) => c.metric === activeMetric) || cells[0] || { metric: "movement", count: 0 };
    html.push(`
      <section class="gov-card${expanded ? " expanded" : ""}" data-board-governorate="${escapeHtml(governorate)}">
        <header class="gov-card-head">
          ${areaCount ? `<button class="gov-toggle" type="button" data-board-toggle-gov="${escapeHtml(governorate)}" aria-label="${expanded ? "طي" : "فتح"} مناطق ${escapeHtml(governorate)}">${expanded ? "▲" : "▼"}</button>` : ""}
          <strong class="gov-card-name"${bucketTip ? ` title="${escapeHtml(bucketTip)}"` : ""}>${escapeHtml(governorate)}</strong>
          <button class="gov-areas-badge" type="button" data-board-toggle-gov="${escapeHtml(governorate)}" title="${areaCount} منطقة — ${govRows.length} إعلان${bucketTip ? ` — ${bucketTip}` : ""}">
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

// ── دوال التصميم الاحترافي الجديد ────────────────────────────────────────
// شريط الملخص السريع أعلى قسم المحافظات
function renderGovSummaryBar(rows, governorates, activeMetric) {
  const bar = $("govSummaryBar");
  if (!bar) return;
  const totalAds = rows.length;
  const totalAreas = uniqueValues(rows.map((r) => r.area).filter(Boolean)).length;
  const totalOpportunities = countMetric(rows, "opportunities");
  const totalPriced = rows.filter((r) => Number(r.price) > 0).length;
  bar.innerHTML = `
    <div class="gov-summary-item">
      <span class="summary-icon">🏢</span>
      <div>
        <div class="summary-value">${totalAds.toLocaleString("en-US")}</div>
        <div class="summary-label">إجمالي الإعلانات</div>
      </div>
    </div>
    <div class="gov-summary-item">
      <span class="summary-icon">📍</span>
      <div>
        <div class="summary-value">${governorates.length}</div>
        <div class="summary-label">محافظة</div>
      </div>
    </div>
    <div class="gov-summary-item">
      <span class="summary-icon">🏘️</span>
      <div>
        <div class="summary-value">${totalAreas}</div>
        <div class="summary-label">منطقة</div>
      </div>
    </div>
    <div class="gov-summary-item">
      <span class="summary-icon">💰</span>
      <div>
        <div class="summary-value">${totalOpportunities}</div>
        <div class="summary-label">فرصة محسوبة</div>
      </div>
    </div>
    <div class="gov-summary-item">
      <span class="summary-icon">🏷️</div>
      <div>
        <div class="summary-value">${totalPriced}</div>
        <div class="summary-label">مع سعر</div>
      </div>
    </div>
  `;
}

// عرض المناطق عند توسيع المحافظة (التصميم الجديد)
function renderGovAreasExpanded(rows, governorate, govRows, sel, activeMetric) {
  const areaGroups = {};
  for (const row of govRows) {
    if (!row.area) continue;
    const key = normalizeArabic(row.area);
    if (!(key in areaGroups)) areaGroups[key] = row.area;
  }
  const areas = Object.values(areaGroups).sort((a, b) => String(a).localeCompare(String(b), "ar"));
  if (!areas.length) return "";
  const metrics = ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"];
  return `
    <div class="gov-card-pro-areas">
      <div class="gov-areas-header">
        <h4>📍 المناطق (${areas.length})</h4>
      </div>
      <div class="gov-areas-grid">
        ${areas.map((area) => {
          const areaRows = govRows.filter((row) => row.area === area);
          const areaCells = metricCells(rows, governorate, area);
          const axisCell = areaCells.find((c) => c.metric === activeMetric) || areaCells[0];
          const delta = metricDailyDelta(areaRows, activeMetric);
          const deltaCls = delta.delta > 0 ? "up" : delta.delta < 0 ? "down" : "flat";
          return `
            <div class="gov-area-item" data-board-area="${escapeHtml(area)}">
              <div class="area-info">
                <span class="area-name">${escapeHtml(area)}</span>
                <span class="area-count">${areaRows.length} إعلان</span>
              </div>
              <div class="area-stats">
                ${areaCells.slice(0, 3).map((cell) => `
                  <button class="gov-area-pill${activeMetric === cell.metric ? " axis" : ""}" type="button" data-board-gov="${escapeHtml(governorate)}" data-board-area-run="${escapeHtml(area)}" data-board-metric-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"} title="${escapeHtml(boardMetricLabels[cell.metric] || "")}">
                    ${cell.count.toLocaleString("en-US")}
                  </button>`).join("")}
              </div>
            </div>`;
        }).join("")}
      </div>
    </div>`;
}

// عرض الإعلانات المرتبطة بالاختيار
function renderGovLinkedAds(governorate, area, metric) {
  const container = $("govLinkedAds");
  const grid = $("govLinkedAdsGrid");
  const countEl = $("govLinkedAdsCount");
  if (!container || !grid) return;
  if (!governorate) {
    container.hidden = true;
    return;
  }
  // جلب الإعلانات المرتبطة
  const rows = boardState.records.filter((row) => {
    const loc = boardLocationBucket(row);
    if (loc !== governorate) return false;
    if (area && row.area !== area) return false;
    return true;
  });
  // ترتيب حسب المقياس النشط
  const sorted = rows.sort((a, b) => {
    const aVal = metric === "movement" ? (a.movement || 0) : metric === "opportunities" ? (a.opportunityScore || 0) : metric === "saleOffers" ? (a.price || 0) : 0;
    const bVal = metric === "movement" ? (b.movement || 0) : metric === "opportunities" ? (b.opportunityScore || 0) : metric === "saleOffers" ? (b.price || 0) : 0;
    return bVal - aVal;
  }).slice(0, 12); // أول 12 إعلان
  if (!sorted.length) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  countEl.textContent = `${sorted.length} من ${rows.length} إعلان`;
  grid.innerHTML = sorted.map((row) => {
    const title = row.title || row.description || "إعلان عقاري";
    const price = row.price ? `${Number(row.price).toLocaleString("en-US")} د.ك` : "بدون سعر";
    const areaName = row.area || "";
    const source = row.source || "";
    const score = row.opportunityScore ? `${Math.round(row.opportunityScore)}%` : "";
    const link = row.url || row.originalUrl || "#";
    return `
      <div class="gov-linked-ad-card">
        <span class="ad-title">${escapeHtml(title.substring(0, 80))}${title.length > 80 ? "..." : ""}</span>
        <div class="ad-meta">
          <span class="ad-pill price">💰 ${escapeHtml(price)}</span>
          ${areaName ? `<span class="ad-pill area">📍 ${escapeHtml(areaName)}</span>` : ""}
          ${source ? `<span class="ad-pill source">🌐 ${escapeHtml(source)}</span>` : ""}
          ${score ? `<span class="ad-pill score">⭐ ${score}</span>` : ""}
        </div>
        <a class="ad-link" href="${escapeHtml(link)}" target="_blank" rel="noreferrer">فتح الإعلان ←</a>
      </div>`;
  }).join("");
}

// الجدول المضغوط لنفس أرقام كروت المحافظات — نفس معالجات النقر (فتح/درج تفاصيل)
// مع صف مدمج قابل للتوسيع يكشف مناطق كل محافظة.
function renderGovTable(rows, governorates, activeMetric, totals) {
  const metrics = ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"];
  const sel = boardState.selectedCell;
  const numCell = (cell, gov, area, extraCls) => {
    const isAxis = activeMetric === cell.metric;
    const isSel = sel && sel.governorate === gov && sel.area === (area || "") && sel.metric === cell.metric;
    return `
      <td class="gov-table-cell${isAxis ? " axis" : ""}${isSel ? " selected" : ""}">
        <button class="gov-table-num${extraCls || ""}" type="button" data-board-gov="${escapeHtml(gov)}" ${area ? `data-board-area-run="${escapeHtml(area)}"` : ""} data-board-metric-run="${escapeHtml(cell.metric)}" ${cell.count ? "" : "disabled"} title="${escapeHtml(boardMetricLabels[cell.metric] || "")}">${cell.count.toLocaleString("en-US")}</button>
      </td>`;
  };
  // خلية التغير اليومي: فرق آخر 24 ساعة عن الـ24 ساعة السابقة لعمود المحور (المقياس النشط)
  const deltaCell = (scopeRows, scopeLabel) => {
    const d = metricDailyDelta(scopeRows, activeMetric);
    const cls = d.delta > 0 ? " up" : d.delta < 0 ? " down" : " flat";
    const text = formatDailyDelta(d);
    const tip = `التغير اليومي لـ${boardMetricLabels[activeMetric] || "المحور"} في ${scopeLabel}: ${d.today} إعلان في آخر 24 ساعة مقابل ${d.prev} في الـ24 ساعة قبلها — ${text}`;
    return `<td class="gov-table-delta${cls}" title="${escapeHtml(tip)}">${text}</td>`;
  };
  const head = `
    <thead>
      <tr>
        <th class="gov-table-name-col">المحافظة</th>
        <th class="gov-table-areas-col">المناطق</th>
        <th class="gov-table-delta-col">التغير اليومي</th>
        ${metrics.map((m) => `<th class="gov-table-head${activeMetric === m ? " axis" : ""}">${escapeHtml(boardMetricLabels[m] || "")}</th>`).join("")}
      </tr>
    </thead>`;
  const body = governorates.map((governorate) => {
    const govRows = rows.filter((row) => boardLocationBucket(row) === governorate);
    const cells = metricCells(rows, governorate);
    const expanded = boardState.expandedGovernorates.has(governorate);
    const areaCount = uniqueValues(govRows.map((row) => row.area).filter(Boolean)).length;
    const bucketTip = LOCATION_BUCKET_TIPS[governorate] || "";
    const areaGroups = {};
    for (const row of govRows) {
      if (!row.area) continue;
      const key = normalizeArabic(row.area);
      if (!(key in areaGroups)) areaGroups[key] = row.area;
    }
    const areas = Object.values(areaGroups).sort((a, b) => String(a).localeCompare(String(b), "ar"));
    return `
      <tbody class="gov-table-gov${expanded ? " expanded" : ""}">
        <tr class="gov-table-row">
          <td class="gov-table-name-cell">
            ${areaCount ? `<button class="gov-table-toggle" type="button" data-board-toggle-gov="${escapeHtml(governorate)}" aria-label="${expanded ? "طي" : "فتح"} مناطق ${escapeHtml(governorate)}">${expanded ? "▲" : "▼"}</button>` : ""}
            <span class="gov-table-govname"${bucketTip ? ` title="${escapeHtml(bucketTip)}"` : ""}>${escapeHtml(governorate)}</span>
          </td>
          <td class="gov-table-areas-count">${areaCount}</td>
          ${deltaCell(govRows, governorate)}
          ${cells.map((cell) => numCell(cell, governorate, "", "")).join("")}
        </tr>
        ${expanded ? `
          <tr class="gov-table-areas-row">
            <td colspan="${3 + metrics.length}">
              <table class="gov-area-table">
                <thead><tr><th class="gov-table-name-col">المنطقة</th><th class="gov-table-delta-col">التغير</th>${metrics.map((m) => `<th class="gov-table-head">${escapeHtml(boardMetricLabels[m] || "")}</th>`).join("")}</tr></thead>
                <tbody>
                  ${areas.map((area) => {
                    const areaRows = govRows.filter((row) => row.area === area);
                    return `
                    <tr>
                      <td class="gov-area-name">${escapeHtml(area)}</td>
                      ${deltaCell(areaRows, area)}
                      ${metricCells(rows, governorate, area).map((cell) => numCell(cell, governorate, area, "")).join("")}
                    </tr>`;
                  }).join("")}
                </tbody>
              </table>
            </td>
          </tr>` : ""}
      </tbody>`;
  }).join("");
  const totalRow = `
    <tbody class="gov-table-total">
      <tr>
        <td class="gov-table-name-cell"><span class="gov-table-govname">الإجمالي</span></td>
        <td class="gov-table-areas-count">—</td>
        ${deltaCell(rows, "السوق كامل")}
        ${totals.map((t) => `
          <td class="gov-table-cell${activeMetric === t.metric ? " axis" : ""}">
            <button class="gov-table-num total" type="button" data-board-total-run="${escapeHtml(t.metric)}" ${t.count ? "" : "disabled"} title="${escapeHtml(boardMetricLabels[t.metric] || "")}">${t.count.toLocaleString("en-US")}</button>
          </td>`).join("")}
      </tr>
    </tbody>`;
  return `
    <div class="gov-table-wrap">
      <table class="gov-table">
        ${head}
        ${body}
        ${totalRow}
      </table>
    </div>`;
}

// ── أدوات تسلسل مشتركة لتصدير/نسخ أرقام الجداول ────────────────────────────────
function csvSerialize(lines) {
  const esc = (value) => {
    const s = String(value ?? "");
    return /[",\r\n;]/.test(s) ? `"${s.replace(/"/g, "\"\"")}"` : s;
  };
  return lines.map((row) => row.map(esc).join(",")).join("\r\n");
}

function tsvSerialize(lines) {
  // TSV للصق المباشر في Excel: لا حاجة للاقتباس، نستبدل فقط أي تبويب/سطر داخل القيم
  const esc = (value) => String(value ?? "").replace(/\t/g, " ").replace(/[\r\n]+/g, " ");
  return lines.map((row) => row.map(esc).join("\t")).join("\r\n");
}

// بناء صفوف أرقام لوحة السوق الحالية (محافظات + إجمالي + مناطق) — مشترك بين CSV وTSV
function buildGovExportRows() {
  const rows = boardState.records.filter((row) => rowMatchesBoardFilters(row, false, false, true));
  const governorates = uniqueValues(rows.map((row) => boardLocationBucket(row)));
  const metrics = ["movement", "opportunities", "saleOffers", "buyRequests", "rentOffers", "rentRequests"];
  const activeMetric = boardState.activeMetric || "movement";
  const header = ["المحافظة", "المنطقة", `التغير اليومي (${boardMetricLabels[activeMetric] || "المحور"})`].concat(metrics.map((m) => boardMetricLabels[m] || m));
  const govLines = [];
  const areaLines = [];
  for (const governorate of governorates) {
    const govRows = rows.filter((row) => boardLocationBucket(row) === governorate);
    const areaCount = uniqueValues(govRows.map((row) => row.area).filter(Boolean)).length;
    govLines.push([governorate, `${areaCount} منطقة`, formatDailyDelta(metricDailyDelta(govRows, activeMetric)), ...metrics.map((m) => countMetric(govRows, m))]);
    const areaGroups = {};
    for (const row of govRows) {
      if (!row.area) continue;
      const key = normalizeArabic(row.area);
      if (!(key in areaGroups)) areaGroups[key] = row.area;
    }
    Object.values(areaGroups).sort((a, b) => String(a).localeCompare(String(b), "ar")).forEach((area) => {
      const areaRows = govRows.filter((row) => row.area === area);
      areaLines.push([governorate, area, formatDailyDelta(metricDailyDelta(areaRows, activeMetric)), ...metrics.map((m) => countMetric(areaRows, m))]);
    });
  }
  const totalLine = ["الإجمالي", "", formatDailyDelta(metricDailyDelta(rows, activeMetric)), ...metrics.map((m) => countMetric(rows, m))];
  return { header, govLines, totalLine, areaLines };
}

function govExportLines() {
  const { header, govLines, totalLine, areaLines } = buildGovExportRows();
  return [header, ...govLines, totalLine, [], ["المناطق — تفصيل كل محافظة"], ...areaLines];
}

// تصدير أرقام المحافظات والمناطق الحالية إلى CSV (UTF-8 مع BOM) يعمل مع Excel مباشرة
function exportGovTableCsv() {
  const today = new Date().toISOString().slice(0, 10);
  const csv = "\uFEFF" + csvSerialize(govExportLines()); // BOM حتى يفتح Excel العربي UTF-8 بشكل صحيح
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `لوحة-السوق-المحافظات-${today}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// نسخ نفس الأرقام إلى الحافظة بصيغة TSV — لصق مباشر في Excel بدون ملف
function copyGovTableTsv(btn) {
  copyText(tsvSerialize(govExportLines()), btn);
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

  // 0) بطاقات المؤشرات الرئيسية (KPI) — نفس أسلوب بطاقات لوحة السوق: رقاقة أيقونة + لون تمييز
  const market = data.market || {};
  const dirClass = market.direction === "صاعد" ? "kpi-up" : market.direction === "هابط" ? "kpi-down" : "kpi-flat";
  const trendTone = market.direction === "صاعد" ? "trend-up" : market.direction === "هابط" ? "trend-down" : "trend-flat";
  const kpis = `
    <div class="insight-kpis">
      <div class="kpi-card" data-insight-metric="areas"><span class="kpi-label">مناطق محللة</span><strong>${areas.length}</strong><small>من الحصاد المتراكم</small></div>
      <div class="kpi-card" data-insight-metric="saleSamples"><span class="kpi-label">عينات بيع</span><strong>${samples.sale || 0}</strong><small>إعلان بيع</small></div>
      <div class="kpi-card" data-insight-metric="rentSamples"><span class="kpi-label">عينات إيجار</span><strong>${samples.rent || 0}</strong><small>إعلان إيجار</small></div>
      <div class="kpi-card" data-insight-metric="buyRequests"><span class="kpi-label">طلبات شراء</span><strong>${samples.buyRequests || 0}</strong><small>مطلوب للشراء — من الفريج المحلي</small></div>
      <div class="kpi-card" data-insight-metric="rentRequests"><span class="kpi-label">طلبات إيجار</span><strong>${samples.rentRequests || 0}</strong><small>مطلوب للإيجار — من الفريج المحلي</small></div>
      <div class="kpi-card" data-insight-metric="yieldCount"><span class="kpi-label">عائد محسوب</span><strong>${withYield.length}</strong><small>منطقة بيع + إيجار معًا</small></div>
      <div class="kpi-card ${trendTone}" data-insight-metric="marketTrend"><span class="kpi-label">اتجاه السوق</span><strong class="${dirClass}">${escapeHtml(market.direction || "—")}</strong><small>${market.changePct != null ? `${market.changePct > 0 ? "+" : ""}${market.changePct}% سعر المتر العام` : "يُبنى مع تراكم الأشهر"}</small></div>
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
      <div class="kpi-card" data-insight-metric="demandTotal"><span class="kpi-label">إجمالي الطلبات</span><strong>${totals.total || 0}</strong><small>شراء + إيجار معًا</small></div>
      <div class="kpi-card" data-insight-metric="demandBuy"><span class="kpi-label">طلبات شراء</span><strong>${totals.buyRequests || 0}</strong><small>أشخاص يبحثون عن شراء</small></div>
      <div class="kpi-card" data-insight-metric="demandRent"><span class="kpi-label">طلبات إيجار</span><strong>${totals.rentRequests || 0}</strong><small>أشخاص يبحثون عن إيجار</small></div>
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
  lastHeatmapAreas = areas;
  if (!areas.length) {
    root.innerHTML = '<div class="empty">لا توجد بيانات سعر/مساحة كافية للرسم الحراري — تتراكم مع الحصاد اليومي.</div>';
    return;
  }
  root.innerHTML = heatmapCellsHtml(areas);
  renderWatchedAreas($("watchedAreasInsights"), areas);
  // الخريطة التفاعلية (إن كانت مفتوحة) تتلوّن من نفس القيم ونفس الوضع
  if (heatmapView === "map") renderInsightsMap(areas);
}

// ─── الخريطة التفاعلية Leaflet: مناطق الكويت فوق الخريطة الحرارية ─────────
let heatmapView = "grid";
let lastHeatmapAreas = [];
let insightsMap = null;
let insightsMapMarkers = [];
let kuwaitCoords = null;
let leafletPromise = null;
// نقاط الإعلانات على الخريطة: سجلات اللوحة (بدرجة الفرصة) + فلاتر المصدر/النوع
let mapListingsCache = null;
let mapListingFilters = { sources: [], types: [] };
let insightsMapListingsLayer = null;

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(css);
    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("تعذر تحميل مكتبة الخريطة (تحقق من الاتصال بالإنترنت)"));
    document.head.appendChild(script);
  });
  return leafletPromise;
}

async function loadKuwaitCoords() {
  if (kuwaitCoords) return kuwaitCoords;
  try {
    const response = await fetch("static-data/kuwait-areas.json", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    kuwaitCoords = await response.json();
  } catch {
    kuwaitCoords = { areas: {}, governorates: {} };
  }
  return kuwaitCoords;
}

function areaCoord(areaName, governorate) {
  // محافظة مفهرسة بصيغتها الكنسية (محافظة حولي) أو المختصرة (حولي)
  const gov = GOVERNORATE_CANONICAL[normalizeArabic(governorate)] || governorate || "";
  const coords = kuwaitCoords || { areas: {}, governorates: {} };
  const entry = coords.areas[normalizeArabic(areaName)];
  if (entry) return { lat: entry.lat, lng: entry.lng, governorate: entry.governorate };
  const govEntry = coords.governorates[gov] || coords.governorates[normalizeArabic(gov)];
  if (govEntry) return { lat: govEntry.lat, lng: govEntry.lng, governorate: gov };
  return null;
}

// درجة الفرصة (0-100) → لون الدائرة: أخضر (فرصة قوية) عبر كهرماني إلى أحمر (منخفضة)، وغير المقيّم رمادي
function oppColor(score) {
  if (score == null) return "hsl(220 15% 50% / .62)";
  const t = Math.max(0, Math.min(1, Number(score) / 100));
  const hue = Math.round(120 * t); // 0 أحمر → 120 أخضر
  return `hsl(${hue} 68% 40% / .85)`;
}

function oppLabel(score) {
  if (score == null) return "غير مقيّم";
  const s = Number(score);
  return s >= 75 ? "فرصة قوية" : s >= 60 ? "مناسبة" : "تحتاج مراجعة";
}

// سجلات اللوحة (نفس مصدر /api/dashboard/summary) تُجلب مرة واحدة وتُخزَّن مؤقتًا لنقاط الخريطة
async function loadMapListings() {
  if (mapListingsCache) return mapListingsCache;
  try {
    const data = await getJson("/api/dashboard/summary");
    mapListingsCache = (data && data.records) || [];
  } catch {
    mapListingsCache = [];
  }
  return mapListingsCache;
}

function plottableMapListings() {
  return (mapListingsCache || []).filter((record) => areaCoord(record.area, record.governorate));
}

function mapListingMatchesFilters(record) {
  const bySource = mapListingFilters.sources;
  if (bySource.length) {
    const src = normalizeArabic(String(record.source || "").trim());
    if (!bySource.includes(src)) return false;
  }
  const byType = mapListingFilters.types;
  if (byType.length) {
    const type = normalizeArabic(String(record.propertyType || "").trim());
    if (!byType.includes(type)) return false;
  }
  return true;
}

// رقائق «المصدر / نوع العقار» تُبنى من الإعلانات القابلة للرسم (ذات إحداثي) مع عدّادات
function renderMapListingFilters() {
  const root = $("mapFilterGroups");
  if (!root) return;
  const plottable = plottableMapListings();
  const sourceCounts = {};
  const typeCounts = {};
  for (const record of plottable) {
    const src = String(record.source || "غير محدد").trim();
    const srcKey = normalizeArabic(src);
    sourceCounts[srcKey] = sourceCounts[srcKey] || { label: src, n: 0 };
    sourceCounts[srcKey].n += 1;
    const type = String(record.propertyType || "").trim();
    if (type) {
      const typeKey = normalizeArabic(type);
      typeCounts[typeKey] = typeCounts[typeKey] || { label: type, n: 0 };
      typeCounts[typeKey].n += 1;
    }
  }
  const groupHtml = (title, counts, field) => {
    const chips = Object.values(counts)
      .sort((a, b) => b.n - a.n)
      .map((entry) => {
        const key = normalizeArabic(entry.label);
        const active = mapListingFilters[field].includes(key);
        return `<button type="button" class="map-filter-chip${active ? " active" : ""}" data-map-filter="${field}" data-map-filter-key="${escapeHtml(key)}" title="${escapeHtml(entry.label)} — ${entry.n} إعلان">${escapeHtml(entry.label)} <small>${entry.n}</small></button>`;
      })
      .join("");
    return `<div class="map-filter-group"><span class="map-filter-group-title">${escapeHtml(title)}</span><div class="map-filter-chips">${chips || '<span class="map-filter-empty">لا خيارات</span>'}</div></div>`;
  };
  root.innerHTML = groupHtml("المصدر", sourceCounts, "sources") + groupHtml("نوع العقار", typeCounts, "types");
}

// دوائر صغيرة لكل إعلان (بإحداثي منطقة) ملونة بدرجة الفرصة — تحترم فلاتر المصدر/النوع
function renderMapListingPoints() {
  const L = window.L;
  if (!L || !insightsMap) return;
  if (!insightsMapListingsLayer) {
    insightsMapListingsLayer = L.layerGroup().addTo(insightsMap);
  }
  insightsMapListingsLayer.clearLayers();
  const plottable = plottableMapListings();
  const visible = plottable.filter(mapListingMatchesFilters);
  for (const record of visible) {
    const coord = areaCoord(record.area, record.governorate);
    if (!coord) continue;
    const score = record.opportunityScore != null ? Number(record.opportunityScore) : null;
    const price = record.priceText || (record.price != null ? `${Number(record.price).toLocaleString("en-US")} د.ك` : "—");
    const marker = L.circleMarker([coord.lat, coord.lng], {
      radius: score != null ? 5 : 4,
      color: "#fff",
      weight: 1,
      fillColor: oppColor(score),
      fillOpacity: 0.9,
    });
    marker.bindTooltip(`${escapeHtml(record.area || "")} — ${escapeHtml(record.propertyType || "")} · ${escapeHtml(price)}`, {
      direction: "top",
      opacity: 0.95,
      className: "map-tip",
    });
    marker.bindPopup(`
      <b>${escapeHtml(record.area || "—")}</b> <span class="map-popup-gov">${escapeHtml(coord.governorate || "")}</span><br>
      <span>${escapeHtml(record.propertyType || "")} · ${escapeHtml(record.source || "")}</span><br>
      <span class="map-popup-sub">السعر: <strong>${escapeHtml(price)}</strong></span><br>
      <span class="map-popup-sub">درجة الفرصة: <strong style="color:${oppColor(score)}">${oppLabel(score)}${score != null ? ` (${Math.round(score)}/100)` : ""}</strong></span><br>
      ${record.originalUrl ? `<a class="map-popup-link" href="${escapeHtml(record.originalUrl)}" target="_blank" rel="noopener">فتح الإعلان الأصلي ↗</a>` : ""}
    `);
    marker.addTo(insightsMapListingsLayer);
  }
  const countEl = $("mapListingCount");
  if (countEl) countEl.textContent = `نقاط ظاهرة: ${visible.length} من ${plottable.length}`;
  const clearBtn = $("mapFilterClearBtn");
  if (clearBtn) clearBtn.hidden = !(mapListingFilters.sources.length || mapListingFilters.types.length);
}

function renderInsightsMap(areas) {
  const container = $("insightsLeafletMap");
  if (!container) return;
  const L = window.L;
  if (!L) return;
  if (!insightsMap) {
    insightsMap = L.map(container, { zoomControl: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(insightsMap);
  }
  insightsMapMarkers.forEach((marker) => marker.remove());
  insightsMapMarkers = [];
  const isYield = heatmapMode === "yield";
  const points = [];
  for (const a of areas) {
    const coord = areaCoord(a.area, a.governorate);
    if (!coord) continue;
    const value = isYield ? a.yieldPct : a.gapPct;
    const color = isYield ? yieldColor(value) : heatColor(value);
    const sign = !isYield && value > 0 ? "+" : "";
    const watched = isWatchedArea(a.area);
    const valueText = value != null ? `${sign}${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%` : "—";
    const unitText = isYield ? "عائد سنوي" : "فجوة عن وسيط المحافظة";
    const watchLabel = watched ? "★ مراقَبة — إلغاء" : "☆ احجز لمراقبة التغيّر";
    const marker = L.circleMarker([coord.lat, coord.lng], {
      radius: isYield ? 13 : 14,
      color: "#fff",
      weight: 2,
      fillColor: color,
      fillOpacity: 0.9,
    });
    marker.bindPopup(`
      <b>${escapeHtml(a.area)}</b> <span class="map-popup-gov">${escapeHtml(coord.governorate || "")}</span><br>
      <span>${escapeHtml(unitText)}: <strong>${valueText}</strong></span><br>
      <span class="map-popup-sub">${a.count || 0} إعلان · سعر المتر ${Number(a.perM2).toLocaleString("en-US")} د.ك</span><br>
      <button type="button" class="map-watch-btn${watched ? " watched" : ""}" data-map-watch-area="${escapeHtml(a.area)}" data-map-watch-gap="${a.gapPct}" data-map-watch-yield="${a.yieldPct ?? ""}">${watchLabel}</button>
    `);
    marker.addTo(insightsMap);
    insightsMapMarkers.push(marker);
    points.push([coord.lat, coord.lng]);
  }
  if (points.length) {
    insightsMap.fitBounds(L.latLngBounds(points).pad(0.18));
  } else {
    insightsMap.setView([29.31, 47.85], 9);
  }
  // أزرار «احجز» داخل النوافذ المنبثقة
  document.querySelectorAll(".map-watch-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const area = btn.dataset.mapWatchArea || "";
      const gap = btn.dataset.mapWatchGap != null && btn.dataset.mapWatchGap !== "" ? Number(btn.dataset.mapWatchGap) : null;
      toggleWatchedArea(area, "", gap);
      renderInsightsMap(lastHeatmapAreas);
      renderInsightsHeatmap(insightsState.data);
    });
  });
  // نقاط الإعلانات + رقائق الفلترة (المصدر/النوع) — تُعاد عند كل إعادة رسم
  renderMapListingFilters();
  renderMapListingPoints();
}

async function setHeatmapView(view) {
  const grid = $("insightsHeatmap");
  const map = $("insightsLeafletMap");
  const filtersBar = $("mapListingFilters");
  if (!grid || !map) return;
  heatmapView = view === "map" ? "map" : "grid";
  document.querySelectorAll(".heatmap-view-switch .view-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.heatView === heatmapView);
  });
  grid.hidden = heatmapView === "map";
  map.hidden = heatmapView !== "map";
  if (filtersBar) filtersBar.hidden = heatmapView !== "map";
  if (heatmapView === "map") {
    map.innerHTML = '<div class="empty map-loading">جاري تحميل الخريطة...</div>';
    try {
      await Promise.all([loadLeaflet(), loadKuwaitCoords(), loadMapListings()]);
    } catch {
      map.innerHTML = '<div class="empty">تعذر تحميل الخريطة التفاعلية — تحقق من الاتصال بالإنترنت، أو استخدم «شبكة المناطق».</div>';
      return;
    }
    map.innerHTML = "";
    renderInsightsMap(lastHeatmapAreas);
  } else if (insightsMap) {
    // تنظيف عند الرجوع للشبكة — تُعاد تهيئة الخريطة عند فتحها مجددًا
    insightsMap.remove();
    insightsMap = null;
    insightsMapMarkers = [];
    insightsMapListingsLayer = null;
  }
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
  // تحديث البطاقات العائمة بعد إعادة رسم اللوحة
  if (window.hoverCard) hoverCard.refresh();
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
  // دلاء الموقع أيضًا (بلا موقع/غير محددة) حتى يمكن فلترة اللوحة عليها مثل المحافظات
  const boardGovernorates = uniqueValues([
    ...boardRows.map((r) => r.governorate).filter(Boolean),
    ...uniqueValues(boardRows.map(boardLocationBucket)).filter((b) => b === "بلا موقع" || b === "غير محددة"),
  ]);
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
          <p>${formatSummary(chatGuidanceAnswer(report) || summaryLead(report.summary || ''))}</p>
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

function renderAgentTrace(report) {
  const root = $("agentTraceBox");
  if (!root) return;
  const trace = report.agentTrace || {};
  const agents = Array.isArray(trace.agents) ? trace.agents : [];
  if (!agents.length) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  const ai = trace.ai || {};
  const aiLabel = ai.provider
    ? `${ai.provider}${ai.model ? ` · ${ai.model}` : ""}`
    : "تحليل محلي";
  const cards = agents.map((agent) => `
    <article class="agent-trace-card">
      <div>
        <h4>${escapeHtml(agent.name || agent.id || "وكيل")}</h4>
        <p>${escapeHtml(agent.summary || "")}</p>
      </div>
      <span class="agent-trace-state">${escapeHtml(agent.status || "done")}</span>
    </article>
  `).join("");
  const attempts = (ai.attempts || []).slice(0, 4).map((attempt) => `
    <span class="agent-attempt ${attempt.status === "success" ? "ok" : "muted"}">
      ${escapeHtml(attempt.provider || "")}${attempt.responseMs != null ? ` · ${Math.round(Number(attempt.responseMs))}ms` : ""}
    </span>
  `).join("");
  root.innerHTML = `
    <div class="agent-trace-head">
      <div>
        <strong>مسار التحليل</strong>
        <span>الأرقام من قاعدة البيانات والمنطق الحسابي، والذكاء الاصطناعي للتفسير فقط.</span>
      </div>
      <b>${escapeHtml(aiLabel)}</b>
    </div>
    ${attempts ? `<div class="agent-attempts">${attempts}</div>` : ""}
    <div class="agent-trace-grid">${cards}</div>
  `;
  root.hidden = false;
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

// ─── وضع مبسّط للباحث العادي: بطاقات أكبر بلا جداول تحليلية + فلترة بالنقر ───

function toggleSimpleMode() {
  state.simpleMode = !state.simpleMode;
  localStorage.setItem("alforaij_simple_mode", state.simpleMode ? "1" : "0");
  applySimpleMode();
}

function applySimpleMode() {
  const on = localStorage.getItem("alforaij_simple_mode") === "1";
  state.simpleMode = on;
  document.body.classList.toggle("simple-mode", on);
  const btn = $("simpleModeToggle");
  if (btn) btn.textContent = on ? "👁 وضع مفصل" : "👁 وضع مبسّط";
  if (btn) btn.title = on ? "العودة للتحليل المفصل الكامل" : "بطاقات أكبر واتصال مباشر بلا جداول تحليلية";
}

// ── خريطة العقارات (Leaflet + OpenStreetMap) ──
// إحداثيات المناطق الكويتية الرئيسية
const KUWAIT_AREAS = {
  "الفريدوس": [29.27, 47.97], "الفردوس": [29.27, 47.97],
  "النهضة": [29.31, 47.93], "ال经": [29.31, 47.93],
  "صباح الناصر": [29.25, 48.05], "صباح السالم": [29.25, 48.05],
  "الجابرية": [29.28, 47.99], "الجهراء": [29.35, 47.65],
  "حولي": [29.34, 48.00], "السالمية": [29.33, 48.08],
  "العاصمة": [29.38, 47.98], "شرق": [29.38, 47.98],
  "المنقف": [29.18, 48.12], "ال Ahmadi": [29.08, 48.08],
  "الأحمدي": [29.08, 48.08], "الفحيحيل": [29.05, 48.13],
  "الفنطاس": [29.15, 48.10], "الرقة": [29.22, 47.95],
  "الخزان": [29.20, 47.93], "المسايل": [29.27, 48.07],
  "بيان": [29.30, 48.05], "الصليبيخات": [29.32, 47.96],
  "ال Ribaeen": [29.35, 47.95], "ال Ribaeen": [29.35, 47.95],
  "الرابية": [29.29, 48.02], "الفيج": [29.36, 47.82],
  "مبارك الكبير": [29.20, 48.07], "الخيران": [29.26, 47.85],
  "海湾": [29.25, 47.90], "ال.url": [29.33, 48.01],
  "بوحليفة": [29.07, 48.10], "أبو حليفة": [29.07, 48.10],
  "المنصورية": [29.24, 48.00], "ال Winnipeg": [29.36, 48.02],
  "ال kuwait": [29.37, 47.97],
  // Default Kuwait center
  "_default": [29.32, 48.00]
};
let _leafletMap = null;
let _markerGroup = null;

// ── Lazy-load CDN libraries (improves FCP by ~3s) ──
const _lazyLibs = {};
function _loadCSS(href) {
  if (document.querySelector(`link[href="${href}"]`)) return Promise.resolve();
  return new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.onload = resolve;
    link.onerror = resolve;
    document.head.appendChild(link);
  });
}
function _loadScript(src) {
  if (_lazyLibs[src]) return _lazyLibs[src];
  if (document.querySelector(`script[src="${src}"]`)) { _lazyLibs[src] = Promise.resolve(); return _lazyLibs[src]; }
  _lazyLibs[src] = new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = resolve;
    document.body.appendChild(s);
  });
  return _lazyLibs[src];
}
async function _ensureLeaflet() {
  if (window.L) return true;
  await Promise.all([
    _loadCSS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"),
    _loadScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"),
  ]);
  return !!window.L;
}
async function _ensureChartJS() {
  if (window.Chart) return true;
  await _loadScript("https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js");
  return !!window.Chart;
}

function _geocodeArea(area) {
  if (!area) return KUWAIT_AREAS["_default"];
  const norm = area.trim();
  if (KUWAIT_AREAS[norm]) return KUWAIT_AREAS[norm];
  // بحث جزئي
  for (const [key, coords] of Object.entries(KUWAIT_AREAS)) {
    if (key === "_default") continue;
    if (norm.includes(key) || key.includes(norm)) return coords;
  }
  return null;
}

async function _ensureMap() {
  const container = document.getElementById("propertyMap");
  if (!container) return null;
  if (_leafletMap) { _leafletMap.invalidateSize(); return _leafletMap; }
  if (!(await _ensureLeaflet())) return null;
  _leafletMap = L.map(container, {
    center: [29.32, 48.00],
    zoom: 11,
    zoomControl: true,
    attributionControl: true,
  });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 18,
  }).addTo(_leafletMap);
  _markerGroup = L.featureGroup().addTo(_leafletMap);
  return _leafletMap;
}

function _scoreColor(score) {
  if (score >= 75) return "#22c55e";  // أخضر — لقطة
  if (score >= 50) return "#3b82f6";  // أزرق — جيد
  if (score >= 30) return "#f59e0b";  // برتقالي — متوسط
  return "#94a3b8";                   // رمادي — ضعيف
}

async function renderMapMarkers(results) {
  const map = await _ensureMap();
  if (!map || !_markerGroup) return;
  _markerGroup.clearLayers();
  let placed = 0;
  for (const item of (results || [])) {
    const coords = _geocodeArea(item.area);
    if (!coords) continue;
    // إضافة عشوائية بسيطة لمنع تراكب العلامات
    const lat = coords[0] + (Math.random() - 0.5) * 0.008;
    const lng = coords[1] + (Math.random() - 0.5) * 0.008;
    const score = Math.round(item.recommendationScore || item.matchScore || 0);
    const color = _scoreColor(score);
    const icon = L.divIcon({
      className: "",
      html: `<div style="background:${color};color:#fff;border-radius:50%;width:28px;height:28px;display:grid;place-items:center;font-size:11px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid #fff;">${score}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const popup = [
      `<div class="popup-title">${escapeHtml(item.code || "")} — ${escapeHtml(item.area || "")}</div>`,
      `<div class="popup-price">${escapeHtml(item.priceText || (item.price ? item.price.toLocaleString() + " د.ك" : "—"))}</div>`,
      `<div class="popup-area">${item.space ? item.space + " م²" : ""} ${item.propertyType ? "· " + item.propertyType : ""}</div>`,
      `<div class="popup-score">توصية ${score}/100</div>`,
      item.originalUrl ? `<div style="margin-top:6px"><a href="${escapeHtml(item.originalUrl)}" target="_blank" rel="noopener" style="color:var(--blue);font-size:12px;">فتح المصدر ↗</a></div>` : "",
    ].join("");
    const marker = L.marker([lat, lng], { icon }).bindPopup(popup, { maxWidth: 260 });
    _markerGroup.addLayer(marker);
    placed++;
  }
  if (placed > 0) {
    map.fitBounds(_markerGroup.getBounds().pad(0.15));
  }
}

let _mapVisible = false;
function toggleMapView() {
  _mapVisible = !_mapVisible;
  const container = $("mapContainer");
  if (container) container.hidden = !_mapVisible;
  if (_mapVisible && _leafletMap) {
    setTimeout(() => _leafletMap.invalidateSize(), 100);
  }
}

function showMapIfResults(results) {
  const btn = $("mapToggleBtn");
  if (!btn) return;
  if (results && results.length > 0) {
    btn.hidden = false;
    // Auto-show map on first results
    if (!_mapVisible && !_leafletMap) {
      _mapVisible = true;
      const container = $("mapContainer");
      if (container) container.hidden = false;
      setTimeout(() => {
        renderMapMarkers(results);
        if (_leafletMap) _leafletMap.invalidateSize();
      }, 200);
    } else if (_mapVisible) {
      renderMapMarkers(results);
    }
  } else {
    btn.hidden = true;
    const container = $("mapContainer");
    if (container) container.hidden = true;
  }
}

// ── Feature 1: مقارنة أسعار المناطق ──
function renderAreaPriceComparison(results) {
  const box = $("areaPriceCompare");
  if (!box || !results || !results.length) { if (box) box.hidden = true; return; }
  // تجميع متوسط السعر/م² لكل منطقة
  const areaMap = {};
  for (const item of results) {
    const area = (item.area || "").trim();
    if (!area) continue;
    const np = item.normalized_price || (item.price && item.space ? item.price / item.space : 0);
    if (np <= 0) continue;
    if (!areaMap[area]) areaMap[area] = { sum: 0, count: 0, total_price: 0 };
    areaMap[area].sum += np;
    areaMap[area].count += 1;
    areaMap[area].total_price += item.price || 0;
  }
  const areas = Object.entries(areaMap)
    .map(([name, d]) => ({ name, avg: Math.round(d.sum / d.count), count: d.count, total: d.total }))
    .sort((a, b) => b.avg - a.avg);
  if (areas.length < 2) { box.hidden = true; return; }
  const maxAvg = areas[0].avg || 1;
  let html = '<div class="area-bar-chart">';
  for (const area of areas) {
    const pct = Math.round((area.avg / maxAvg) * 100);
    const color = area.avg > maxAvg * 0.8 ? "var(--red)" : area.avg > maxAvg * 0.5 ? "var(--amber)" : "var(--green)";
    html += `<div class="area-bar-row">
      <span class="area-bar-label">${escapeHtml(area.name)}</span>
      <div class="area-bar-track"><div class="area-bar-fill" style="width:${pct}%;background:${color}">${area.count} إعلان</div></div>
      <span class="area-bar-value">${area.avg.toLocaleString()} د.ك/م²</span>
    </div>`;
  }
  html += '</div>';
  box.hidden = false;
  const chartEl = $("areaPriceChart");
  if (chartEl) chartEl.innerHTML = html;
}

// ── Feature 2: اتجاهات الأسعار (رسم بياني) ──
let _priceTrendsChart = null;
async function loadPriceTrends(results) {
  const box = $("priceTrendsBox");
  if (!box) return;
  // حدد المنطقة الأولى من النتائج
  const area = results && results[0] ? (results[0].area || "") : "";
  if (!area) { box.hidden = true; return; }
  try {
    const resp = await fetch(`/api/price-trends?area=${encodeURIComponent(area)}`);
    const data = await resp.json();
    const rows = data.rows || [];
    if (!rows.length) { box.hidden = true; return; }
    box.hidden = false;
    // تجميع البيانات حسب الشهر
    const byMonth = {};
    for (const row of rows) {
      const month = (row.month || "").slice(0, 7);
      if (!month) continue;
      if (!byMonth[month]) byMonth[month] = { prices: [], spaces: [] };
      const ppm = row.median_price_per_m2 || row.median_price_per_sqm || 0;
      if (ppm) { byMonth[month].prices.push(ppm); byMonth[month].hasPerM2 = true; }
      else if (row.median_price) { byMonth[month].totalPrices = (byMonth[month].totalPrices || 0) + 1; byMonth[month].prices.push(row.median_price); }
    }
    const labels = Object.keys(byMonth).sort();
    const values = labels.map(m => {
      const p = byMonth[m].prices;
      return p.length ? Math.round(p.reduce((a, b) => a + b, 0) / p.length) : 0;
    });
    if (!values.some(v => v > 0)) { box.hidden = true; return; }
    const canvas = document.getElementById("priceTrendsChart");
    if (!canvas) return;
    if (_priceTrendsChart) _priceTrendsChart.destroy();
    await _ensureChartJS();
    if (!window.Chart) return;
    _priceTrendsChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: labels.map(l => l),
        datasets: [{
          label: Object.values(byMonth).some(m => m.hasPerM2) ? `سعر المتر — ${area}` : `متوسط السعر — ${area}`,
          data: values,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59,130,246,.15)",
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: "#3b82f6",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "rgba(255,255,255,.06)" }, ticks: { color: "#94a3b8", font: { size: 10 } } },
          y: { grid: { color: "rgba(255,255,255,.06)" }, ticks: { color: "#94a3b8", font: { size: 10 }, callback: v => { const unit = Object.values(byMonth).some(m => m.hasPerM2) ? ' د.ك/م²' : ' د.ك'; return v.toLocaleString() + unit; } } },
        },
      },
    });
  } catch (e) {
    box.hidden = true;
  }
}

// ── Feature 3: حاسبة العائد الاستثماري ──
function showROICalculator(results) {
  const box = $("roiCalculatorBox");
  if (!box) return;
  if (!results || !results.length) { box.hidden = true; return; }
  box.hidden = false;
  // ملء تلقائي من أفضل نتيجة
  const top = results[0];
  if (top && top.price) {
    const buyInput = $("roiBuyPrice");
    if (buyInput && !buyInput.value) buyInput.value = top.price;
  }
}

async function calculateROI() {
  const buyPrice = parseFloat($("roiBuyPrice")?.value) || 0;
  const monthlyRent = parseFloat($("roiMonthlyRent")?.value) || 0;
  const renovation = parseFloat($("roiRenovation")?.value) || 0;
  if (!buyPrice || !monthlyRent) {
    const resultEl = $("roiResult");
    if (resultEl) { resultEl.hidden = false; resultEl.innerHTML = '<div style="color:var(--red)">أدخل سعر الشراء والإيجار الشهري</div>'; }
    return;
  }
  try {
    const resp = await fetch("/api/invest/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ buy_price: buyPrice, monthly_rent: monthlyRent, renovation }),
    });
    const data = await resp.json();
    const resultEl = $("roiResult");
    if (!resultEl) return;
    resultEl.hidden = false;
    resultEl.innerHTML = [
      `<div class="roi-metric"><div class="roi-val">${(data.annual_roi_percent || 0).toFixed(1)}%</div><div class="roi-lbl">عائد سنوي</div></div>`,
      `<div class="roi-metric"><div class="roi-val">${(data.monthly_roi_percent || 0).toFixed(1)}%</div><div class="roi-lbl">عائد شهري</div></div>`,
      `<div class="roi-metric"><div class="roi-val">${(data.payback_years || 0).toFixed(1)}</div><div class="roi-lbl">سنوات استرداد</div></div>`,
      `<div class="roi-metric"><div class="roi-val">${(data.annual_cashflow || 0).toLocaleString()}</div><div class="roi-lbl">تدفق نقدي سنوي (د.ك)</div></div>`,
    ].join("");
  } catch (e) {
    const resultEl = $("roiResult");
    if (resultEl) { resultEl.hidden = false; resultEl.innerHTML = '<div style="color:var(--red)">خطأ في الحساب</div>'; }
  }
}

function countByNormalized(items, pick) {
  const counts = {};
  for (const item of items) {
    const raw = String(pick(item) || "").trim();
    const key = normalizeArabic(raw);
    if (!key) continue;
    if (!counts[key]) counts[key] = { label: raw, count: 0 };
    counts[key].count += 1;
  }
  return counts;
}

function renderResultsFilterChips(results) {
  const root = $("resultsFilterChips");
  if (!root) return;
  root.innerHTML = "";
  const items = (results || []).filter((r) => !(r.warnings || []).some((w) => String(w).includes("خارج المنطقة المطلوبة")));
  const byArea = countByNormalized(items, (r) => r.area);
  const byType = countByNormalized(items, (r) => r.propertyType || r.detailClass);
  const byTx = countByNormalized(items, (r) => r.transaction);
  if (!Object.keys(byArea).length && !Object.keys(byType).length && !Object.keys(byTx).length) {
    root.hidden = true;
    return;
  }
  root.hidden = false;
  const groups = [
    ["area", "المنطقة", byArea],
    ["type", "نوع العقار", byType],
    ["tx", "المعاملة", byTx],
  ];
  for (const [key, label, counts] of groups) {
    const entries = Object.entries(counts).sort((a, b) => b[1].count - a[1].count).slice(0, 8);
    if (!entries.length) continue;
    root.insertAdjacentHTML("beforeend", `<span class="chip-group-label">${escapeHtml(label)}</span>`);
    for (const [value, meta] of entries) {
      const active = (state.simpleFilters[key] || new Set()).has(value);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `filter-chip${active ? " active" : ""}`;
      btn.dataset.key = key;
      btn.dataset.value = value;
      btn.innerHTML = `${escapeHtml(meta.label)} <b>${meta.count}</b>`;
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      btn.addEventListener("click", () => toggleSimpleFilter(key, value, btn));
      root.appendChild(btn);
    }
  }
  if (Object.keys(state.simpleFilters).some((k) => (state.simpleFilters[k] || new Set()).size)) {
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "filter-chip clear";
    clear.textContent = "✕ مسح الفلاتر";
    clear.addEventListener("click", () => {
      state.simpleFilters = {};
      renderResultsFilterChips(results);
      applySimpleFilters();
    });
    root.appendChild(clear);
  }
}

function toggleSimpleFilter(key, value, btn) {
  if (!state.simpleFilters[key]) state.simpleFilters[key] = new Set();
  const set = state.simpleFilters[key];
  if (set.has(value)) set.delete(value);
  else set.add(value);
  btn.classList.toggle("active", set.has(value));
  btn.setAttribute("aria-pressed", set.has(value) ? "true" : "false");
  applySimpleFilters();
}

function applySimpleFilters() {
  const root = $("results");
  if (!root) return;
  let note = $("simpleFilterNote");
  const all = root.querySelectorAll(".result-card");
  const hasFilters = Object.keys(state.simpleFilters).some((k) => (state.simpleFilters[k] || new Set()).size);
  if (!hasFilters) {
    all.forEach((card) => { card.hidden = false; });
    if (note) note.remove();
    return;
  }
  let shown = 0;
  all.forEach((card) => {
    const matches = Object.entries(state.simpleFilters).every(([key, set]) => {
      if (!set.size) return true;
      const val = card.dataset[key === "area" ? "sarea" : key === "type" ? "stype" : "stx"] || "";
      return set.has(val);
    });
    card.hidden = !matches;
    if (matches) shown += 1;
  });
  if (!note) {
    note = document.createElement("div");
    note.id = "simpleFilterNote";
    note.className = "simple-filter-note";
    root.insertAdjacentElement("afterbegin", note);
  }
  note.textContent = `معروض ${shown} من ${all.length} نتيجة حسب الفلاتر.`;
}

// ─── سجل سعر العقار: خط زمني لسعر كل إعلان عند كل ظهور (من الحصاد اليومي) ───
const _priceHistoryCache = {};

function phShortDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function priceTimelineHtml(rows) {
  // تجميع الملاحظات المتتالية ذات السعر نفسه في مقاطع (سعر + فترة ظهور) —
  // يُظهر «كم ظل السعر» بدل تكرار نفس السعر يوميًا.
  const segments = [];
  for (const row of rows) {
    const price = Number(row.price);
    if (!price || price <= 0) continue;
    const last = segments[segments.length - 1];
    if (last && last.price === price) {
      last.last = row.seen_at;
      last.count += 1;
    } else {
      segments.push({ price, first: row.seen_at, last: row.seen_at, count: 1 });
    }
  }
  if (!segments.length) return "";
  const enriched = segments.map((seg, index) => ({
    ...seg,
    prev: index > 0 ? segments[index - 1].price : null,
  }));
  const first = enriched[0].price;
  const final = enriched[enriched.length - 1].price;
  const overall = final - first;
  const overallPct = first ? Math.round((overall / first) * 1000) / 10 : 0;
  let meta;
  if (overall < 0) meta = `انخفض من ${formatMoney(first)} إلى ${formatMoney(final)} (${overallPct}%)`;
  else if (overall > 0) meta = `ارتفع من ${formatMoney(first)} إلى ${formatMoney(final)} (+${overallPct}%)`;
  else meta = `السعر ثابت عند ${formatMoney(first)} منذ أول ظهور`;
  // آخر 8 مقاطع (الأحدث أولوية الرؤية) + ملاحظة بالأقدم إن وُجدت
  const LIMIT = 8;
  const recent = enriched.slice(-LIMIT);
  const older = enriched.length - recent.length;
  const rowsHtml = recent.map((seg) => {
    const delta = seg.prev !== null ? seg.price - seg.prev : null;
    const pct = seg.prev ? Math.round((delta / seg.prev) * 1000) / 10 : null;
    const deltaClass = delta < 0 ? "ph-down" : delta > 0 ? "ph-up" : "";
    const deltaIcon = delta < 0 ? "📉" : delta > 0 ? "📈" : "➖";
    const range = seg.last !== seg.first
      ? `${phShortDate(seg.first)} ← ${phShortDate(seg.last)}`
      : phShortDate(seg.first);
    const times = seg.count > 1
      ? ` (شوهد ${seg.count} ${seg.count === 2 ? "مرتين" : "مرات"})`
      : "";
    return `
      <div class="ph-row">
        <span class="ph-price">${escapeHtml(formatMoney(seg.price))}</span>
        <span class="ph-range">${escapeHtml(range)}${escapeHtml(times)}</span>
        ${delta !== null ? `<span class="ph-delta ${deltaClass}">${deltaIcon} ${delta > 0 ? "+" : ""}${Number(delta).toLocaleString("en-US")} (${pct > 0 ? "+" : ""}${pct}%)</span>` : ""}
      </div>
    `;
  }).join("");
  const olderNote = older > 0
    ? `<div class="ph-more">… +${older} مستوى سعر أقدم قبل التاريخ الموضح</div>`
    : "";
  return `
    <h4 class="price-history-title">📈 سجل سعر العقار</h4>
    <p class="price-history-meta">${escapeHtml(meta)} · ${enriched.length} مستوى سعر منذ ${escapeHtml(phShortDate(segments[0].first))}</p>
    <div class="price-history-list">${rowsHtml}${olderNote}</div>
  `;
}

async function loadListingPriceHistory(code, slot) {
  // جلب محروس مباشرة من القاعدة الحية (نمط shareCountsBase): أي فشل يُبتلع صامتًا
  // — صفر أخطاء كونسول (درس فحص الجوال). يعمل على الخادم الحي والموقع الثابت معًا.
  if (!code || code === "STATIC" || !slot) return;
  if (code in _priceHistoryCache) {
    renderPriceHistory(slot, _priceHistoryCache[code]);
    return;
  }
  _priceHistoryCache[code] = [];
  try {
    const base = await supabaseBase();
    if (!base) return;
    const res = await fetch(
      `${base.url}/rest/v1/listing_price_observations?select=price,seen_at&code=eq.${encodeURIComponent(code)}&order=seen_at.asc`,
      { headers: { apikey: base.key, Authorization: `Bearer ${base.key}` } },
    );
    if (!res.ok) return;
    const rows = await res.json();
    _priceHistoryCache[code] = Array.isArray(rows) ? rows : [];
    renderPriceHistory(slot, _priceHistoryCache[code]);
  } catch {
    /* ignore */
  }
}

function renderPriceHistory(slot, rows) {
  if (!slot) return;
  const html = priceTimelineHtml(rows || []);
  if (!html) return;
  slot.hidden = false;
  slot.innerHTML = html;
}

function renderReport(report) {
  const summaryEl = $("summaryText");
  const summary = report.summary || "";
  const conciseAnswer = chatGuidanceAnswer(report);
  if (summaryEl) summaryEl.innerHTML = formatSummary(conciseAnswer || summaryLead(summary) || summary);
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
  renderAgentTrace(report);
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
    // حقول الفلترة بالنقر (منطقة/نوع/معاملة) — تُطابق الرقائق فوق النتائج
    const cardNode = node.querySelector(".result-card");
    if (cardNode) {
      cardNode.dataset.sarea = normalizeArabic(item.area || "");
      cardNode.dataset.stype = normalizeArabic(item.propertyType || item.detailClass || "");
      cardNode.dataset.stx = normalizeArabic(item.transaction || "");
    }
    // فتحة سجل السعر تُلتقط قبل appendChild (المقتطف يفرغ بعد الإلحاق)
    const priceHistorySlot = node.querySelector(".price-history");
    // كتلة البطاقة المبسطة: السعر كبير + منطقة + نوع + تاريخ (تظهر في وضع مبسّط فقط)
    const simplePrice = node.querySelector(".simple-price");
    if (simplePrice) simplePrice.textContent = item.priceText || (item.price ? formatMoney(item.price) : "غير معلن");
    const simpleArea = node.querySelector(".simple-area");
    if (simpleArea) simpleArea.textContent = item.area ? `📍 ${item.area}` : "";
    const simpleType = node.querySelector(".simple-type");
    if (simpleType) simpleType.textContent = item.propertyType || item.detailClass || "";
    const simpleDate = node.querySelector(".simple-date");
    if (simpleDate) simpleDate.textContent = item.publishedDate ? `🗓 ${dateText(item.publishedDate)}` : "";
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
    // شارات التصنيف التلقائي
    const classBadges = node.querySelector(".classification-badges");
    if (classBadges && item.classification) {
      const c = item.classification;
      const badges = [];
      if (c.priority) {
        const pCls = c.priority === "عالية" ? "priority-high" : c.priority === "متوسطة" ? "priority-medium" : "priority-low";
        badges.push(`<span class="class-badge ${pCls}">🎯 ${c.priority}</span>`);
      }
      if (c.investmentLevel) {
        const iCls = c.investmentLevel === "ممتاز" ? "investment-excellent" : c.investmentLevel.includes("جيد") ? "investment-good" : c.investmentLevel === "متوسط" ? "investment-medium" : "investment-low";
        badges.push(`<span class="class-badge ${iCls}">💰 ${c.investmentLevel}</span>`);
      }
      if (c.trustLevel) {
        const tCls = c.trustLevel === "عالي" ? "trust-high" : "";
        badges.push(`<span class="class-badge ${tCls}">✅ ثقة ${c.trustLevel}</span>`);
      }
      if (c.propertyType) {
        badges.push(`<span class="class-badge">🏢 ${c.propertyType}</span>`);
      }
      if (c.dealType) {
        badges.push(`<span class="class-badge">🤝 ${c.dealType}</span>`);
      }
      if (c.dataSource) {
        const sCls = c.dataSource === "الفريج" ? "source-local" : "source-external";
        badges.push(`<span class="class-badge ${sCls}">🌐 ${c.dataSource}</span>`);
      }
      if (c.tags && c.tags.length) {
        c.tags.forEach(tag => badges.push(`<span class="class-badge">🏷️ ${tag}</span>`));
      }
      classBadges.innerHTML = badges.join("");
      classBadges.hidden = !badges.length;
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
    // ── Trust Score Badge: مؤشر ثقة الإعلان ──
    const ts = item.trustScore || {};
    const trustScoreEl = node.querySelector(".trust-score-section");
    if (trustScoreEl && ts.score != null) {
      const grade = ts.grade || "moderate";
      const icon = grade === "trusted" ? "✅" : grade === "low" ? "🔴" : "🟡";
      trustScoreEl.innerHTML = `
        <span class="trust-score-badge ${grade}" title="درجة ثقة الإعلان: ${ts.score}/100">
          <span class="trust-icon">${icon}</span> ثقة ${ts.score}/100
        </span>
        ${ts.alerts && ts.alerts.length ? `<div class="trust-score-alerts${ts.alerts[0].startsWith('ℹ') ? ' info' : ''}">${ts.alerts.join(' · ')}</div>` : ""}
        ${ts.factors && ts.factors.length ? `<details class="trust-score-details"><summary>تفاصيل التقييم</summary>${ts.factors.map(f => `<div class="trust-factor"><span class="trust-factor-name">${f.name}: ${f.detail}</span><span class="trust-factor-score" style="color:${f.score >= f.max * 0.7 ? '#16a34a' : f.score >= f.max * 0.4 ? '#d97706' : '#dc2626'}">${f.score}/${f.max}</span></div>`).join('')}</details>` : ""}
      `;
    }
    // ── Confidence Interval: نطاق الثقة ──
    const ci = item.confidenceInterval || {};
    const ciEl = node.querySelector(".confidence-interval-section");
    if (ciEl && ci.low != null && ci.high != null) {
      ciEl.innerHTML = `
        <div class="ci-box">
          <span class="ci-label">نطاق الثقة</span>
          <span class="ci-range">${latinDigits(ci.display)}</span>
          <span class="ci-pct">${ci.label}</span>
        </div>
      `;
    }
    // ── Explanation Factors: عوامل التقييم ──
    const ef = item.explanationFactors || [];
    const efEl = node.querySelector(".explanation-factors-section");
    if (efEl && ef.length) {
      efEl.innerHTML = ef.map(f => {
        const tone = f.impact === 'positive' ? '#16a34a' : f.impact === 'negative' ? '#dc2626' : f.impact === 'neutral' ? '#d97706' : '#6b7280';
        return '<div class="ef-item">'
          + '<span class="ef-label">' + f.label + '</span>'
          + '<span class="ef-value" style="color:' + tone + '">' + f.value + '</span>'
          + (f.detail ? '<span class="ef-detail">' + f.detail + '</span>' : '')
          + '</div>';
      }).join("");
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
    // زر اتصال مباشر (tel:) — يظهر عند توفر رقم هاتف المعلن بجانب فتح الإعلان
    const callLink = node.querySelector(".call-link");
    if (callLink) {
      if (item.phone) {
        callLink.href = `tel:${String(item.phone).replace(/[^\d+]/g, "")}`;
        callLink.title = `اتصال بالمعلن: ${latinDigits(item.phone)}`;
        callLink.hidden = false;
        callLink.addEventListener("click", () => trackOutreach({ action: "call", channel: "search_result", opportunityCode: item.code || "" }));
      }
    }
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
    shareLink.addEventListener("click", () => {
      trackOutreach({ action: "send", channel: "chat_result", opportunityCode: item.code || "" });
      incrementShare(item.code || "");
    });
    copyBtn.after(shareLink);
    const shareChip = document.createElement("span");
    shareChip.className = "share-count";
    shareChip.dataset.code = item.code || "";
    shareChip.hidden = true;
    shareChip.innerHTML = "🔄 <b>0</b>";
    shareLink.after(shareChip);
    root.appendChild(node);
    // سجل سعر العقار: خط زمني للسعر عند كل ظهور يُجلب محروسًا ويظهر في بطاقة التحليل
    loadListingPriceHistory(item.code, priceHistorySlot);
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
  // فلاتر النقر تُبنى من نتائج هذا البحث، ويُصفَّر الاختيار عند كل بحث جديد
  state.simpleFilters = {};
  renderResultsFilterChips(results);
  applySimpleFilters();
  // تحديث البطاقات العائمة بعد إعادة رسم النتائج
  if (window.hoverCard) hoverCard.refresh();
  // تحديث الخريطة بالنتائج الجديدة
  showMapIfResults(results);
  // ── ميزات التمييز: مقارنة الأسعار + اتجاهات + حاسبة العائد ──
  renderAreaPriceComparison(results);
  loadPriceTrends(results);
  showROICalculator(results);
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

async function downloadExcelReport(btnId) {
  if (!state.report) return;
  const btn = btnId ? $(btnId) : null;
  const original = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "جاري توليد Excel...";
  }
  try {
    const response = await fetch(apiUrl("/api/report-excel"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report: state.report }),
    });
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `alforaij-report-${Date.now()}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("Excel generation failed:", err);
    alert("تعذر توليد ملف Excel — تأكد من اتصال الخادم");
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
  view: "grid", // شبكة/جدول — مفتاح موحّد مع لوحة السوق (viewModeKey)
};

try {
  const savedView = localStorage.getItem(viewModeKey);
  if (savedView === "table" || savedView === "grid") oppState.view = savedView;
} catch { /* تجاهل — نبقى على الوضع الافتراضي */ }

const OPP_TIER_LABELS = { best: "الأفضل", daily: "يومية", weekly: "أسبوعية", monthly: "شهرية", yearly: "سنوية" };

// آخر مجموعة فرص معروضة في الجدول المضغوط — يستخدمها زر تصدير CSV
let lastOppTableItems = [];

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

// ── تسجيل الدخول عبر Google ──
function googleLogin() {
  const CLIENT_ID = window.GOOGLE_CLIENT_ID || localStorage.getItem("alforaij_google_client_id") || "demo-client-id";
  if (CLIENT_ID && typeof google !== "undefined" && google.accounts) {
    _startGoogleSignIn(CLIENT_ID);
    return;
  }
  fetch("/api/google-client-id")
    .then(r => r.json())
    .then(cfg => {
      const cid = cfg.client_id || CLIENT_ID;
      localStorage.setItem("alforaij_google_client_id", cid);
      _startGoogleSignIn(cid);
    })
    .catch(() => {
      _startGoogleSignIn(CLIENT_ID);
    });
}

function _startGoogleSignIn(clientId) {
  if (typeof google === "undefined" || !google.accounts) {
    showAccountMsg("جاري تحميل Google — أعد المحاولة بعد قليل", true);
    return;
  }
  try {
    google.accounts.id.initialize({ client_id: clientId || "demo-client-id", callback: _handleGoogleCredential });
    google.accounts.id.prompt();
  } catch (err) {
    showAccountMsg("تعذر فتح تسجيل الدخول بـ Google — أعد المحاولة", true);
  }
}

async function _handleGoogleCredential(response) {
  if (!response || !response.credential) return;
  showAccountMsg("جاري التحقق من حساب Google...", false);
  let data = null;
  try {
    const res = await fetch("/api/google-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    if (res.ok) data = await res.json();
  } catch { /* ignore */ }

  // السقوط للتحقق المحلي المباشر من شفرة JWT عند النشر الثابت أو انقطاع الاتصال
  if (!data || !data.secret) {
    try {
      const parts = response.credential.split(".");
      if (parts.length === 3) {
        const payloadStr = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
        const payload = JSON.parse(decodeURIComponent(escape(payloadStr)));
        data = {
          status: "ok",
          secret: "google_" + (payload.sub || Date.now()),
          phone: payload.email || "google_user@gmail.com",
          name: payload.name || "مستخدم Google",
          avatar: payload.picture || "",
          provider: "google",
        };
      }
    } catch (parseErr) {
      console.warn("JWT parse fallback failed:", parseErr);
    }
  }

  if (!data || !data.secret) {
    showAccountMsg("تعذر تسجيل الدخول بـ Google — استخدم رقم الهاتف", true);
    return;
  }

  accountState.secret = data.secret;
  accountState.phone = data.phone || "";
  accountSave();
  // حفظ معلومات الملف الشخصي
  try {
    localStorage.setItem("alforaij_user_name", data.name || "");
    localStorage.setItem("alforaij_user_avatar", data.avatar || "");
    localStorage.setItem("alforaij_user_provider", data.provider || "phone");
  } catch { /* ignore */ }
  const stepPhone = $("accountStepPhone");
  const stepOtp = $("accountStepOtp");
  if (stepPhone) stepPhone.hidden = true;
  if (stepOtp) stepOtp.hidden = true;
  renderAccountStatus();
  showAccountMsg(`تم تسجيل الدخول بنجاح ✓ — مرحباً ${escapeHtml(data.name || "")}`, false);
  loadSavedSearches();
  loadUserAlerts();
  loadPortfolio();
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

// تتبع نقرات التسويق (نسخ/إرسال فرصة أو عميل) في Supabase — بلا انتظار وبلا كسر أي شيء عند الفشل.
// الموقع المنشور ثابت بلا خادم API (لا نقطة outreach-click) — التتبع محصور في وضع الخادم
// حتى لا تُسجَّل 405 في الكونسول (درس فحص الجوال)؛ الإحصاءات تصل للوحة من اللقطة الثابتة.
function trackOutreach(click) {
  if (STATIC_SNAPSHOT_MODE) return;
  try {
    fetch(apiUrl("/api/outreach-click"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(click),
    }).catch(() => {});
  } catch { /* ignore */ }
}

// عدّاد مشاركات بطاقات التقييم: جدول share_counts يُقرأ ويُزاد عبر REST العام (مثل عدّادات
// القاعدة الحية) فيعمل على الموقع المرفوع بلا خادم API — مع سقوط سلس عند تعذر الاتصال.
const shareState = { counts: {}, base: null, loaded: false };

async function shareCountsBase() {
  if (shareState.base) return shareState.base;
  try {
    const cfg = await getJson("/api/live-db");
    if (cfg && cfg.url && cfg.anonKey) {
      shareState.base = { url: String(cfg.url).replace(/\/$/, ""), key: cfg.anonKey };
    }
  } catch { /* ignore */ }
  return shareState.base;
}

function refreshShareChips() {
  document.querySelectorAll(".share-count").forEach((el) => {
    const code = el.dataset.code || "";
    const n = shareState.counts[code] || 0;
    const b = el.querySelector("b");
    if (b) b.textContent = n;
    el.hidden = n <= 0;
    if (n > 0) el.title = `شارك هذا التقييم ${n} مرة`;
  });
}

async function loadShareCounts() {
  if (shareState.loaded) return;
  shareState.loaded = true;
  try {
    const base = await shareCountsBase();
    if (!base) return;
    const res = await fetch(`${base.url}/rest/v1/share_counts?select=opportunity_code,count`, {
      headers: { apikey: base.key, Authorization: `Bearer ${base.key}` },
    });
    if (!res.ok) return;
    const rows = await res.json();
    (rows || []).forEach((r) => {
      if (r && r.opportunity_code) shareState.counts[r.opportunity_code] = Number(r.count || 0);
    });
    refreshShareChips();
  } catch { /* ignore */ }
}

function incrementShare(code) {
  if (!code) return;
  shareState.counts[code] = (shareState.counts[code] || 0) + 1;
  refreshShareChips();
  shareCountsBase().then((base) => {
    if (!base) return;
    fetch(`${base.url}/rest/v1/rpc/increment_share`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: base.key, Authorization: `Bearer ${base.key}` },
      body: JSON.stringify({ p_code: code }),
    }).catch(() => {});
  });
}

// شارة العدّاد داخل بطاقة تقييم — تُبنى من الحالة المحمّلة (قد تكتمل القراءة قبل رسم البطاقات)،
// ومخفية حتى يتجاوز العدّاد الصفر.
function shareCounterChip(code) {
  const n = shareState.counts[code] || 0;
  return `<span class="share-count" data-code="${escapeHtml(code || "")}" ${n > 0 ? "" : "hidden"}>🔄 <b>${n}</b></span>`;
}

// ===== الحساب المجاني (المهمتان 2 و4): تسجيل بالهاتف + بحث محفوظ + تنبيهات =====
// السرّ (مفتاح الملكية) والهاتف في localStorage — بلا كلمة مرور، ولا يُكشف السرّ أبدًا.
const accountState = {
  secret: "",
  phone: "",
  saved: [],
  loaded: false,
  isLoggedIn() {
    return Boolean(this.secret);
  },
};

function accountLoad() {
  try {
    accountState.secret = localStorage.getItem("alforaij_secret") || "";
    accountState.phone = localStorage.getItem("alforaij_phone") || "";
  } catch {
    /* ignore */
  }
}

function accountSave() {
  try {
    if (accountState.secret) localStorage.setItem("alforaij_secret", accountState.secret);
    else localStorage.removeItem("alforaij_secret");
    if (accountState.phone) localStorage.setItem("alforaij_phone", accountState.phone);
    else localStorage.removeItem("alforaij_phone");
  } catch {
    /* ignore */
  }
}

function accountLogout() {
  accountState.secret = "";
  accountState.phone = "";
  accountState.saved = [];
  accountState.loaded = false;
  alertState.alerts = [];
  alertState.loaded = false;
  portfolioState.items = [];
  portfolioState.loaded = false;
  accountSave();
  // مسح بيانات Google المحفوظة
  try {
    localStorage.removeItem("alforaij_user_name");
    localStorage.removeItem("alforaij_user_avatar");
    localStorage.removeItem("alforaij_user_provider");
  } catch { /* ignore */ }
  renderAccountStatus();
  renderSavedSearches();
  portfolioShowHide();
  renderBell();
  closeBell();
  showAccountMsg("سجّلت خروجك من هذا الجهاز.", false);
}

accountLoad();

// ── إخفاء زر Google إذا لم يكن Client ID متاحاً ──
fetch("/api/google-client-id")
  .then(r => r.json())
  .then(cfg => {
    if (!cfg.client_id) {
      const wrap = $("googleSignInWrap");
      if (wrap) wrap.style.display = "none";
    } else {
      localStorage.setItem("alforaij_google_client_id", cfg.client_id);
    }
  })
  .catch(() => {
    const wrap = $("googleSignInWrap");
    if (wrap) wrap.style.display = "none";
  });

// قاعدة Supabase (عنوان + مفتاح anon): تُقرأ من /api/live-db التي يقدمها الخادم حيًا
// أو اللقطة الثابتة على الموقع المنشور — أي فشل يُبتلع صامتًا (درس فحص الجوال).
let _supabaseBaseCache = null;
async function supabaseBase() {
  if (_supabaseBaseCache) return _supabaseBaseCache;
  try {
    const cfg = await getJson("/api/live-db");
    if (cfg && cfg.url && cfg.anonKey) {
      _supabaseBaseCache = { url: String(cfg.url).replace(/\/$/, ""), key: cfg.anonKey };
    }
  } catch {
    /* ignore */
  }
  return _supabaseBaseCache;
}

// نداء دالة RPC محروس: أي فشل يُرجع null بصمت — لا أخطاء كونسول من الميزة أبدًا.
async function supabaseRpc(name, args) {
  try {
    const base = await supabaseBase();
    if (!base) return null;
    const res = await fetch(`${base.url}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: base.key, Authorization: `Bearer ${base.key}` },
      body: JSON.stringify(args || {}),
    });
    if (!res.ok) return null;
    const raw = await res.text();
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function normalizePhoneKw(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  // Strip leading 00 international prefix
  const d = digits.startsWith("00") ? digits.slice(2) : digits;
  // Kuwaiti local 8-digit numbers (legacy — must come before generic rule)
  if (d.length === 8 && /^[2-9]/.test(d)) return "+965" + d;
  // Any international number with country code (8-15 digits, starts with non-zero)
  if (d.length >= 8 && d.length <= 15 && !d.startsWith("0")) {
    return "+" + d;
  }
  return "";
}

function showAccountMsg(text, isError) {
  const msg = $("accountMsg");
  if (!msg) return;
  msg.textContent = text;
  msg.className = "account-msg" + (isError ? " error" : " ok");
  msg.hidden = false;
}

function renderAccountStatus() {
  const el = $("accountStatus");
  if (!el) return;
  if (accountState.secret) {
    el.hidden = false;
    const userName = localStorage.getItem("alforaij_user_name") || "";
    const userAvatar = localStorage.getItem("alforaij_user_avatar") || "";
    const provider = localStorage.getItem("alforaij_user_provider") || "phone";
    const avatarHtml = userAvatar ? `<img src="${escapeHtml(userAvatar)}" alt="" class="account-avatar" referrerpolicy="no-referrer">` : "";
    const displayName = userName || accountState.phone || "";
    const providerBadge = provider === "google" ? ` <span class="provider-badge google">G</span>` : "";
    el.innerHTML = `${avatarHtml} مسجّل ✓ — <b>${escapeHtml(displayName)}</b>${providerBadge}
      <button type="button" class="account-logout" id="accountLogoutBtn">تسجيل خروج</button>`;
    const btn = $("accountLogoutBtn");
    if (btn) btn.onclick = accountLogout;
  } else {
    el.hidden = true;
  }
}

function openAccountModal() {
  const modal = $("accountModal");
  if (!modal) return;
  modal.hidden = false;
  renderAccountStatus();
  portfolioShowHide();
  // إظهار زر Google دائماً (الافتراضي: متاح)
  const googleWrap = $("googleSignInWrap");
  if (googleWrap) {
    googleWrap.style.display = "";
  }
  const phoneEl = $("accountPhone");
  const stepPhone = $("accountStepPhone");
  const stepOtp = $("accountStepOtp");
  const msg = $("accountMsg");
  if (accountState.secret) {
    if (stepPhone) stepPhone.hidden = true;
    if (stepOtp) stepOtp.hidden = true;
    if (msg) msg.hidden = true;
  } else {
    if (stepPhone) stepPhone.hidden = false;
    if (stepOtp) stepOtp.hidden = true;
    if (phoneEl) phoneEl.value = accountState.phone || "";
    if (msg) msg.hidden = true;
    // تنسيق تلقائي لرقم الهاتف أثناء الكتابة
    _attachPhoneFormatter();
    setTimeout(() => phoneEl && phoneEl.focus(), 60);
  }
}

/** تنسيق رقم الهاتف تلقائياً: يحذف الأصفار الزائدة بعد رمز الدولة */
function _attachPhoneFormatter() {
  const phoneEl = $("accountPhone");
  const codeEl = $("phoneCountryCode");
  if (!phoneEl || phoneEl._formatterAttached) return;
  phoneEl._formatterAttached = true;
  phoneEl.addEventListener("input", function () {
    let val = this.value.replace(/[^\d+]/g, "");
    // إذا المستخدم كتب رمز الدولة مع الرقم، نحذف القيمة من حقل الدولة
    const m = val.match(/^(\+\d{1,3})(.+)$/);
    if (m && codeEl) {
      codeEl.value = m[1];
      val = m[2];
    }
    // حذف الأصفار الزائدة في البداية (البادئة المحلية)
    val = val.replace(/^0+/, "");
    this.value = val;
  });
}

function closeAccountModal() {
  const modal = $("accountModal");
  if (modal) modal.hidden = true;
}

async function accountRequestOtp() {
  const sendBtn = $("accountSendOtp");
  const raw = (($("accountPhone") || {}).value || "").trim();
  const countryCodeEl = document.getElementById("phoneCountryCode");
  const countryCode = countryCodeEl ? countryCodeEl.value : "";
  // If user typed full international number, use normalizePhoneKw; otherwise combine with selector
  let phone;
  if (raw.startsWith("+")) {
    // المستخدم أدخل الرقم كاملاً مع رمز الدولة
    phone = normalizePhoneKw(raw);
  } else {
    // حذف الأصفار الزائدة (بما فيها الصفر الأولي)
    const localNum = raw.replace(/^0+/, "");
    if (!localNum) {
      showAccountMsg("أدخل رقم الهاتف بدون رمز الدولة (مثال: 1064955051)", true);
      return;
    }
    phone = normalizePhoneKw(countryCode + localNum);
  }
  if (!phone) {
    showAccountMsg("أدخل رقم الهاتف من القائمة ثم الرقم (مثال: 55512345)", true);
    return;
  }
  if (sendBtn) sendBtn.disabled = true;
  try {
    // Try Supabase RPC first, fall back to backend /api/register
    let res = await supabaseRpc("register_user", { p_phone: phone });
    if (!res || !res.code || res.message || (res.error && !res.status)) {
      // Fallback: call backend /api/register which supports international numbers + WhatsApp delivery
      try {
        const apiRes = await fetch("/api/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: phone }),
        });
        const apiData = await apiRes.json();
        if (apiRes.ok && (apiData.code || apiData.delivery)) {
          res = apiData; // {status: 'ok', delivery: 'on_screen', code: '...', expires_in_seconds: 600}
        }
      } catch {
        /* backend unavailable */
      }
    }
    if (!res || (!res.code && !res.status)) {
      showAccountMsg("تعذر إرسال الرمز — أعد المحاولة بعد قليل", true);
      return;
    }
    accountState.phone = phone;
    accountSave();
    const stepPhone = $("accountStepPhone");
    const stepOtp = $("accountStepOtp");
    if (stepPhone) stepPhone.hidden = true;
    if (stepOtp) stepOtp.hidden = false;
    const note = $("accountOtpNote");
    if (note) {
      note.innerHTML =
        res.delivery === "whatsapp"
          ? `أرسلنا رمز التحقق عبر واتساب إلى <b>${escapeHtml(phone)}</b>.`
          : `الرمز: <b>${escapeHtml(res.code)}</b> — أدخله في الخانة لتأكيد تسجيل <b>${escapeHtml(phone)}</b>.`;
    }
    const codeEl = $("accountOtpCode");
    if (codeEl) codeEl.value = "";
    const msg = $("accountMsg");
    if (msg) msg.hidden = true;
    setTimeout(() => codeEl && codeEl.focus(), 60);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

async function accountVerifyOtp() {
  const verifyBtn = $("accountVerifyBtn");
  const code = (($("accountOtpCode") || {}).value || "").trim();
  if (code.length !== 6) {
    showAccountMsg("أدخل الرمز المكوّن من 6 أرقام", true);
    return;
  }
  if (verifyBtn) verifyBtn.disabled = true;
  try {
    // Try Supabase RPC first, fall back to backend /api/verify-otp
    let res = await supabaseRpc("verify_otp_code", { p_phone: accountState.phone, p_code: code });
    if (!res || !res.secret || res.message || (res.error && !res.status)) {
      // Fallback: call backend /api/verify-otp (retry up to 2x if no_otp — background upsert may still be in flight)
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const apiRes = await fetch("/api/verify-otp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone: accountState.phone, code: code }),
          });
          const apiData = await apiRes.json();
          if (apiRes.ok && apiData.secret) {
            res = apiData;
            break;
          }
          if (apiData.error === "no_otp" && attempt === 0) {
            await new Promise(r => setTimeout(r, 2000)); // wait for background upsert
            continue;
          }
          res = apiData;
          break;
        } catch {
          break;
        }
      }
    }
    if (!res || !res.secret) {
      showAccountMsg("الرمز غير صحيح أو منتهي — أعد المحاولة أو أرسل رمزًا جديدًا", true);
      return;
    }
    accountState.secret = res.secret;
    accountState.phone = res.phone || accountState.phone;
    accountSave();
    const stepOtp = $("accountStepOtp");
    if (stepOtp) stepOtp.hidden = true;
    renderAccountStatus();
    showAccountMsg("تم التسجيل بنجاح ✓ — تنبيهاتك مفعّلة", false);
    loadSavedSearches();
    loadUserAlerts();
    loadPortfolio();
  } finally {
    if (verifyBtn) verifyBtn.disabled = false;
  }
}

// ── تسجيل الدخول عبر Google ──
function googleLogin() {
  const CLIENT_ID = window.GOOGLE_CLIENT_ID || localStorage.getItem("alforaij_google_client_id") || "";
  if (CLIENT_ID) {
    _startGoogleSignIn(CLIENT_ID);
    return;
  }
  fetch("/api/google-client-id")
    .then(r => r.json())
    .then(cfg => {
      if (cfg.client_id) {
        localStorage.setItem("alforaij_google_client_id", cfg.client_id);
        _startGoogleSignIn(cfg.client_id);
      } else {
        showAccountMsg("تسجيل الدخول بـ Google غير متاح حاليًا — استخدم رقم الهاتف", true);
      }
    })
    .catch(() => {
      showAccountMsg("تعذر الاتصال — أعد المحاولة", true);
    });
}

function _startGoogleSignIn(clientId) {
  if (typeof google === "undefined" || !google.accounts) {
    showAccountMsg("جاري تحميل Google — أعد المحاولة", true);
    return;
  }
  google.accounts.id.initialize({ client_id: clientId, callback: _handleGoogleCredential });
  google.accounts.id.prompt();
}

async function _handleGoogleCredential(response) {
  if (!response || !response.credential) return;
  showAccountMsg("جاري التحقق من حساب Google...", false);
  try {
    const res = await fetch("/api/google-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    const data = await res.json();
    if (!res.ok || !data.secret) {
      showAccountMsg(data.detail || "تعذر تسجيل الدخول بـ Google", true);
      return;
    }
    accountState.secret = data.secret;
    accountState.phone = data.phone || "";
    accountSave();
    // حفظ معلومات الملف الشخصي
    try {
      localStorage.setItem("alforaij_user_name", data.name || "");
      localStorage.setItem("alforaij_user_avatar", data.avatar || "");
      localStorage.setItem("alforaij_user_provider", data.provider || "phone");
    } catch { /* ignore */ }
    const stepPhone = $("accountStepPhone");
    const stepOtp = $("accountStepOtp");
    if (stepPhone) stepPhone.hidden = true;
    if (stepOtp) stepOtp.hidden = true;
    renderAccountStatus();
    showAccountMsg(`تم تسجيل الدخول بنجاح ✓ — مرحباً ${escapeHtml(data.name || "")}`, false);
    loadSavedSearches();
    loadUserAlerts();
    loadPortfolio();
  } catch (e) {
    showAccountMsg("خطأ في الاتصال — أعد المحاولة", true);
    console.error("Google login error:", e);
  }
}

/* ─── تسجيل الدخول بـ Apple ─── */
function appleLogin() {
  // Apple Sign-In via Apple JS SDK (يُحمّل من cdn-apple.com)
  if (typeof AppleID === "undefined" || !AppleID.auth) {
    // تحميل SDK إذا لم يكن محمّلاً
    const script = document.createElement("script");
    script.src = "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js";
    script.async = true;
    script.onload = () => _initAppleSignIn();
    script.onerror = () => showAccountMsg("تعذر تحميل Apple SDK — أعد المحاولة", true);
    document.head.appendChild(script);
  } else {
    _initAppleSignIn();
  }
}

function _initAppleSignIn() {
  const clientId = window.APPLE_CLIENT_ID || localStorage.getItem("alforaij_apple_client_id") || "";
  if (!clientId) {
    // بدون Client ID: نستخدم بديل — نطلب البريد الإلكتروني يدوياً
    showAccountMsg("تسجيل الدخول بـ Apple يتطلب Client ID. استخدم رقم الهاتف مؤقتاً.", true);
    return;
  }
  try {
    AppleID.auth.init({
      clientId: clientId,
      scope: "name email",
      redirectURI: window.location.origin,
      usePopup: true,
    });
    AppleID.auth.signIn();
  } catch (e) {
    showAccountMsg("خطأ في بدء تسجيل الدخول بـ Apple", true);
    console.error("Apple login init error:", e);
  }
}

// استقبال callback من Apple Sign-In
async function _handleAppleCredential(response) {
  if (!response || !response.code) return;
  showAccountMsg("جاري التحقق من حساب Apple...", false);
  try {
    const res = await fetch("/api/apple-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: response.code,
        id_token: response.id_token || "",
        user: response.user || null,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.secret) {
      showAccountMsg(data.detail || "تعذر تسجيل الدخول بـ Apple", true);
      return;
    }
    accountState.secret = data.secret;
    accountState.phone = data.phone || "";
    accountSave();
    try {
      localStorage.setItem("alforaij_user_name", data.name || "");
      localStorage.setItem("alforaij_user_avatar", "");
      localStorage.setItem("alforaij_user_provider", data.provider || "apple");
    } catch { /* ignore */ }
    const stepPhone = $("accountStepPhone");
    const stepOtp = $("accountStepOtp");
    if (stepPhone) stepPhone.hidden = true;
    if (stepOtp) stepOtp.hidden = true;
    renderAccountStatus();
    showAccountMsg(`تم تسجيل الدخول بنجاح ✓ — مرحباً ${escapeHtml(data.name || "")}`, false);
    loadSavedSearches();
    loadUserAlerts();
    loadPortfolio();
  } catch (e) {
    showAccountMsg("خطأ في الاتصال — أعد المحاولة", true);
    console.error("Apple login error:", e);
  }
}

// حفظ البحث الحالي (من الفلاتر الحالية في صفحة البحث) مع تفعيل التنبيه
async function handleSaveSearch() {
  if (!accountState.secret) {
    showAccountMsg("");
    openAccountModal();
    return;
  }
  const filters = collectAdvancedFilters();
  const typed = (($("chatInput") || {}).value || "").trim();
  const text = typed || buildTextFromFilters(filters);
  if (!text) {
    showAccountMsg("لا يوجد بحث للحفظ — نفّذ بحثًا أولًا", true);
    return;
  }
  const isRent = /إيجار|ايجار/.test(String(filters.transaction || ""));
  const budgetRaw = isRent ? filters.rentBudget : filters.budget;
  const budget = budgetRaw ? Number(budgetRaw) : null;
  const res = await supabaseRpc("save_search", {
    p_secret: accountState.secret,
    p_name: String(text).slice(0, 60),
    p_request: text,
    p_transaction: filters.transaction,
    p_property: filters.propertyType,
    p_areas: String(filters.areas || "")
      .split(/[،,]/)
      .map((s) => s.trim())
      .filter(Boolean),
    p_govs: filters.governorate ? [filters.governorate] : [],
    p_min: null,
    p_max: Number.isFinite(budget) ? budget : null,
    p_id: 0,
  });
  const msgEl = $("saveSearchMsg");
  if (res) {
    loadSavedSearches().then(() => {
      const box = $("savedSearchesBox");
      if (box) box.hidden = false;
    });
    if (msgEl) {
      msgEl.textContent = "تم الحفظ ✓ — سننبّهك عند نزول فرصة مطابقة.";
      msgEl.className = "save-search-msg ok";
      msgEl.hidden = false;
      setTimeout(() => {
        if (msgEl) msgEl.hidden = true;
      }, 6000);
    }
  } else if (msgEl) {
    msgEl.textContent = "تعذر الحفظ — تحقق من اتصالك وأعد المحاولة";
    msgEl.className = "save-search-msg error";
    msgEl.hidden = false;
  }
}

async function loadSavedSearches() {
  if (!accountState.secret) return;
  const rows = await supabaseRpc("list_saved_searches", { p_secret: accountState.secret });
  accountState.saved = Array.isArray(rows) ? rows : [];
  accountState.loaded = true;
  renderSavedSearches();
}

function renderSavedSearches() {
  const box = $("savedSearchesBox");
  if (!box) return;
  if (!accountState.secret) {
    box.hidden = true;
    return;
  }
  // لا نغيّر حالة الإظهار هنا — إظهار/إخفاء الصندوق من اختصاص زر «بحثي المحفوظ»
  // ولحظة الحفظ؛ هذا يُملأ المحتوى فقط حتى لا يقفز الصندوق ظاهرًا عند كل إقلاع.
  const list = accountState.saved || [];
  if (!list.length) {
    box.innerHTML =
      '<div class="saved-empty">لا أبحاث محفوظة بعد — نفّذ بحثًا ثم اضغط «احفظ البحث ونبّهني».</div>';
    return;
  }
  box.innerHTML =
    `<div class="saved-title">بحثي المحفوظ (${list.length})</div>` +
    list
      .map(
        (s) => `
      <div class="saved-item" data-id="${Number(s.id)}">
        <div class="saved-info">
          <strong>${escapeHtml(s.name || "")}</strong>
          <span>${escapeHtml(s.request_text || "")}</span>
        </div>
        <div class="saved-actions">
          <label class="saved-alert" title="تنبيه واتساب عند نزول فرصة مطابقة">
            <input type="checkbox" data-alert="${Number(s.id)}" ${s.alert_enabled ? "checked" : ""}> تنبيه
          </label>
          <button class="saved-del" data-del="${Number(s.id)}" type="button" aria-label="حذف البحث">حذف</button>
        </div>
      </div>`
      )
      .join("");
}

function toggleSavedSearches() {
  const box = $("savedSearchesBox");
  if (!box) return;
  if (box.hidden) {
    if (accountState.secret && !accountState.loaded) loadSavedSearches();
    box.hidden = false;
  } else {
    box.hidden = true;
  }
}

function bindSavedSearchesEvents() {
  const box = $("savedSearchesBox");
  if (!box) return;
  box.addEventListener("change", (e) => {
    const cb = e.target.closest && e.target.closest("input[data-alert]");
    if (!cb || !accountState.secret) return;
    supabaseRpc("set_search_alert", {
      p_secret: accountState.secret,
      p_id: Number(cb.dataset.alert),
      p_enabled: cb.checked,
    });
  });
  box.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button[data-del]");
    if (!btn || !accountState.secret) return;
    supabaseRpc("delete_saved_search", {
      p_secret: accountState.secret,
      p_id: Number(btn.dataset.del),
    }).then(() => loadSavedSearches());
  });
}

// ─── Smart Alerts: تنبيهات ذكية ───
let _smartAlertsData = [];

async function refreshSmartAlerts() {
  const list = $("smartAlertsList");
  if (!list) return;
  if (!accountState.secret) {
    list.innerHTML = '<p class="smart-alerts-empty">سجّل دخولك لتفعيل التنبيهات الذكية</p>';
    return;
  }
  list.innerHTML = '<p class="smart-alerts-empty">جاري التحقق...</p>';
  try {
    const res = await fetch("/api/smart-alerts/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_secret: accountState.secret }),
    });
    const data = await res.json();
    if (data.error) {
      list.innerHTML = '<p class="smart-alerts-empty">' + escapeHtml(data.detail || data.error) + '</p>';
      return;
    }
    _smartAlertsData = (data.priceDrops || []).concat(data.newListings || []);
    _renderSmartAlerts(list, _smartAlertsData);
    // إظهار زر الاشتراك إذا كانت هناك منطقة في نتائج البحث الحالية
    _updateSmartAlertSubscribe();
  } catch (e) {
    list.innerHTML = '<p class="smart-alerts-empty">خطأ في الاتصال</p>';
  }
}

function _renderSmartAlerts(container, alerts) {
  if (!alerts.length) {
    container.innerHTML = '<p class="smart-alerts-empty">لا توجد تنبيهات جديدة — سنبّهك عند ظهور فرصة مطابقة</p>';
    return;
  }
  container.innerHTML = alerts.slice(0, 10).map(a => {
    const icon = a.type === "price_drop" ? "📉" : a.type === "new_listing" ? "🏢" : "💰";
    const sevClass = a.severity || "info";
    return '<div class="smart-alert-item">'
      + '<span class="smart-alert-icon">' + icon + '</span>'
      + '<div class="smart-alert-body">'
      + '<span class="alert-msg">' + escapeHtml(a.message || "") + '</span>'
      + '<span class="alert-meta">' + (a.area || "") + (a.price ? ' — ' + formatMoney(a.price) + ' د.ك' : '') + '</span>'
      + '</div>'
      + '<span class="smart-alert-severity ' + sevClass + '">' + (a.severity === 'high' ? 'مهم' : a.severity === 'medium' ? 'متوسط' : 'جديد') + '</span>'
      + '</div>';
  }).join("");
}

function _updateSmartAlertSubscribe() {
  const wrap = $("smartAlertSubscribe");
  const areaEl = $("smartAlertSubscribeArea");
  if (!wrap || !areaEl) return;
  //خذ المنطقة من أول نتيجة بحث
  const firstResult = (window._lastSearchResults || [])[0];
  if (firstResult && firstResult.area) {
    areaEl.textContent = "المنطقة: " + firstResult.area;
    wrap.hidden = false;
  } else {
    wrap.hidden = true;
  }
}

async function subscribeSmartAlert() {
  if (!accountState.secret) {
    openAccountModal();
    return;
  }
  const firstResult = (window._lastSearchResults || [])[0];
  const area = firstResult && firstResult.area;
  if (!area) {
    alert("حدد منطقة في البحث أولاً");
    return;
  }
  try {
    const res = await fetch("/api/smart-alerts/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_secret: accountState.secret, area: area }),
    });
    const data = await res.json();
    if (data.status === "ok") {
      const msg = $("smartAlertSubscribeArea");
      if (msg) msg.textContent = "✅ تم الاشتراك في تنبيهات " + area;
      const btn = $("smartAlertSubscribeBtn");
      if (btn) btn.hidden = true;
    }
  } catch (e) {
    alert("خطأ في الاتصال");
  }
}

// تحميل التنبيهات عند فتح التبويب
function initSmartAlerts() {
  if (accountState.secret) {
    refreshSmartAlerts();
  }
}

// ===== محفظة المستثمر المجانية: سجّل عقاراتك وتتبّع قيمتها التقديرية وعائدها =====
const portfolioState = { items: [], loaded: false, trends: null, forecast: null };

// مصادر التقييم: التوقعات (سعر المتر المتوقع لكل منطقة) ثم price_trends — تُحمَّل مرة واحدة.
async function ensurePortfolioData() {
  if (!portfolioState.trends) {
    portfolioState.trends = await getJson("/api/price-trends")
      .then((d) => (d && Array.isArray(d.rows) ? d.rows : null))
      .catch(() => null);
  }
  if (!portfolioState.forecast) {
    if (oppState.data && Array.isArray(oppState.data.forecast)) {
      portfolioState.forecast = oppState.data.forecast;
    } else {
      const opp = await getJson("/api/opportunities").catch(() => null);
      portfolioState.forecast = opp && Array.isArray(opp.forecast) ? opp.forecast : null;
    }
  }
}

// مرآة جافاسكربت لمنطق portfolio.py النقي (نفس قواعد التطبيع والاختيار).
function portfolioNorm(text) {
  return String(text || "")
    .replace(/[\u0640]/g, "")
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي")
    .replace(/\s+/g, " ")
    .trim();
}

function portfolioEstimate(item) {
  const space = Number(item.space);
  const purchase = Number(item.purchase_price);
  const rent = Number(item.monthly_rent);
  const areaN = portfolioNorm(item.area);
  let perSqm = null;
  const forecast = portfolioState.forecast || [];
  for (const entry of forecast) {
    if (portfolioNorm(entry.area) !== areaN) continue;
    const v = Number(entry.expectedPricePerSqm);
    if (Number.isFinite(v) && v > 0 && (perSqm === null || v > perSqm)) perSqm = v;
  }
  if (!(perSqm > 0)) {
    const trends = portfolioState.trends || [];
    let bestType = null;
    let bestArea = null;
    const typeN = portfolioNorm(item.property_type);
    for (const t of trends) {
      const v = Number(t.median_price_per_m2);
      if (!Number.isFinite(v) || v <= 0 || portfolioNorm(t.area) !== areaN) continue;
      const month = String(t.month || "");
      if (portfolioNorm(t.property_type) && portfolioNorm(t.property_type) === typeN) {
        if (!bestType || month > bestType.month) bestType = { month, v };
      }
      if (!bestArea || month > bestArea.month) bestArea = { month, v };
    }
    perSqm = bestType ? bestType.v : bestArea ? bestArea.v : null;
  }
  const value = Number.isFinite(space) && space > 0 && perSqm !== null && perSqm > 0 ? space * perSqm : null;
  const changePct = value !== null && Number.isFinite(purchase) && purchase > 0 ? ((value - purchase) / purchase) * 100 : null;
  const yieldPct = Number.isFinite(rent) && rent > 0 && Number.isFinite(purchase) && purchase > 0 ? (rent * 12 / purchase) * 100 : null;
  return {
    estimatedValue: value !== null ? Math.round(value) : null,
    changePct: changePct !== null ? Math.round(changePct * 10) / 10 : null,
    yieldPct: yieldPct !== null ? Math.round(yieldPct * 10) / 10 : null,
  };
}

async function loadPortfolio() {
  if (!accountState.secret) return;
  const rows = await supabaseRpc("list_portfolio_items", { p_secret: accountState.secret });
  portfolioState.items = Array.isArray(rows) ? rows : [];
  portfolioState.loaded = true;
  renderPortfolio();
}

// يعرض/يخفي قسم المحفظة حسب حالة التسجيل — يُستدعى عند فتح نافذة الحساب وبعد كل تسجيل/خروج.
function portfolioShowHide() {
  const wrap = $("portfolioWrap");
  if (!wrap) return;
  wrap.hidden = !accountState.isLoggedIn();
  if (accountState.isLoggedIn() && !portfolioState.loaded) loadPortfolio();
}

async function renderPortfolio() {
  const list = $("portfolioList");
  if (!list) return;
  await ensurePortfolioData();
  const items = portfolioState.items || [];
  if (!items.length) {
    list.innerHTML = '<div class="saved-empty">لا عقارات بعد — أضف أول عقار لتتتبّع قيمته التقديرية وعائده.</div>';
    return;
  }
  list.innerHTML =
    `<div class="saved-title">عقاراتي (${items.length})</div>` +
    items
      .map((item) => {
        const est = portfolioEstimate(item);
        const change =
          est.changePct !== null
            ? `<span class="pf-change ${est.changePct >= 0 ? "up" : "down"}">${est.changePct >= 0 ? "+" : ""}${est.changePct}%</span>`
            : "";
        return `
      <article class="portfolio-item" data-id="${Number(item.id)}">
        <div class="portfolio-item-head">
          <strong>${escapeHtml(item.area || "")}${item.property_type ? ` · ${escapeHtml(item.property_type)}` : ""}</strong>
          <button type="button" class="saved-del" data-pf-del="${Number(item.id)}" aria-label="حذف العقار">حذف</button>
        </div>
        <div class="portfolio-stats">
          <span>المساحة: ${item.space ? `${Number(item.space).toLocaleString("en-US")} م²` : "—"}</span>
          <span>الشراء: ${oppMoney(item.purchase_price)}</span>
          <span>الإيجار: ${oppMoney(item.monthly_rent)}/شهر</span>
        </div>
        <div class="portfolio-value">
          القيمة التقديرية الحالية: <strong>${oppMoney(est.estimatedValue)}</strong> ${change}
          <span class="portfolio-yield">عائد سنوي تقديري: ${est.yieldPct !== null ? `${est.yieldPct}%` : "—"}</span>
        </div>
      </article>`;
      })
      .join("");
}

async function portfolioSave(ev) {
  if (ev && ev.preventDefault) ev.preventDefault();
  if (!accountState.secret) {
    showAccountMsg("سجّل حسابك أولًا لحفظ عقاراتك", true);
    return false;
  }
  const area = (($("pfArea") || {}).value || "").trim();
  if (!area) {
    showAccountMsg("أدخل اسم المنطقة", true);
    return false;
  }
  const res = await supabaseRpc("save_portfolio_item", {
    p_secret: accountState.secret,
    p_area: area,
    p_governorate: "",
    p_property_type: (($("pfType") || {}).value || "").trim(),
    p_space: Number(($("pfSpace") || {}).value) || null,
    p_purchase_price: Number(($("pfPrice") || {}).value) || null,
    p_purchase_date: (($("pfDate") || {}).value || "").trim(),
    p_monthly_rent: Number(($("pfRent") || {}).value) || null,
    p_note: "",
  });
  if (res == null) {
    showAccountMsg("تعذر الحفظ — أعد المحاولة لاحقًا", true);
    return false;
  }
  const form = $("portfolioForm");
  if (form) form.reset();
  await loadPortfolio();
  showAccountMsg("أُضيف العقار إلى محفظتك ✓", false);
  return false;
}

function bindPortfolioEvents() {
  const list = $("portfolioList");
  if (!list) return;
  list.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button[data-pf-del]");
    if (!btn || !accountState.secret) return;
    supabaseRpc("delete_portfolio_item", {
      p_secret: accountState.secret,
      p_id: Number(btn.dataset.pfDel),
    }).then(() => loadPortfolio());
  });
}

// ===== جدول «بداية التغطية لكل منصة» في صفحة لماذا مجاني وأدق =====
async function renderPlatformDates() {
  const wrap = $("platformDatesWrap");
  if (!wrap) return;
  try {
    const data = await getJson("/api/platform-dates");
    const platforms = data && Array.isArray(data.platforms) ? data.platforms : [];
    if (!platforms.length) {
      wrap.innerHTML = '<div class="saved-empty">بيانات بداية الحصاد غير متاحة بعد.</div>';
      return;
    }
    const fmt = (d) => (d ? String(d).replace(/-/g, "/") : "—");
    const rows = platforms
      .map(
        (p) => `
      <div class="coverage-row" role="row">
        <span class="coverage-src">${escapeHtml(p.source || "")}</span>
        <strong>${Number(p.count || 0).toLocaleString("en-US")}</strong>
        <span>${fmt(p.firstFetch)}</span>
        <span>${fmt(p.earliestPublished)}</span>
      </div>`
      )
      .join("");
    wrap.innerHTML =
      `<div class="coverage-row coverage-head" role="row">
        <span>المنصة</span><span>إعلانات</span><span>أول جلب</span><span>أقدم تاريخ نشر معروف</span>
      </div>` + rows;
  } catch {
    wrap.innerHTML = '<div class="saved-empty">بيانات بداية الحصاد غير متاحة حاليًا.</div>';
  }
}

const PLATFORM_BUCKET_LABELS = {
  connected: "متصل ويدخل التقييم",
  conditional: "مشروط بجودة البيانات",
  official: "رسمي/تحقق",
  partner_required: "يحتاج شراكة أو اشتراك مرخص",
  reference: "مرجع مساعد",
  inactive: "غير نشط حاليًا",
};

async function loadPlatformIntelligence() {
  const root = $("platformIntelRoot");
  const meta = $("platformIntelMeta");
  if (!root) return;
  try {
    const data = await getJson("/api/platform-intelligence");
    const summary = data.summary || {};
    const sources = Array.isArray(data.sources) ? data.sources : [];
    const strategy = data.databaseStrategy || {};
    const highlight = sources
      .filter((s) => ["partner_required", "official", "conditional"].includes(s.bucket))
      .slice(0, 8);
    if (meta) {
      meta.textContent = `${Number(summary.connected || 0)} متصل · ${Number(summary.official || 0)} رسمي · ${Number(summary.partnerRequired || 0)} شراكة`;
    }
    const stats = [
      ["متصل", summary.connected],
      ["مشروط", summary.conditional],
      ["رسمي", summary.official],
      ["شراكة", summary.partnerRequired],
    ].map(([label, count]) => `<span><b>${Number(count || 0).toLocaleString("en-US")}</b>${escapeHtml(label)}</span>`).join("");
    const rules = (strategy.qualityRules || []).slice(0, 4)
      .map((rule) => `<li>${escapeHtml(rule)}</li>`)
      .join("");
    const rows = highlight.map((s) => `
      <article class="platform-intel-card">
        <div class="platform-intel-card-head">
          <h5>${escapeHtml(s.name)}</h5>
          <span class="platform-bucket bucket-${escapeHtml(s.bucket)}">${escapeHtml(PLATFORM_BUCKET_LABELS[s.bucket] || s.status || "مصدر")}</span>
        </div>
        <p>${escapeHtml(s.professionalUse || "")}</p>
        <dl>
          <div><dt>الربط</dt><dd>${escapeHtml(s.integrationMode || "")}</dd></div>
          <div><dt>الجداول</dt><dd>${escapeHtml((s.databaseTables || []).join("، "))}</dd></div>
        </dl>
        <small>${escapeHtml(s.nextAction || "")}</small>
      </article>
    `).join("");
    root.innerHTML = `
      <div class="platform-intel-stats">${stats}</div>
      <div class="platform-intel-rules">
        <strong>${escapeHtml(strategy.principle || "سياسة البيانات")}</strong>
        <ul>${rules}</ul>
      </div>
      <div class="platform-intel-cards">${rows || '<div class="empty">لا توجد مصادر تحتاج عرضًا خاصًا الآن.</div>'}</div>
    `;
  } catch {
    if (meta) meta.textContent = "";
    root.innerHTML = '<div class="saved-empty">خريطة الربط غير متاحة حاليًا، وباقي المنصة يعمل من سجل المصادر الأساسي.</div>';
  }
}

// ===== جرس التنبيهات (المهمة 4): عدّاد غير المقروء + قائمة منسدلة + «تم» =====
const alertState = { alerts: [], loaded: false };

async function loadUserAlerts() {
  if (!accountState.secret) return;
  const rows = await supabaseRpc("list_user_alerts", { p_secret: accountState.secret });
  alertState.alerts = Array.isArray(rows) ? rows : [];
  alertState.loaded = true;
  renderBell();
}

function renderBell() {
  const countEl = $("bellCount");
  const list = alertState.alerts || [];
  const unseen = list.filter((a) => !a.seen).length;
  if (countEl) {
    countEl.hidden = unseen <= 0;
    countEl.textContent = unseen > 99 ? "99+" : String(unseen);
    countEl.title = unseen > 0 ? `${unseen} تنبيه غير مقروء` : "لا تنبيهات غير مقروءة";
  }
  const dropdown = $("bellDropdown");
  if (!dropdown) return;
  if (!accountState.secret) {
    dropdown.innerHTML =
      '<div class="bell-empty">سجّل حسابك المجاني ثم احفظ بحثًا — سننبّهك عند نزول فرصة مطابقة.</div>';
    return;
  }
  if (!list.length) {
    dropdown.innerHTML =
      '<div class="bell-empty">لا تنبيهات بعد — احفظ بحثًا لننبّهك عند نزول فرصة مطابقة لبحثك.</div>';
    return;
  }
  dropdown.innerHTML =
    `<div class="bell-head">تنبيهاتي (${list.length}) <button type="button" class="bell-mark" id="bellMarkAll">تم — علّم الكل مقروءًا</button></div>` +
    list
      .map(
        (a) => `
      <div class="bell-item ${a.seen ? "seen" : ""}">
        <div class="bell-item-main">
          <strong>${a.change === "price_drop" ? "📉 انخفاض سعر" : "🆕 فرصة جديدة"}</strong>
          <span>${escapeHtml(a.message || "")}</span>
          <em>${escapeHtml(a.area || "")}${a.price ? ` — ${Number(a.price).toLocaleString("en-US")} د.ك` : ""}</em>
        </div>
        ${a.url ? `<a class="bell-open" href="${escapeHtml(a.url)}" target="_blank" rel="noreferrer">فتح الفرصة</a>` : ""}
      </div>`
      )
      .join("");
  const markBtn = $("bellMarkAll");
  if (markBtn) markBtn.onclick = markAllAlertsSeen;
}

function toggleBell() {
  const dropdown = $("bellDropdown");
  if (!dropdown) return;
  if (dropdown.hidden) {
    if (accountState.secret) loadUserAlerts();
    dropdown.hidden = false;
  } else {
    dropdown.hidden = true;
  }
}

async function markAllAlertsSeen() {
  if (!accountState.secret) return;
  await supabaseRpc("mark_alerts_seen", { p_secret: accountState.secret });
  (alertState.alerts || []).forEach((a) => (a.seen = true));
  renderBell();
}

function closeBell() {
  const dropdown = $("bellDropdown");
  if (dropdown) dropdown.hidden = true;
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
        ${shareCounterChip(item.code)}
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
        <label>رقم الهاتف (مطلوب)<input id="clientPhone" type="tel" placeholder="5XXXXXXX" pattern="[0-9]{8}" maxlength="8" required dir="ltr"></label>
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

// بناء صفوف الفرص الحالية (مع الفلاتر المطبقة) — مشترك بين CSV وTSV
function buildOppExportRows() {
  const items = lastOppTableItems || [];
  const clientText = (item) => (item.clients || []).map((c) => {
    const parts = [c.area || "", c.type || ""].filter(Boolean).join(" ");
    const match = c.matchScore != null ? `تطابق ${c.matchScore}/100` : "";
    return [parts, match, String(c.phones || "")].filter(Boolean).join(" — ");
  }).join(" ؛ ");
  const header = ["الكود", "المنطقة", "الفئة", "المصدر", "المحافظة", "نوع العقار", "المعاملة", "السعر", "سعر المتر", "العائد", "الثقة", "الدرجة", "الحكم", "العملاء المحتملون"];
  const rows = items.map((item) => [
    item.code || "",
    item.area || "",
    item.bestTier ? (OPP_TIER_LABELS[item.bestTier] || item.bestTier) : "",
    item.source || "",
    item.governorate || "",
    item.propertyType || "",
    item.transaction || "",
    item.priceText || oppMoney(item.price),
    item.pricePerSqm ? `${item.pricePerSqm} د.ك/م²` : "",
    item.rentalYieldPercent != null ? `${item.rentalYieldPercent}%` : "",
    item.confidence != null ? `${Math.round(Number(item.confidence) * 100)}%` : "",
    item.score != null ? Math.round(Number(item.score)) : "",
    item.valuationLabel || "",
    clientText(item),
  ]);
  return { header, rows, tierLabel: OPP_TIER_LABELS[oppState.tier] || oppState.tier || "الفرص" };
}

// تصدير الفرص الحالية إلى CSV (UTF-8 مع BOM) — الكود والسعر والدرجة والثقة والعملاء المحتملين
function exportOppTableCsv() {
  const { header, rows, tierLabel } = buildOppExportRows();
  const today = new Date().toISOString().slice(0, 10);
  const csv = "\uFEFF" + csvSerialize([header, ...rows]); // BOM حتى يفتح Excel العربي UTF-8 بشكل صحيح
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `افضل-الفرص-${tierLabel}-${today}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// نسخ نفس الفرص إلى الحافظة بصيغة TSV — لصق مباشر في Excel بدون ملف
function copyOppTableTsv(btn) {
  const { header, rows } = buildOppExportRows();
  copyText(tsvSerialize([header, ...rows]), btn);
}

// الجدول المضغوط لنفس فرص الكروت — نفس الصفوف بنفس الترتيب (نسخ/فتح تعمل كالكروت)
function renderOppTable(items) {
  const row = (item, i) => `
    <tr class="opp-table-row">
      <td class="opp-table-rank">${i + 1}</td>
      <td class="opp-table-name">
        <span class="opp-table-code">${escapeHtml(item.code || "—")}</span>
        <small>${escapeHtml(item.area || "")}${item.listingType && item.listingType !== "غير محدد" ? ` · ${escapeHtml(item.listingType)}` : ""}</small>
      </td>
      <td>${item.bestTier ? `<span class="opp-badge opp-badge-tier">${escapeHtml(OPP_TIER_LABELS[item.bestTier] || item.bestTier)}</span>` : "—"}</td>
      <td>${escapeHtml(item.source || "—")}</td>
      <td>${escapeHtml(item.governorate || "—")}</td>
      <td>${escapeHtml(item.propertyType || "—")}</td>
      <td>${escapeHtml(item.priceText || oppMoney(item.price))}</td>
      <td>${item.pricePerSqm ? `${escapeHtml(item.pricePerSqm)} د.ك/م²` : "—"}</td>
      <td>${item.rentalYieldPercent != null ? `${escapeHtml(item.rentalYieldPercent)}%` : "—"}</td>
      <td>${item.confidence != null ? `${Math.round(Number(item.confidence) * 100)}%` : "—"}</td>
      <td class="opp-table-score"><b>${item.score != null ? `${Math.round(Number(item.score))}/100` : "—"}</b><small>${escapeHtml(item.valuationLabel || "")}</small></td>
      <td class="opp-table-actions">
        ${item.url ? `<a class="open-link" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">فتح</a>` : ""}
        <button class="opp-copy-btn" type="button">نسخ</button>
      </td>
    </tr>`;
  return `
    <div class="gov-table-wrap opp-table-wrap">
      <table class="gov-table opp-table">
        <thead>
          <tr>
            <th class="opp-table-rank-col">#</th>
            <th class="opp-table-name-col">الفرصة</th>
            <th>الفئة</th>
            <th>المصدر</th>
            <th>المحافظة</th>
            <th>نوع العقار</th>
            <th>السعر</th>
            <th>سعر المتر</th>
            <th>العائد</th>
            <th>الثقة</th>
            <th class="opp-table-score-col">الدرجة</th>
            <th>إجراءات</th>
          </tr>
        </thead>
        <tbody>${items.map(row).join("")}</tbody>
      </table>
    </div>`;
}

function renderOppTier() {
  const root = $("oppList");
  if (!root || !oppState.data) return;
  // مرشّح المصدر ونوع الإعلان (مباشر/مكتب) خاص بتبويبات الفرص (الأفضل + الفئات الزمنية)
  const cardTiers = ["best", "daily", "weekly", "monthly", "yearly"];
  const isCardTier = cardTiers.includes(oppState.tier);
  const viewSwitch = $("oppViewSwitch");
  if (viewSwitch) viewSwitch.hidden = !isCardTier;
  // زرا تصدير/نسخ CSV خاصان بالجدول المضغوط في فئات الفرص البطاقية فقط
  const exportBtn = $("oppExportCsvBtn");
  if (exportBtn) exportBtn.hidden = !(isCardTier && oppState.view === "table");
  const oppCopyBtn = $("oppCopyBtn");
  if (oppCopyBtn) oppCopyBtn.hidden = !(isCardTier && oppState.view === "table");
  syncViewModeButtons();
  setOppSourceRowVisible(isCardTier);
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
  lastOppTableItems = items; // للتصدير: نفس الفرص المعروضة حاليًا (مع الفلاتر المطبقة)
  root.innerHTML = `<p class="scope-note">${escapeHtml(note)}</p>` +
    (items.length
      ? (oppState.view === "table" ? renderOppTable(items) : items.map(oppCard).join(""))
      : '<div class="empty">لا توجد فرص مطابقة للفلاتر الحالية.</div>');
  root.querySelectorAll(".opp-card .opp-reason").forEach(attachClampToggle);
  // أزرار التسويق في كل بطاقة/صف فرصة: نسخ/إرسال واتساب + إرسال شخصي لكل عميل — مع تتبع النقرات
  root.querySelectorAll(".opp-card, .opp-table-row").forEach((card, i) => {
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
      link.addEventListener("click", () => {
        trackOutreach({ action: "send", channel: "opportunity_card", opportunityCode: code });
        incrementShare(code);
      });
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
  // تحديث البطاقات العائمة بعد إعادة رسم الفرص
  if (window.hoverCard) hoverCard.refresh();
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
      let clients = [];
      try {
        const payload = await getJson("/api/clients");
        clients = payload.clients || [];
      } catch {
        // وضع الثابت: قراءة من localStorage
        try { clients = JSON.parse(localStorage.getItem(CLIENTS_KEY) || "[]"); } catch { clients = []; }
      }
      oppState.clients = clients;
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
  const oppExportBtn = $("oppExportCsvBtn");
  if (oppExportBtn) oppExportBtn.addEventListener("click", exportOppTableCsv);
  const oppCopyBtn = $("oppCopyBtn");
  if (oppCopyBtn) oppCopyBtn.addEventListener("click", () => copyOppTableTsv(oppCopyBtn));
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
  on("downloadExcelBtn", () => downloadExcelReport("downloadExcelBtn"));
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
  on("govExportCsvBtn", exportGovTableCsv);
  on("govCopyBtn", () => copyGovTableTsv($("govCopyBtn")));
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
    const viewBtn = ev.target.closest?.("[data-heat-view]");
    if (viewBtn) {
      ev.preventDefault();
      setHeatmapView(viewBtn.dataset.heatView);
      return;
    }
    const mapFilterClear = ev.target.closest?.("[data-map-filter-clear]");
    if (mapFilterClear) {
      ev.preventDefault();
      mapListingFilters.sources = [];
      mapListingFilters.types = [];
      renderMapListingFilters();
      renderMapListingPoints();
      return;
    }
    const mapFilterChip = ev.target.closest?.("[data-map-filter]");
    if (mapFilterChip) {
      ev.preventDefault();
      ev.stopPropagation();
      const field = mapFilterChip.dataset.mapFilter; // "sources" | "types"
      const key = mapFilterChip.dataset.mapFilterKey || "";
      const arr = mapListingFilters[field] || [];
      const idx = arr.indexOf(key);
      if (idx >= 0) arr.splice(idx, 1);
      else arr.push(key);
      renderMapListingFilters();
      renderMapListingPoints();
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
    // مبدّل عرض كروت المحافظات: شبكة/جدول — ذاكرة موحّدة مع أفضل الفرص
    // (إعادة رسم القسمين معًا حتى يظهر التغيير فورًا في أي تبويب مفتوح)
    const govViewBtn = ev.target.closest?.("[data-gov-view]");
    if (govViewBtn) {
      setViewMode(govViewBtn.dataset.govView);
      renderBoard();
      renderOppTier();
      return;
    }
    // مبدّل عرض الفرص: شبكة/جدول — نفس الذاكرة الموحّدة
    const oppViewBtn = ev.target.closest?.("[data-opp-view]");
    if (oppViewBtn) {
      setViewMode(oppViewBtn.dataset.oppView);
      renderOppTier();
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
      boardState.activeMetric = metric;
      boardState.selectedCell = { governorate: gov, area: area || "", metric };
      const metricFilter = $("boardMetricFilter");
      const govFilter = $("boardGovernorateFilter");
      const areaFilter = $("boardAreaFilter");
      if (metricFilter) metricFilter.value = metric;
      if (govFilter) govFilter.value = gov;
      if (areaFilter) areaFilter.value = area;
      renderBoard();
      renderGovLinkedAds(gov, area, metric);
      const rows = filteredBoardRows().filter((row) => {
        const rowGov = boardLocationBucket(row);
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
  if (name === "account") {
    openAccountModal();
    return;
  }
  const visiblePanels = name === "market" ? new Set(["board", "insights"]) : new Set([name]);
  document.querySelectorAll(".main-tab").forEach((btn) => {
    const isActive = btn.dataset.mainTab === name;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    btn.setAttribute("tabindex", isActive ? "0" : "-1");
  });
  document.querySelectorAll("[data-main-panel]").forEach((panel) => {
    panel.classList.toggle("active", visiblePanels.has(panel.dataset.mainPanel));
  });
  if (name === "opportunities") loadOpportunities(false);
  if (name === "market" || name === "board") loadDashboardBoard();
  if (name === "market" || name === "insights") loadInsights();
  if (name === "developments") loadDevelopments();
  if (name === "why-free") loadPlatformIntelligence();
}

// زر «اسأل المساعد» العائم: يفتح صندوق المحادثة العائم
let _assistantBound = false;
function _bindAssistant() {
  if (_assistantBound) return;
  _assistantBound = true;
  const chatFab = document.getElementById("chatFab");
  const assistantOverlay = document.getElementById("assistantOverlay");
  const assistantForm = document.getElementById("assistantForm");
  const assistantInput = document.getElementById("assistantInput");
  const assistantMessages = document.getElementById("assistantMessages");
  const assistantCloseBtn = document.getElementById("assistantCloseBtn");
  if (!assistantOverlay) return;
  window._openAssistant = function() {
    assistantOverlay.hidden = false;
    document.body.style.overflow = "hidden";
    setTimeout(() => assistantInput && assistantInput.focus(), 200);
  };
  window._closeAssistant = function() {
    assistantOverlay.hidden = true;
    document.body.style.overflow = "";
  };
  if (chatFab) chatFab.addEventListener("click", window._openAssistant);
  if (assistantCloseBtn) assistantCloseBtn.addEventListener("click", window._closeAssistant);
  assistantOverlay.addEventListener("click", (e) => {
    if (e.target === assistantOverlay) window._closeAssistant();
  });
  // assistant form submit
  if (assistantForm) {
    assistantForm.addEventListener("submit", (e) => {
      e.preventDefault();
      _submitAssistant();
    });
  }
  if (assistantInput) {
    assistantInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); _submitAssistant(); }
    });
  }
  function _appendMsg(text, isUser) {
    const div = document.createElement("div");
    div.className = "assistant-msg " + (isUser ? "assistant-msg-user" : "assistant-msg-bot");
    div.innerHTML = `<div class="assistant-msg-avatar">${isUser ? "\uD83D\uDC64" : "\uD83C\uDFE0"}</div><div class="assistant-msg-body">${escapeHtml(text)}</div>`;
    assistantMessages.appendChild(div);
    assistantMessages.scrollTop = assistantMessages.scrollHeight;
  }
  async function _submitAssistant() {
    const queryText = (assistantInput ? assistantInput.value.trim() : "");
    if (!queryText) return;
    assistantInput.value = "";
    _appendMsg(queryText, true);
    // ── مؤشر التحميل مع تحديث دوري ──
    const loadDiv = document.createElement("div");
    loadDiv.className = "assistant-msg assistant-msg-bot assistant-msg-loading";
    loadDiv.innerHTML = `<div class="assistant-msg-avatar">\uD83C\uDFE0</div><div class="assistant-msg-body"><span class="lp-spinner" aria-hidden="true"></span> جاري البحث في قاعدة الفريج...</div>`;
    assistantMessages.appendChild(loadDiv);
    assistantMessages.scrollTop = assistantMessages.scrollHeight;
    const startTime = Date.now();
    const loadInterval = setInterval(() => {
      const elapsed = Math.round((Date.now() - startTime) / 1000);
      if (loadDiv.isConnected) {
        const bodyEl = loadDiv.querySelector(".assistant-msg-body");
        if (bodyEl) bodyEl.innerHTML = `<span class="lp-spinner" aria-hidden="true"></span> جاري البحث... (${elapsed} ثانية)`;
        assistantMessages.scrollTop = assistantMessages.scrollHeight;
      }
    }, 3000);
    // ── إرسال الطلب مع مهلة 60 ثانية ──
    const ctrl = new AbortController();
    const timeoutId = setTimeout(() => ctrl.abort(), 60000);
    try {
      const userSecret = localStorage.getItem("alforaij_secret") || "";
      const headers = { "Content-Type": "application/json" };
      if (userSecret) headers["Authorization"] = "Bearer " + userSecret;
      const jobId = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: headers,
        signal: ctrl.signal,
        body: JSON.stringify({
          text: queryText,
          sourceMode: "local",
          jobId: jobId,
          fast: true,
          user_secret: userSecret || "",
        }),
      });
      const data = await res.json();
      clearInterval(loadInterval);
      clearTimeout(timeoutId);
      loadDiv.remove();
      if (data.error && !data.summary && (!data.results || !data.results.length)) {
        // عرض رسالة خطأ واضحة بدل الكود التقني
        const errMsg = data.message || data.error || "تعذر الحصول على النتائج. حاول مرة أخرى.";
        _appendMsg(errMsg, false);
      } else {
        // بناء عرض النتائج بشكل منسق من ملخص التقرير + النتائج
        let summary = data.summary || data.answer || "";
        if (typeof summary === "object") summary = JSON.stringify(summary, null, 2).slice(0, 1200);
        // إضافة عدد النتائج إن وُجد
        const resultCount = (data.results && data.results.length) || 0;
        const countNote = resultCount > 0 ? `\n\n📊 عدد النتائج: ${resultCount} نتيجة` : "";
        _appendMsg(summary + countNote, false);
      }
    } catch (err) {
      clearInterval(loadInterval);
      clearTimeout(timeoutId);
      loadDiv.remove();
      if (err.name === "AbortError") {
        _appendMsg("⏰ انتهت المهلة (60 ثانية). حاول البحث في نطاق أضيق مثل: بيت 400م في الفردوس", false);
      } else {
        _appendMsg("خطأ في الاتصال بالخادم. تأكد من تشغيل السيرفر والاتصال بالإنترنت.", false);
      }
    }
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _bindAssistant);
} else {
  _bindAssistant();
}

// أزرار «لماذا مجاني وأدق» — قفزة مباشرة إلى البحث أو الفرص
const whyfreeCtas = document.querySelectorAll(".whyfree-cta");
whyfreeCtas.forEach((btn) => {
  btn.addEventListener("click", () => {
    switchMainTab(btn.dataset.go || "search");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});

// مشاركة صفحة «لماذا مجاني وأدق»: يفتح محرر واتساب برسالة مقارنة موجزة (بدون رقم)
// + تتبع النقرة في outreach_clicks (نفس نمط تتبع نسخ/إرسال الفرص).
function shareWhyFreePage() {
  const lines = [
    "منصة الفريج — «لماذا مجاني وأدق؟»",
    "",
    "كل ما تدفع عليه في المنصات الأخرى، عندنا مجاني وأدق:",
    "• ترتيب الظهور: 4Sale تثبيت/تمييز برصيد مدفوع (3 د.ك/شهر) — عندنا بدرجة الفرصة الموضوعية",
    "• الإدراج المميز: PropertyFinder رسم إداري 1,000 درهم + رسم شهري — عندنا التقييم الموثق مجانًا",
    "• تقرير التقييم: البنوك معاينة ميدانية وأيام — عندنا فوري بمصادره وأدلته",
    "• إغلاق الصفقة في دبي: عمولة وسيط 2% + رسوم DLD 4% — عندنا سجل السوق مفتوح بلا رسوم",
    "",
    "الترتيب بالمصلحة لا بالدفع — وكل رقم بمصدره:",
    window.location.href.split("#")[0],
  ];
  const url = waShareLink(lines.join("\n"));
  try {
    window.open(url, "_blank", "noopener,noreferrer");
  } catch {
    window.location.href = url;
  }
  trackOutreach({ action: "send", channel: "why_free_page" });
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
    // عرض المصادر بشكل مختصر فقط (بدون التفاصيل التقنية)
    const sources = data.sources || [];
    const okCount = sources.filter(s => s.status === 'success').length;
    if (sources.length) {
      sourcesEl.innerHTML = `<p class="source-summary-bar tone-ok">وكيل الاكتشاف: جمع ${items.length} خبرًا من ${okCount}/${sources.length} مصدر نشط</p>`;
    } else {
      sourcesEl.innerHTML = '';
    }
  }

  const countEl = $("tabCountDevelopments");
  if (countEl) countEl.textContent = items.length ? String(items.length) : "";
}

function bindMainTabs() {
  document.querySelectorAll(".main-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchMainTab(btn.dataset.mainTab));
  });
  document.querySelectorAll("[data-more-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wrap = btn.closest("details");
      if (wrap) wrap.open = false;
      switchMainTab(btn.dataset.moreTab);
    });
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

// ─── حاسبة الرهن العقاري — مقارنة بنوك الكويت ───
function initMortgageCalculator() {
  const btn = $("mortgageCalcBtn");
  if (!btn) return;
  btn.addEventListener("click", runMortgageComparison);
}

async function runMortgageComparison() {
  const price = Number($("mortgagePrice")?.value || 0);
  const downPct = Number($("mortgageDownPct")?.value || 30);
  const years = Number($("mortgageYears")?.value || 20);
  const salary = Number($("mortgageSalary")?.value || 0) || null;

  if (price <= 0) {
    alert("أدخل قيمة العقار أولاً");
    return;
  }

  const btn = $("mortgageCalcBtn");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/api/invest/compare-banks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        price: price,
        down_payment_pct: downPct,
        years: years,
        salary: salary,
      }),
    });
    const data = await res.json();
    if (data.error) {
      alert(data.error);
      return;
    }
    renderMortgageResults(data);
  } catch (e) {
    console.error("Mortgage comparison error:", e);
    alert("خطأ في الاتصال — أعد المحاولة");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderMortgageResults(data) {
  const container = $("mortgageResults");
  const summaryEl = $("mortgageSummary");
  const banksEl = $("mortgageBanks");
  if (!container || !summaryEl || !banksEl) return;

  container.hidden = false;

  // ملخص
  const rec = data.recommendation || {};
  summaryEl.innerHTML = `
    <div>💰 <strong>${formatMoney(data.property_value)}</strong> د.ك — الدفعة المقدمة: <strong>${formatMoney(data.down_payment_amount)}</strong> (${data.down_payment_pct}%)</div>
    <div>🏦 مبلغ القرض: <strong>${formatMoney(data.loan_amount)}</strong> د.ك — المدة: <strong>${data.requested_years}</strong> سنة</div>
    ${rec.summary ? `<div style="margin-top:6px;color:#16a34a">🎯 ${rec.summary}</div>` : ""}
  `;

  // بطاقات البنوك
  banksEl.innerHTML = (data.banks || []).map(bank => {
    const isBest = bank.code === data.best_bank;
    const ratioClass = bank.salary_ratio == null ? "" : bank.salary_ratio <= 30 ? "ok" : bank.salary_ratio <= 40 ? "warn" : "danger";
    const featuresHtml = (bank.features || []).map(f => '<li>' + f + '</li>').join("");
    const urlHtml = bank.url ? '<a href="' + bank.url + '" target="_blank" rel="noreferrer" style="font-size:11px;color:var(--blue);margin-top:6px;display:inline-block">الرابط الرسمي ↗</a>' : "";
    const ratioHtml = bank.salary_ratio != null ? '<div class="bank-salary-ratio ' + ratioClass + '">نسبة القسط من الراتب: ' + bank.salary_ratio + '%</div>' : "";
    return '<div class="mortgage-bank-card' + (isBest ? ' best' : '') + '">' +
      '<div class="bank-name">' + bank.name + ' <span class="bank-name-en">' + bank.name_en + '</span></div>' +
      '<span class="bank-rate">' + bank.rate + '%</span>' +
      '<div class="bank-monthly">' + formatMoney(bank.monthly_payment) + ' <small>د.ك/شهر</small></div>' +
      '<div class="bank-details">' +
        '<div>إجمالي الفائدة: <strong>' + formatMoney(bank.total_interest) + '</strong> د.ك</div>' +
        '<div>الإجمالي المدفوع: <strong>' + formatMoney(bank.total_paid) + '</strong> د.ك</div>' +
        '<div>المدة: <strong>' + bank.years + '</strong> سنة</div>' +
        ratioHtml +
      '</div>' +
      '<ul class="bank-features">' + featuresHtml + '</ul>' +
      urlHtml +
    '</div>';
  }).join("");
}

// ─── حاسبة التأمين العقاري ───
function initInsuranceCalculator() {
  const btn = $("insuranceCalcBtn");
  if (!btn) return;
  btn.addEventListener("click", runInsuranceComparison);
}

async function runInsuranceComparison() {
  const price = Number($("insurancePrice")?.value || 0);
  const contents = Number($("insuranceContents")?.value || 0);
  const age = Number($("insuranceAge")?.value || 0);
  const years = Number($("insuranceYears")?.value || 1);

  if (price <= 0) {
    alert("أدخل قيمة العقار أولاً");
    return;
  }

  const btn = $("insuranceCalcBtn");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/api/invest/insurance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        price: price,
        contents_value: contents,
        building_age: age,
        years: years,
      }),
    });
    const data = await res.json();
    if (data.error) {
      alert(data.error);
      return;
    }
    renderInsuranceResults(data);
  } catch (e) {
    console.error("Insurance comparison error:", e);
    alert("خطأ في الاتصال — أعد المحاولة");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderInsuranceResults(data) {
  const container = $("insuranceResults");
  const summaryEl = $("insuranceSummary");
  const optionsEl = $("insuranceOptions");
  if (!container || !summaryEl || !optionsEl) return;

  container.hidden = false;

  // ملخص
  const rec = data.recommendation || {};
  summaryEl.innerHTML = '<div>🛡️ مقارنة خيارات التأمين لعقار <strong>' + formatMoney(data.property_value) + '</strong> د.ك</div>' +
    (rec.summary ? '<div style="margin-top:6px">🎯 ' + rec.summary + '</div>' : '');

  // بطاقات الخيارات
  const bestType = data.best_option?.insurance_type;
  optionsEl.innerHTML = (data.options || []).map(opt => {
    const isBest = opt.insurance_type === bestType;
    const featuresHtml = (opt.features || []).map(f => '<li>' + f + '</li>').join("");
    const discountsHtml = (opt.discounts || []).map(d => d.name + ': -' + (d.percent * 100).toFixed(0) + '%').join(', ');
    return '<div class="insurance-option-card' + (isBest ? ' best' : '') + '">' +
      '<div class="ins-type">' + opt.type_name + ' <span style="font-weight:400;font-size:11px;color:var(--muted)">' + opt.type_name_en + '</span></div>' +
      '<div class="ins-desc">' + opt.description + '</div>' +
      '<div class="ins-annual">' + formatMoney(opt.total_annual) + ' <small>د.ك/سنة</small></div>' +
      '<div class="ins-details">' +
        '<div>النسبة: <strong>' + opt.final_rate.toFixed(2) + '%</strong></div>' +
        '<div>الشهري: <strong>' + formatMoney(opt.monthly_cost) + '</strong> د.ك</div>' +
        '<div>الإجمالي: <strong>' + formatMoney(opt.total_cost) + '</strong> د.ك</div>' +
        (opt.total_discount > 0 ? '<div>الخصم: <strong style="color:#10b981">-' + opt.total_discount + '%</strong></div>' : '') +
        (discountsHtml ? '<div style="font-size:10px">(' + discountsHtml + ')</div>' : '') +
      '</div>' +
      '<ul class="ins-features">' + featuresHtml + '</ul>' +
    '</div>';
  }).join("");
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


// ── سجل تعريفات المقاييس: توثيق كل رقم يظهر في المنصة (صيغة + مصدر + معتمد) ──
// مرجع داخلي موحد — أي تعديل في منطق الحساب يجب أن يحدّث هذا السجل في نفس التعديل.
const METRIC_REGISTRY = [
  {
    id: "governance",
    title: "قواعد الحوكمة — تتحكم في كل الأرقام",
    note: "قواعد معتمدة من فريق بيانات الفريج — أي رقم في المنصة يُحسب في إطارها.",
    rows: [
      {
        name: "المساحة الصريحة فقط",
        what: "لا يُعدّ «ارتداد» ولا «عرض الشارع» ولا «الواجهة» مساحة. المساحة تدخل أي حساب فقط كمذكورة صريحة: حقل مساحة أو نص مثل «المساحة: 300م²». مثال: إعلان AF-303 به «ارتداد 40 متر» فمساحته غير محددة.",
        formula: "قاعدة تصنيف لا حساب — إن لم تُذكر المساحة صراحةً تظهر «غير محددة»",
        source: "القواعد المعتمدة من فريق بيانات الفريج",
        status: "approved",
      },
      {
        name: "ميزانيات الطلب خارج أسعار العرض",
        what: "طلبات «مطلوب للشراء/للإيجار» تُعدّ في مؤشرات الطلب فقط ولا تدخل وسيطات أسعار العرض حتى لا تشوّه سعر السوق (ميزانية المشتري ليست سعر عرض).",
        formula: "—",
        source: "منطق تحليلات السوق — تصنيف معاملات الطلب",
        status: "approved",
      },
      {
        name: "استبعاد القيم الشاذة قبل الوسيط",
        what: "أي وسيط (سعر / إيجار / سعر المتر) يُحسب بعد استبعاد الشواذ بمعيار 3×IQR عندما تكون العينات ≥4 — الأسعار المهرطبة لا تشوّه الوسيط.",
        formula: "الحدود = Q1 − 3×IQR و Q3 + 3×IQR — تُطبَّق فقط عند 4 عينات فأكثر",
        source: "منطق تحليلات السوق — تنظيف القيم الشاذة",
        status: "approved",
      },
      {
        name: "شروط حساب العائد الإيجاري",
        what: "يُحسب فقط عند عينتين على الأقل بيعًا وإيجارًا بعد التنظيف، وسعر البيع أكبر من الإيجار السنوي، والناتج ≤ 15% (أعلى من ذلك غالبًا خطأ بيانات لا فرصة حقيقية).",
        formula: "(وسيط الإيجار × 12) ÷ وسيط سعر البيع × 100",
        source: "قواعد حساب العائد الإيجاري — سقف 15% + حد أدنى عينتين",
        status: "approved",
      },
      {
        name: "خط البيع منفصل عن خط الإيجار",
        what: "لا يُخلط سعر البيع مع الإيجار الشهري: خط البيع (سعر إجمالي، سعر المتر، وسيط، نسبة السعر) وخط الإيجار (شهري/سنوي، إيجار المتر، وسيط الإيجارات، العائد) كلٌّ بحساباته. العائد يُقاس لعروض البيع المؤجرة ولا يُطبَّق على عروض الإيجار.",
        formula: "—",
        source: "منطق التقييم — خط البيع مقابل خط الإيجار",
        status: "approved",
      },
      {
        name: "التصنيف القانوني/التمويلي من نص الإعلان فقط",
        what: "تصنيف الملكية والاستخدام والحالة القانونية مستخرج من نص الإعلان فقط، ولا يتحول إلى حقيقة رسمية إلا بوجود وثيقة أو مصدر رسمي موثق داخل التقرير.",
        formula: "—",
        source: "ملف العقار — مستخرج من نص الإعلان",
        status: "approved",
      },
    ],
  },
  {
    id: "board",
    title: "مقاييس لوحة السوق",
    note: "الأرقام في تبويب «لوحة السوق» — عدّ مباشر على الإعلانات حسب الفلاتر الحالية.",
    rows: [
      {
        name: "حركة الدلال",
        what: "كل الإعلانات الظاهرة ضمن الاختيار الحالي — المحور الافتراضي للوحة والمحافظات.",
        formula: "عدّ الصفوف المطابقة للفلاتر",
        source: "بيانات الفريج + الحصاد الخارجي",
        status: "auto",
      },
      {
        name: "فرص محسوبة",
        what: "الإعلانات التي حصلت على درجة فرصة أكبر من صفر (دخلت التقييم بفرصة فعلية).",
        formula: "العد حيث درجة الفرصة أكبر من صفر",
        source: "محرك تقييم الفرص",
        status: "auto",
      },
      {
        name: "عروض للبيع",
        what: "إعلانات بيع فعلية (بدون طلبات شراء).",
        formula: "المعاملة تحوي «بيع» ولا تحوي «مطلوب»",
        source: "من معاملة الإعلان (بيع/شراء/إيجار)",
        status: "auto",
      },
      {
        name: "طلبات شراء",
        what: "إعلانات «مطلوب للشراء» من الفريج أو قسم «مطلوب» في المواقع الخارجية — كل طلب عميل محتمل.",
        formula: "المعاملة تحوي «مطلوب» و«شراء»",
        source: "من معاملة الإعلان (بيع/شراء/إيجار)",
        status: "auto",
      },
      {
        name: "عروض الإيجار",
        what: "إعلانات إيجار فعلية (بدون طلبات إيجار).",
        formula: "المعاملة تحوي «إيجار/أجار» ولا تحوي «مطلوب»",
        source: "من معاملة الإعلان (بيع/شراء/إيجار)",
        status: "auto",
      },
      {
        name: "طلبات الإيجار",
        what: "إعلانات «مطلوب للإيجار».",
        formula: "المعاملة تحوي «مطلوب» و«إيجار/أجار»",
        source: "من معاملة الإعلان (بيع/شراء/إيجار)",
        status: "auto",
      },
      {
        name: "فرص ظاهرة / دخلت التقييم",
        what: "«فرص ظاهرة»: الفرص المقيّمة ضمن الاختيار. «دخلت التقييم»: إجمالي الإعلانات المقيّمة حتى بلا فرصة.",
        formula: "فرص ظاهرة: الفرص بدرجة > 0 · دخلت التقييم: كل الصفوف بدرجة محسوبة",
        source: "محرك التقييم اليومي",
        status: "auto",
      },
      {
        name: "أدلة ومقارنات",
        what: "مجموع الإعلانات التي تحمل أدلة أو مقارنات سعرية — يعكس عمق توثيق كل رقم.",
        formula: "مجموع عدد الأدلة + عدد المقارنات",
        source: "محرك التقييم — سجل الأدلة",
        status: "auto",
      },
      {
        name: "أسعار معلنة",
        what: "الإعلانات التي يحمل صفها سعرًا صريحًا أكبر من صفر.",
        formula: "العد حيث السعر المعلن أكبر من صفر",
        source: "من سعر الإعلان المعلن",
        status: "auto",
      },
      {
        name: "مساحات موثقة",
        what: "الإعلانات التي تحمل مساحة صريحة أكبر من صفر — بعد تطبيق قاعدة المساحة الصريحة فقط.",
        formula: "العد حيث المساحة الصريحة أكبر من صفر",
        source: "من مساحة الإعلان بعد تطبيق قاعدة الحوكمة",
        status: "auto",
      },
      {
        name: "مباشر / مكتب",
        what: "تقسيم الإعلانات حسب نمط الإدراج: مباشر (المالك) أو مكتب (وساطة).",
        formula: "العد حسب نمط الإعلان (مباشر/مكتب)",
        source: "من نمط الإعلان (مباشر/مكتب)",
        status: "auto",
      },
    ],
  },
  {
    id: "market",
    title: "مقاييس تحليلات السوق",
    note: "الأرقام في تبويب «تحليلات السوق» — من الحصاد المتراكم للمنصات.",
    rows: [
      {
        name: "وسيط سعر المتر (منطقة)",
        what: "سعر المتر النموذجي لإعلانات البيع في المنطقة — أساس مقارنة أي عرض في التقييم.",
        formula: "وسيط (السعر ÷ المساحة الصريحة) لإعلانات البيع بعد استبعاد الشواذ",
        source: "الحصاد المتراكم من منصات السوق",
        status: "auto",
      },
      {
        name: "وسيط سعر المتر (محافظة)",
        what: "وسيط وسيطات مناطق المحافظة — يُعرض كأشرطة في التحليلات وكمرجع للخريطة الحرارية.",
        formula: "وسيط (وسيطات مناطق المحافظة)",
        source: "مشتق من وسيطات المناطق",
        status: "auto",
      },
      {
        name: "العائد الإيجاري السنوي",
        what: "العائد السنوي المتوقع لشراء عقار في المنطقة ثم تأجيره — يظهر فقط عند استيفاء شروط الحوكمة.",
        formula: "(وسيط الإيجار × 12) ÷ وسيط سعر البيع × 100 — بحد أدنى عينتين لكل جانب وسقف 15%",
        source: "منطق تحليلات السوق",
        status: "auto",
      },
      {
        name: "ثقة العائد",
        what: "الشارة بجانب العائد: «ثقة عالية» عند وفرة العينات و«تقديري» عند قلتها.",
        formula: "ثقة عالية: عينات بيع ≥ 5 وعينات إيجار ≥ 5 (بعد التنظيف) — وإلا تقديري",
        source: "منطق تحليلات السوق — شارة موثوقية العائد",
        status: "auto",
      },
      {
        name: "اتجاه السوق",
        what: "اتجاه وسيط سعر المتر العام بين أول وآخر شهر حصاد — بطاقة KPI في التحليلات.",
        formula: "(آخر شهر − أول شهر) ÷ أول شهر × 100 — صاعد ≥ +3% · هابط ≤ −3% · وإلا مستقر",
        source: "سلسلة وسيط السوق العام الشهرية",
        status: "auto",
      },
      {
        name: "وسيط السوق العام",
        what: "الخط المتقطع في رسم الاتجاه — الوسيط العام لسعر المتر عبر كل أشهر الحصاد.",
        formula: "وسيط (السعر ÷ المساحة) لكل صفوف البيع في كل الأشهر",
        source: "سلسلة وسيط السوق العام الشهرية",
        status: "auto",
      },
      {
        name: "مؤشرات الطلب",
        what: "عدّ طلبات الشراء والإيجار حسب المنطقة والمحافظة والمنصة مع الاتجاه الشهري — ميزانيات الطلب لا تدخل وسيطات العرض.",
        formula: "عدّ معاملات «مطلوب للشراء/للإيجار»",
        source: "الفريج المحلي + قسم «مطلوب» في 4Sale",
        status: "auto",
      },
    ],
  },
  {
    id: "valuation",
    title: "مقاييس التقييم والترتيب",
    note: "الأرقام في «النتائج المرتبة» و«أفضل الفرص» — تُحسب لكل نتيجة أو فرصة.",
    rows: [
      {
        name: "درجة التوصية (0–100)",
        what: "الترتيب النهائي في «النتائج المرتبة» — أعلى درجة أولًا.",
        formula: "مطابقة الطلب ×62% + جاذبية السعر ×28% + الثقة ×10% − (3 نقاط لكل تحذير، حد أقصى 12)",
        source: "منطق التقييم — درجة التوصية",
        status: "approved",
      },
      {
        name: "جاذبية السعر",
        what: "عدالة السعر مقابل وسيط المقارنات (أو القيمة الرسمية عند توفرها) — نفس الحدود لخط الإيجار على الإيجار الشهري.",
        formula: "نسبة السعر ≤0.82 → 100 ممتاز · ≤0.92 → 88 أقل من السوق · ≤1.08 → 74 عادل · ≤1.18 → 58 أعلى قليلًا · ≤1.35 → 38 غالي · >1.35 → 20 مبالغ فيه",
        source: "منطق التقييم — جاذبية السعر",
        status: "approved",
      },
      {
        name: "نسبة السعر",
        what: "مقارنة السعر المطلوب بسوق المنطقة — تظهر في بطاقة النتيجة (مثل 1.05 مقابل الوسيط).",
        formula: "السعر المطلوب ÷ وسيط المقارنات (أو القيمة الرسمية عند توفرها)",
        source: "منطق التقييم — نسبة السعر",
        status: "auto",
      },
      {
        name: "الثقة (%)",
        what: "مدى اعتماد التقييم على بيانات فعلية — كلما زادت المقارنات أو توفرت مراجع رسمية ارتفعت.",
        formula: "50% أساس + 6% لكل مقارنة سعرية (حد أقصى 90%) — 85% مع مؤشر رسمي · 90% مع صفقات رسمية مسجلة",
        source: "منطق التقييم — جاذبية السعر",
        status: "approved",
      },
      {
        name: "سعر المتر",
        what: "سعر المتر للمطلوب نفسه للمقارنة مع وسيط المنطقة — يُحسب فقط عند مساحة صريحة.",
        formula: "السعر ÷ المساحة (الصريحة فقط)",
        source: "منطق التقييم — سعر المتر",
        status: "auto",
      },
      {
        name: "العائد الإيجاري (بيع مؤجر)",
        what: "حكم استثماري للعروض المؤجرة: قوي ≥6% · متوسط ≥4% · ضعيف — لا يُطبَّق على عروض الإيجار.",
        formula: "(الدخل السنوي ÷ سعر البيع) × 100 — الدخل من الطلب أولًا ثم الإعلان",
        source: "منطق التقييم — العائد للبيع المؤجر",
        status: "approved",
      },
      {
        name: "درجة الفرصة (0–100)",
        what: "ترتيب الفرص في «أفضل الفرص» وشارة درجة الفرصة في اللوحة — بدون أي عنصر عشوائي.",
        formula: "جاذبية السعر ×65% + الثقة ×35%",
        source: "منطق تقييم الفرص — الدرجة",
        status: "approved",
      },
      {
        name: "ثقة الفرصة",
        what: "ثقة مركبة لكل فرصة تجمع مصداقية المصدر وقوة التقييم والأدلة.",
        formula: "مصداقية المصدر ×50% + ثقة التقييم ×30% + قوة الأدلة ×20%",
        source: "منطق تقييم الفرص — الثقة",
        status: "approved",
      },
      {
        name: "نطاق المقارنة",
        what: "داخل أي نطاق تتم المقارنات السعرية — يظهر في سبب التقييم وشفافية كل رقم.",
        formula: "نفس المنطقة (≥3 مقارنات) → ثم توسعة محدودة → بدونه «لا توجد مقارنات كافية»",
        source: "منطق التقييم — نطاق المقارنات",
        status: "auto",
      },
    ],
  },
  {
    id: "sources",
    title: "مصادر الأرقام ومستويات الاعتماد",
    note: "أي مصدر يدخل التقييم وكيف يظهر في التقرير — سياسة الاعتماد من القواعد المعتمدة.",
    rows: [
      {
        name: "الفريج",
        what: "المصدر المحلي الأساسي — بيانات الشركة من لوحة الفريج الداخلية.",
        formula: "دخل التقييم",
        source: "بيانات الفريج — السجلات المحلية",
        status: "approved",
      },
      {
        name: "الصفقات الرسمية",
        what: "أعلى مصداقية — تدخل التقييم فقط عند توفر صفقات موثقة بمنطقة ونوع عقار وتاريخ ومساحة وسعر.",
        formula: "دخل التقييم (مشروط بالبيانات المنظمة)",
        source: "وزارة العدل / التسجيل العقاري عبر القاعدة",
        status: "approved",
      },
      {
        name: "المؤشرات الرسمية",
        what: "مرجع أعلى عند توفر بيانات منظمة لسعر المتر في القاعدة أو الملفات المحلية.",
        formula: "دخل التقييم (مشروط بالبيانات المنظمة)",
        source: "PACI / Kuwait Finder / تقارير سوقية موثقة",
        status: "approved",
      },
      {
        name: "OpenSooq · Mourjan · 4Sale",
        what: "تدخل المقارنات فقط عند نفس المنطقة ونفس نوع العقار ونفس العملية وبسعر قابل للقراءة — 4Sale يعيد المحاولة حتى 4 مرات ثم يلجأ لمصدر بديل مع إفصاح.",
        formula: "دخل التقييم (عبر الجلب الحي أو البديل الموثق)",
        source: "سياسة الحصاد الحي للمنصات",
        status: "auto",
      },
      {
        name: "Q8Aqar",
        what: "يدخل فقط عندما يثبت رابط/نص الإعلان نفس الطلب — وإلا يظهر كمصدر مفحوص لا كمقارنة سعرية.",
        formula: "دخل مشروط (بعد إثبات التطابق)",
        source: "سياسة الحصاد الحي للمنصات",
        status: "auto",
      },
      {
        name: "Sakan",
        what: "دليل توفر ورابط صفحة فقط حاليًا — لا يدخل التقييم حتى تتوفر واجهة بيانات تفاصيل قابلة للتحقق.",
        formula: "مساعد فقط (لا يدخل التقييم)",
        source: "سياسة الحصاد الحي للمنصات",
        status: "auto",
      },
      {
        name: "Waseet · NabdAqar · Bu3qar · Aqarat",
        what: "حسب توفّر صفحاتها العامة أو بدائل البحث — تظهر كمساعد أو مشروط حتى تعيد بيانات منظمة.",
        formula: "مساعد / مشروط حسب توفر البيانات",
        source: "سياسة الحصاد الحي للمنصات",
        status: "auto",
      },
      {
        name: "مستويات الاعتماد في التقرير",
        what: "كل مصدر يظهر في التقرير بأحد هذه المستويات — تُقرأ كما هي دون مبالغة.",
        formula: "دخل التقييم · دخل عبر بديل · مساعد فقط · لا يدخل التقييم · فشل الاتصال",
        source: "سياسة الاعتماد المعتمدة من فريق البيانات",
        status: "approved",
      },
    ],
  },
];

function registryRowHtml(row) {
  const isApproved = row.status === "approved";
  return `
    <div class="registry-row ${isApproved ? "connected" : "live_conditional"}">
      <strong>${escapeHtml(row.name)}</strong>
      <p>${escapeHtml(row.what)}</p>
      <p class="registry-formula"><em>${row.formula && row.formula !== "—" ? escapeHtml(row.formula) : "—"}</em></p>
      <div class="registry-src">
        <span>${escapeHtml(row.source)}</span>
        <em class="registry-status ${isApproved ? "approved" : "auto"}">${escapeHtml(row.statusText || (isApproved ? "معتمد — فريق البيانات" : "محسوب تلقائيًا"))}</em>
      </div>
    </div>`;
}

// بيانات السجل: تبدأ من النسخة الثابتة كاحتياط، ويُستبدَل بها رد الخادم الحي عند توفره
// (/api/metric-registry) — الصيغ الرقمية في الرد مبنية من ثوابت المحرك الفعلية.
let metricsRegistryLive = null;   // { generatedAt, source, sections }
let metricsRegistryLiveAt = "";  // نص آخر مزامنة حية مع الخادم

function renderMetricsRegistry(query = "") {
  const root = $("metricsRoot");
  if (!root) return;
  const q = String(query || "").trim().toLowerCase();
  const source = metricsRegistryLive && Array.isArray(metricsRegistryLive.sections) ? metricsRegistryLive.sections : METRIC_REGISTRY;
  let total = 0;
  let matched = 0;
  const sections = source.map((section) => {
    const rows = (section.rows || []).filter((row) => {
      if (!q) return true;
      return [row.name, row.what, row.formula, row.source].join(" ").toLowerCase().includes(q);
    });
    total += (section.rows || []).length;
    matched += rows.length;
    if (!rows.length) return "";
    return `
      <section class="metrics-section">
        <div class="section-title compact-title">
          <div>
            <h3>${escapeHtml(section.title)} <span class="metrics-section-count">${rows.length}</span></h3>
            <span>${escapeHtml(section.note)}</span>
          </div>
        </div>
        <div class="registry-table">
          ${rows.map((row) => registryRowHtml(row)).join("")}
        </div>
      </section>`;
  }).join("");
  const meta = $("metricsMeta");
  if (meta) {
    meta.textContent = q ? `${matched} من ${total} مقياس مطابق للبحث` : `${total} مقياسًا موثقًا${metricsRegistryLive ? " · مصدر حي من الخادم" : ""}`;
    if (metricsRegistryLive && metricsRegistryLiveAt) {
      meta.title = `آخر مزامنة مع الخادم: ${metricsRegistryLiveAt} — الصيغ مبنية من ثوابت المحرك الفعلية`;
    }
  }
  const countEl = $("tabCountMetrics");
  if (countEl) countEl.textContent = q ? "" : String(total);
  root.innerHTML = sections || '<div class="empty">لا توجد مقاييس مطابقة للبحث — جرّب كلمة أخرى.</div>';
}

async function initMetricsRegistry() {
  const input = $("metricsFilter");
  // عرض فوري من النسخة الثابتة ثم استبدالها بالمصدر الحي من الخادم عند توفره
  renderMetricsRegistry(input ? input.value : "");
  try {
    const payload = await getJson("/api/metric-registry");
    if (payload && Array.isArray(payload.sections)) {
      metricsRegistryLive = payload;
      metricsRegistryLiveAt = String(payload.generatedAt || "").replace("T", " ").slice(0, 16);
      renderMetricsRegistry(input ? input.value : "");
    }
  } catch {
    // الخادم غير متاح (وضع ثابت/لقطة) — تبقى النسخة الثابتة كما هي بلا خطأ ظاهر
  }
  if (input) {
    input.addEventListener("input", () => renderMetricsRegistry(input.value));
  }
}

// ── اسأل السوق: شات سريع فوق بيانات تحليلات السوق المتراكمة ──────────────────
// يجيب مباشرة من /api/market-insights + /api/market-demand (المحمَّلة في insightsState)
// بدون تشغيل بحث كامل — أسئلة مثل «متوسط سعر المتر في الجهراء».
const MARKET_GOVERNORATES = ["العاصمة", "حولي", "الجهراء", "الفروانية", "الأحمدي", "مبارك الكبير"];
const MARKET_CHAT_SUGGESTIONS = [
  "متوسط سعر المتر في الجهراء",
  "أعلى منطقة عائد إيجار",
  "أرخص منطقة سعر متر",
  "كم طلب شراء في الأحمدي",
  "اتجاه سعر المتر العام",
  "قارن بين العاصمة وحولي",
];

function marketChatNorm(value) {
  // توحيد اسم المحافظة/المنطقة مع إزالة بادئة «محافظة» قبل التطبيع حتى تتطابق المقارنات
  return normalizeArabic(String(value || "").replace(/^محافظة\s*/i, ""));
}

function marketChatMedian(values) {
  const list = (values || []).filter((v) => v != null && isFinite(Number(v))).map(Number).sort((a, b) => a - b);
  if (!list.length) return null;
  const mid = Math.floor(list.length / 2);
  return list.length % 2 ? list[mid] : (list[mid - 1] + list[mid]) / 2;
}

function marketChatNum(value, digits = 0) {
  if (value == null || !isFinite(Number(value))) return "—";
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: digits });
}

function marketChatScopes(q) {
  const data = insightsState.data || {};
  const areas = data.areas || [];
  // ذكر «محافظة» صراحةً يوجّه السؤال لمستوى المحافظة لا لمنطقة بنفس الاسم
  const explicitGov = q.includes("محافظه");
  // المحافظة المذكورة في السؤال (أطول اسم مطابق — لتفادي «الكبير» داخل «مبارك الكبير»)
  const govs = MARKET_GOVERNORATES
    .map((g) => ({ name: g, norm: marketChatNorm(g) }))
    .filter((g) => g.norm && q.includes(g.norm))
    .sort((a, b) => b.norm.length - a.norm.length);
  const governorates = govs.map((g) => g.name);
  // المنطقة المذكورة (أطول اسم مطابق في البيانات) — تُتجاهل مع ذكر «محافظة» صراحةً
  const areaMatch = areas
    .map((a) => ({ area: a, norm: marketChatNorm(a.area) }))
    .filter((m) => m.norm && q.includes(m.norm))
    .sort((a, b) => b.norm.length - a.norm.length)[0];
  const area = explicitGov ? null : (areaMatch ? areaMatch.area : null);
  return { governorates, area, explicitGov };
}

function marketChatScopeLabel(governorates, area) {
  if (area) return area.area;
  if (governorates.length === 1) return governorates[0];
  if (governorates.length > 1) return governorates.join(" و");
  return "";
}

function marketChatGovAreas(governorate) {
  const target = marketChatNorm(governorate);
  return ((insightsState.data || {}).areas || []).filter((a) => marketChatNorm(a.governorate) === target);
}

function marketChatPerM2Text(perM2, count) {
  if (perM2 == null) return null;
  return `${marketChatNum(perM2)} د.ك/م²${count != null ? ` (من ${count} عينة بيع)` : ""}`;
}

function answerMarketQuestion(rawText) {
  const data = insightsState.data;
  if (!data || !data.tableOk) {
    return { text: "بيانات تحليلات السوق لم تُحمَّل بعد — أعد السؤال بعد اكتمال التحميل، أو افتح تبويب «تحليلات السوق» أولًا." };
  }
  const areas = data.areas || [];
  const governorates = data.governorates || [];
  const demand = insightsState.demand || {};
  const q = normalizeArabic(rawText);
  const { governorates: govMentions, area } = marketChatScopes(q);
  const gov = govMentions[0] || null;
  const scopeLabel = marketChatScopeLabel(govMentions, area);

  // مقارنة محافظات: «قارن بين العاصمة وحولي»
  if (govMentions.length >= 2 && (q.includes("قارن") || q.includes("مقارن"))) {
    const rows = govMentions.map((name) => {
      const g = governorates.find((x) => marketChatNorm(x.governorate) === marketChatNorm(name));
      const gAreas = marketChatGovAreas(name);
      const rentMed = marketChatMedian(gAreas.map((a) => a.medianRent));
      const yieldMed = marketChatMedian(gAreas.map((a) => a.rentalYield));
      return {
        name,
        perM2: g ? g.medianSalePerM2 : marketChatMedian(gAreas.map((a) => a.medianSalePerM2)),
        rent: rentMed,
        yield: yieldMed,
        areas: gAreas.length,
      };
    });
    const cells = rows.map((r) => `
      <div class="market-compare-col">
        <b>${escapeHtml(r.name)}</b>
        <span>سعر المتر: ${marketChatPerM2Text(r.perM2, null) || "—"}</span>
        <span>وسيط الإيجار: ${r.rent != null ? `${marketChatNum(r.rent)} د.ك/شهر` : "—"}</span>
        <span>العائد: ${r.yield != null ? `${marketChatNum(r.yield, 1)}%` : "—"}</span>
        <small>${r.areas} منطقة محللة</small>
      </div>`).join("");
    return { text: `<div class="market-compare">${cells}</div>` };
  }

  // أفضل/أعلى عائد — «أعلى» تصبح «اعلي» بعد تطبيع الألف المقصورة
  if (q.includes("اعلي عائد") || q.includes("افضل عائد") || (q.includes("عائد") && (q.includes("افضل") || q.includes("اعلي منطقه")))) {
    const pool = areas.filter((a) => a.rentalYield != null && (!gov || marketChatNorm(a.governorate) === marketChatNorm(gov)) && (!area || marketChatNorm(a.area) === marketChatNorm(area.area)));
    if (!pool.length) return { text: "لا توجد مناطق بعائد إيجاري محسوب في هذا النطاق بعد — العائد يُحسب فقط عند توفر عينتين على الأقل بيعًا وإيجارًا." };
    const sorted = pool.slice().sort((a, b) => Number(b.rentalYield) - Number(a.rentalYield)).slice(0, 5);
    const rows = sorted.map((a) => `
      <div class="market-chat-row-inline">
        <b>${escapeHtml(a.area)}</b>
        <span>${marketChatNum(a.rentalYield, 1)}% سنويًا</span>
        <small>بيع ${marketChatNum(a.saleCount)} + إيجار ${marketChatNum(a.rentCount)} · ${a.yieldNote === "high" ? "ثقة عالية" : "تقديري"}</small>
      </div>`).join("");
    return { text: `${scopeLabel ? `أعلى عائد إيجاري ${scopeLabel ? `في ${escapeHtml(scopeLabel)}` : ""}:` : "أعلى عائد إيجاري سنوي (مناطق):"} <div class="market-chat-list">${rows}</div>` };
  }

  // أرخص منطقة (سعر متر)
  if (q.includes("ارخص") || q.includes("اقل سعر") || q.includes("اقل منطقه")) {
    const pool = areas.filter((a) => a.medianSalePerM2 != null && (!gov || marketChatNorm(a.governorate) === marketChatNorm(gov)));
    if (!pool.length) return { text: "لا توجد مناطق بوسيط سعر متر محسوب في هذا النطاق بعد." };
    const sorted = pool.slice().sort((a, b) => Number(a.medianSalePerM2) - Number(b.medianSalePerM2)).slice(0, 5);
    const rows = sorted.map((a) => `
      <div class="market-chat-row-inline">
        <b>${escapeHtml(a.area)}</b>
        <span>${marketChatPerM2Text(a.medianSalePerM2, a.saleCount)}</span>
        <small>${escapeHtml(a.governorate || "")}</small>
      </div>`).join("");
    return { text: `${scopeLabel ? `أرخص المناطق ${`في ${escapeHtml(scopeLabel)}`}:` : "أرخص المناطق سعر متر (بيع):"} <div class="market-chat-list">${rows}</div>` };
  }

  // أغلى منطقة (سعر متر) — «أغلى/أعلى» تصبح «اغلي/اعلي» بعد تطبيع الألف المقصورة
  if (q.includes("اغلي") || q.includes("اعلي سعر")) {
    const pool = areas.filter((a) => a.medianSalePerM2 != null && (!gov || marketChatNorm(a.governorate) === marketChatNorm(gov)));
    if (!pool.length) return { text: "لا توجد مناطق بوسيط سعر متر محسوب في هذا النطاق بعد." };
    const sorted = pool.slice().sort((a, b) => Number(b.medianSalePerM2) - Number(a.medianSalePerM2)).slice(0, 5);
    const rows = sorted.map((a) => `
      <div class="market-chat-row-inline">
        <b>${escapeHtml(a.area)}</b>
        <span>${marketChatPerM2Text(a.medianSalePerM2, a.saleCount)}</span>
        <small>${escapeHtml(a.governorate || "")}</small>
      </div>`).join("");
    return { text: `${scopeLabel ? `أغلى المناطق ${`في ${escapeHtml(scopeLabel)}`}:` : "أغلى المناطق سعر متر (بيع):"} <div class="market-chat-list">${rows}</div>` };
  }

  // اتجاه السوق — يُفحص قبل «سعر المتر» لأن «اتجاه سعر المتر العام» يحوي كلمة «سعر المتر»
  if (q.includes("اتجاه") || q.includes("صاعد") || q.includes("هابط") || q.includes("مستقر") || q.includes("وضع السوق") || q.includes("كيف السوق")) {
    const market = data.market || {};
    const dir = market.direction || "—";
    const change = market.changePct;
    const mSeries = (market.series || []).filter((p) => p.perM2 != null);
    const first = mSeries[0];
    const last = mSeries[mSeries.length - 1];
    const range = first && last && first.perM2 != null && last.perM2 != null
      ? ` — سعر المتر العام ${marketChatNum(first.perM2)} ← ${marketChatNum(last.perM2)} د.ك/م² عبر الأشهر`
      : "";
    return { text: `اتجاه سعر المتر العام: <b>${escapeHtml(dir)}</b>${change != null ? ` — تغير ${change > 0 ? "+" : ""}${marketChatNum(change, 1)}% بين أول وآخر شهر حصاد.` : "."}${range}` };
  }

  // سعر المتر
  if (q.includes("سعر المتر") || (q.includes("المتر") && (q.includes("سعر") || q.includes("كم")))) {
    if (area && area.medianSalePerM2 != null) {
      const gap = area.medianSalePerM2 != null && area.governorate ? (() => {
        const g = governorates.find((x) => marketChatNorm(x.governorate) === marketChatNorm(area.governorate));
        if (!g || !g.medianSalePerM2) return null;
        return ((area.medianSalePerM2 - g.medianSalePerM2) / g.medianSalePerM2) * 100;
      })() : null;
      return { text: `وسيط سعر المتر في <b>${escapeHtml(area.area)}</b> هو <b>${marketChatPerM2Text(area.medianSalePerM2, area.saleCount)}</b>${gap != null ? ` — ${gap <= -8 ? "أقل من وسيط محافظته (فرصة)" : gap >= 8 ? "أعلى من وسيط محافظته (مضخم)" : "قريب من وسيط محافظته"}` : ""}.` };
    }
    if (gov) {
      const g = governorates.find((x) => marketChatNorm(x.governorate) === marketChatNorm(gov));
      const gAreas = marketChatGovAreas(gov);
      if (g && g.medianSalePerM2 != null) {
        return { text: `وسيط سعر المتر في <b>${escapeHtml(gov)}</b> هو <b>${marketChatPerM2Text(g.medianSalePerM2, gAreas.length ? gAreas.reduce((s, a) => s + Number(a.saleCount || 0), 0) : null)}</b> — وسيط وسيطات ${gAreas.length} منطقة محللة.` };
      }
      return { text: `لا توجد بيانات سعر متر كافية لمحافظة ${escapeHtml(gov)} بعد.` };
    }
    if (governorates.length) {
      const rows = governorates.slice().sort((a, b) => Number(b.medianSalePerM2 || 0) - Number(a.medianSalePerM2 || 0)).map((g) => `
        <div class="market-chat-row-inline">
          <b>${escapeHtml(g.governorate)}</b>
          <span>${marketChatPerM2Text(g.medianSalePerM2, null)}</span>
        </div>`).join("");
      return { text: `وسيط سعر المتر حسب المحافظات (تنازليًا): <div class="market-chat-list">${rows}</div>` };
    }
    const sortedGovs = governorates.slice().sort((a, b) => Number(b.medianSalePerM2 || 0) - Number(a.medianSalePerM2 || 0));
    if (sortedGovs.length) {
      const rows = sortedGovs.map((g) => `
        <div class="market-chat-row-inline">
          <b>${escapeHtml(g.governorate)}</b>
          <span>${marketChatPerM2Text(g.medianSalePerM2, null)}</span>
        </div>`).join("");
      return { text: `وسيط سعر المتر حسب المحافظات (تنازليًا): <div class="market-chat-list">${rows}</div>` };
    }
    return { text: "لا توجد بيانات سعر متر محسوبة بعد — تتكوّن مع تراكم الحصاد اليومي." };
  }

  // متوسط سعر البيع (إجمالي)
  if (q.includes("سعر البيع") || q.includes("متوسط سعر") || (q.includes("سعر") && !q.includes("ايجار"))) {
    if (area && area.medianSalePrice != null) {
      return { text: `وسيط سعر البيع في <b>${escapeHtml(area.area)}</b> هو <b>${formatKd(area.medianSalePrice)} د.ك</b> (من ${marketChatNum(area.saleCount)} عينة بيع).` };
    }
    if (gov) {
      const gAreas = marketChatGovAreas(gov).filter((a) => a.medianSalePrice != null);
      const med = marketChatMedian(gAreas.map((a) => a.medianSalePrice));
      if (med != null) return { text: `وسيط سعر البيع في <b>${escapeHtml(gov)}</b> هو <b>${formatKd(med)} د.ك</b> (من ${gAreas.reduce((s, a) => s + Number(a.saleCount || 0), 0)} عينة بيع).` };
      return { text: `لا توجد بيانات سعر بيع كافية لمحافظة ${escapeHtml(gov)} بعد.` };
    }
    const total = data.sampleTotals || {};
    return { text: `الحصاد المتراكم يحوي <b>${marketChatNum(total.sale || 0)} إعلان بيع</b> و<b>${marketChatNum(total.rent || 0)} إعلان إيجار</b> — اذكر منطقة أو محافظة لأسألك عن وسيط سعرها.` };
  }

  // الإيجار — أسئلة «عائد إيجار» تمر لفرع العائد و«طلب إيجار» لفرع الطلبات أدناه
  if ((q.includes("ايجار") || q.includes("الاجار")) && !q.includes("عائد") && !q.includes("طلب") && !q.includes("مطلوب")) {
    if (area && area.medianRent != null) {
      return { text: `وسيط الإيجار في <b>${escapeHtml(area.area)}</b> هو <b>${formatKd(area.medianRent)} د.ك/شهر</b>${area.rentalYield != null ? ` — والعائد الإيجاري السنوي المتوقع ${marketChatNum(area.rentalYield, 1)}%` : ""}.` };
    }
    if (gov) {
      const gAreas = marketChatGovAreas(gov).filter((a) => a.medianRent != null);
      const med = marketChatMedian(gAreas.map((a) => a.medianRent));
      if (med != null) return { text: `وسيط الإيجار في <b>${escapeHtml(gov)}</b> هو <b>${formatKd(med)} د.ك/شهر</b> (من ${gAreas.reduce((s, a) => s + Number(a.rentCount || 0), 0)} عينة إيجار).` };
      return { text: `لا توجد بيانات إيجار كافية لمحافظة ${escapeHtml(gov)} بعد.` };
    }
    return { text: "اذكر منطقة أو محافظة مع كلمة إيجار — مثال: «متوسط الإيجار في السالمية»." };
  }

  // العائد (بدون اسم منطقة — نظهر الأعلى)
  if (q.includes("عائد")) {
    const pool = areas.filter((a) => a.rentalYield != null && (!gov || marketChatNorm(a.governorate) === marketChatNorm(gov)));
    if (!pool.length) return { text: "لا توجد مناطق بعائد محسوب بعد — العائد يُحسب عند توفر عينتين على الأقل بيعًا وإيجارًا." };
    const sorted = pool.slice().sort((a, b) => Number(b.rentalYield) - Number(a.rentalYield)).slice(0, 5);
    const rows = sorted.map((a) => `
      <div class="market-chat-row-inline">
        <b>${escapeHtml(a.area)}</b>
        <span>${marketChatNum(a.rentalYield, 1)}%</span>
        <small>${escapeHtml(a.governorate || "")} · ${a.yieldNote === "high" ? "ثقة عالية" : "تقديري"}</small>
      </div>`).join("");
    return { text: `${gov ? `أعلى عائد إيجاري في ${escapeHtml(gov)}:` : "أعلى عائد إيجاري سنوي (مناطق):"} <div class="market-chat-list">${rows}</div>` };
  }

  // مؤشرات الطلب — يُفضَّل مستوى المحافظة عندما لا تكون المنطقة نفسها مسجلة في بيانات الطلب
  if (q.includes("طلب") || q.includes("مطلوب")) {
    const totals = demand.totals || {};
    const demandArea = area
      ? (demand.areas || []).find((x) => marketChatNorm(x.area) === marketChatNorm(area.area))
      : null;
    if (demandArea && Number(demandArea.total || 0) > 0) {
      return { text: `في <b>${escapeHtml(demandArea.area)}</b>: <b>${marketChatNum(demandArea.buy || 0)} طلب شراء</b> و<b>${marketChatNum(demandArea.rent || 0)} طلب إيجار</b> (الإجمالي ${marketChatNum(demandArea.total || 0)}).` };
    }
    if (gov) {
      const g = (demand.governorates || []).find((x) => marketChatNorm(x.governorate) === marketChatNorm(gov));
      if (g && Number(g.total || 0) > 0) {
        const prefix = demandArea ? `لم تُسجَّل طلبات باسم منطقة ${escapeHtml(demandArea.area)} نفسها، لكن ` : "";
        return { text: `${prefix}في <b>${escapeHtml(g.governorate)}</b>: <b>${marketChatNum(g.buy || 0)} طلب شراء</b> و<b>${marketChatNum(g.rent || 0)} طلب إيجار</b> (الإجمالي ${marketChatNum(g.total || 0)}).` };
      }
    }
    if (demandArea) return { text: `لا توجد طلبات مسجلة في ${escapeHtml(demandArea.area)} بعد.` };
    if (gov) return { text: `لا توجد طلبات مسجلة في ${escapeHtml(gov)} بعد.` };
    if (demand.tableOk) {
      return { text: `إجمالي الطلبات المتراكمة: <b>${marketChatNum(totals.total || 0)}</b> — منها <b>${marketChatNum(totals.buyRequests || 0)} طلب شراء</b> و<b>${marketChatNum(totals.rentRequests || 0)} طلب إيجار</b>. كل طلب عميل محتمل — افتح تبويب «أفضل الفرص» ← «العرض والطلب» للتفاصيل.` };
    }
    return { text: "لا توجد بيانات طلبات متراكمة بعد." };
  }

  // عينات/عدد الإعلانات
  if (q.includes("عدد") || q.includes("عينات") || q.includes("كم اعلان")) {
    const totals = data.sampleTotals || {};
    if (area) return { text: `في <b>${escapeHtml(area.area)}</b>: ${marketChatNum(area.saleCount || 0)} إعلان بيع و${marketChatNum(area.rentCount || 0)} إعلان إيجار.` };
    if (gov) {
      const gAreas = marketChatGovAreas(gov);
      return { text: `في <b>${escapeHtml(gov)}</b>: ${marketChatNum(gAreas.reduce((s, a) => s + Number(a.saleCount || 0), 0))} إعلان بيع و${marketChatNum(gAreas.reduce((s, a) => s + Number(a.rentCount || 0), 0))} إعلان إيجار عبر ${marketChatNum(gAreas.length)} منطقة محللة.` };
    }
    return { text: `الحصاد المتراكم: <b>${marketChatNum(totals.sale || 0)} إعلان بيع</b> + <b>${marketChatNum(totals.rent || 0)} إعلان إيجار</b> + <b>${marketChatNum(totals.buyRequests || 0)} طلب شراء</b> + <b>${marketChatNum(totals.rentRequests || 0)} طلب إيجار</b>.` };
  }

  // مصادر البيانات
  if (q.includes("مصدر") || q.includes("من اين")) {
    const sources = data.sources || [];
    if (!sources.length) return { text: "لا توجد بيانات مصادر في هذه اللقطة بعد." };
    const rows = sources.slice(0, 6).map((s) => `
      <div class="market-chat-row-inline">
        <b>${escapeHtml(s.source)}</b>
        <span>${marketChatNum(s.count)} إعلان (${marketChatNum(s.sharePct, 1)}%)</span>
      </div>`).join("");
    return { text: `مصادر بيانات هذا التحليل (الأعلى تغذية): <div class="market-chat-list">${rows}</div>` };
  }

  // لم يُفهم السؤال — إرشاد + أمثلة
  return {
    text: `لم أتعرف على المطلوب من هذا السؤال ضمن بيانات تحليلات السوق. جرّب صيغة مثل: «متوسط سعر المتر في <منطقة/محافظة>»، «أعلى عائد إيجار»، «كم طلب شراء في <محافظة>»، «اتجاه السوق»، أو «قارن بين <محافظة> و<محافظة>».<br><span class="market-chat-hint">للحصول على تقييم كامل بترتيب النتائج والمصادر استخدم تبويب «البحث والتقييم».</span>`,
  };
}

function appendMarketChat(role, html) {
  const log = $("marketChatLog");
  if (!log) return;
  const el = document.createElement("div");
  el.className = `market-chat-msg ${role}`;
  el.innerHTML = html;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}

function initMarketChat() {
  const input = $("marketChatInput");
  const send = $("marketChatSend");
  const chips = $("marketChatChips");
  const ask = async () => {
    const text = input ? input.value.trim() : "";
    if (!text) return;
    if (input) input.value = "";
    appendMarketChat("user", escapeHtml(text));
    // إن لم تكن البيانات محمَّلة بعد (فتح التبويب لأول مرة) نحمّلها أولًا ثم نجيب
    if (!insightsState.loaded) {
      appendMarketChat("bot", "جاري تحميل بيانات تحليلات السوق...");
      try {
        await loadInsights();
      } catch {
        appendMarketChat("bot", "تعذر تحميل بيانات تحليلات السوق — حاول مجددًا بعد قليل.");
        return;
      }
    }
    const answer = answerMarketQuestion(text);
    appendMarketChat("bot", answer.text);
  };
  if (send) send.addEventListener("click", ask);
  if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
  if (chips) {
    chips.innerHTML = MARKET_CHAT_SUGGESTIONS
      .map((s) => `<button type="button" class="market-chat-chip" data-q="${escapeHtml(s)}">${escapeHtml(s)}</button>`)
      .join("");
    chips.querySelectorAll("[data-q]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (input) input.value = btn.dataset.q;
        ask();
      });
    });
  }
}

async function boot() {
  initTheme();
  applySimpleMode();
  initCardReveal();
  bind();
  bindMainTabs();
  switchMainTab("search");
  bindOppEvents();
  populateAdvancedOptions();
  initAreaChips();
  initDealSimulator();
  initMortgageCalculator();
  initInsuranceCalculator();
  initSmartAlerts();
  initMetricsRegistry();
  initMarketChat();
  // تفعيل أزرار تبديل الخريطة الحرارية وحالة الوضع المحفوظ عند الإقلاع
  // (النقر عبر المعالج المفوض [data-heat-mode] في bind)
  document.querySelectorAll(".heatmap-mode-switch .mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.heatMode === heatmapMode);
  });
  syncHeatmapLegends();
  loadDashboardBoard();
  loadOpportunities();
  // عدّادات المشاركة ميزة الموقع المنشور (قراءة مباشرة من القاعدة عبر anon REST مثل
  // applyLiveDbCounts) — في وضع الخادم لا توجد لقطات static-data في نسخة نظيفة،
  // فيُحاول الجلب فيرجع 404 مسجَّل في الكونسول. يُحمَّل عند الحاجة في وضع الثابت فقط.
  if (STATIC_SNAPSHOT_MODE) loadShareCounts();
  // الحساب المجاني: إغلاق النافذة (زر/خلفية/Escape) + أحداث قائمة الأبحاث المحفوظة.
  // تُحمَّل الأبحاث المحفوظة عند وجود سرّ مسجّل فقط (لا نداءات في وضع الخادم النظيف
  // بلا مستخدم — صفر 404 في الكونسول).
  const accountCloseBtn = $("accountCloseBtn");
  if (accountCloseBtn) accountCloseBtn.onclick = closeAccountModal;
  const accountModal = $("accountModal");
  if (accountModal) {
    accountModal.addEventListener("click", (e) => {
      if (e.target === accountModal) closeAccountModal();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAccountModal();
  });
  bindSavedSearchesEvents();
  bindPortfolioEvents();
  renderPlatformDates();
  // الجرس: التبديل + الإغلاق عند النقر خارجه أو Escape؛ تُحمَّل التنبيهات عند وجود سرّ فقط
  const bellToggle = $("bellToggle");
  if (bellToggle) bellToggle.onclick = toggleBell;
  document.addEventListener("click", (e) => {
    const wrap = e.target.closest && e.target.closest(".bell-wrap");
    if (!wrap) closeBell();
  });
  if (accountState.secret) {
    loadSavedSearches();
    loadUserAlerts();
    loadPortfolio();
  }
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

// ── نظام التتبع والتحليل + تصدير PDF/Excel ────────────────────────────
const Analytics = {
  _events: [],
  init() {
    try { this._events = JSON.parse(localStorage.getItem("alforaij_analytics") || "[]"); } catch { this._events = []; }
    this.track("pageview", { page: location.pathname, title: document.title });
    this._trackClicks();
    this._trackSearchInterests();
    setInterval(() => this.flush(), 30000);
  },
  track(event, data) {
    this._events.push({ event, data, ts: Date.now(), page: location.pathname });
    localStorage.setItem("alforaij_analytics", JSON.stringify(this._events.slice(-500)));
  },
  flush() {
    const batch = this._events.splice(0);
    localStorage.setItem("alforaij_analytics", JSON.stringify(this._events));
    if (batch.length > 0 && navigator.sendBeacon) {
      try { navigator.sendBeacon("/api/analytics", JSON.stringify(batch)); } catch {}
    }
  },
  _trackClicks() {
    document.addEventListener("click", (e) => {
      const el = e.target.closest("button, a, [data-track]");
      if (!el) return;
      const label = el.textContent.trim().slice(0, 60) || el.getAttribute("aria-label") || el.dataset.track || "";
      const tag = el.tagName;
      this.track("click", { label, tag, id: el.id || "" });
    }, true);
  },
  _trackSearchInterests() {
    const origSend = window.sendChat;
    if (typeof origSend === "function") {
      const patched = async function() {
        const input = document.getElementById("chatInput");
        const q = (input ? input.value.trim() : "");
        if (q) Analytics.track("search", { query: q, len: q.length });
        return origSend.apply(this, arguments);
      };
      window.sendChat = patched;
    }
  },
  getInsights() {
    const clicks = {};
    const searches = {};
    const pages = {};
    this._events.forEach(e => {
      if (e.event === "click") { const k = e.data.label; clicks[k] = (clicks[k] || 0) + 1; }
      if (e.event === "search") { const k = e.data.query; searches[k] = (searches[k] || 0) + 1; }
      if (e.event === "pageview") { const k = e.data.page; pages[k] = (pages[k] || 0) + 1; }
    });
    return { clicks, searches, pages, total: this._events.length };
  },
};
try { Analytics.init(); } catch {}

// ── تصدير نتائج الشات كـ PDF ──────────────────────
function exportChatPDF() {
  const msgs = document.querySelectorAll("#chatWindow .chat-msg, #assistantMessages .assistant-msg");
  if (!msgs.length) { alert("لا توجد رسائل للتصدير"); return; }
  let text = "منصة الفريج — نتائج البحث" + "\n" + "=".repeat(40) + "\n\n";
  msgs.forEach(m => {
    const isBot = m.classList.contains("chat-msg-bot") || m.classList.contains("assistant-msg-bot");
    const body = (m.querySelector(".chat-msg-body, .assistant-msg-body") || m).textContent.trim();
    text += (isBot ? "🤖 المساعد: " : "👤 أنت: ") + body + "\n\n";
  });
  text += "\n" + "=".repeat(40) + "\n" + "تصدير من منصة الفريج — " + new Date().toLocaleDateString("ar");
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "alforaij-results.txt";
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── تصدير نتائج الشات كـ Excel (CSV) ────────────────
function exportChatExcel() {
  const msgs = document.querySelectorAll("#chatWindow .chat-msg, #assistantMessages .assistant-msg");
  if (!msgs.length) { alert("لا توجد رسائل للتصدير"); return; }
  let csv = "\uFEFFالمرسل,الرسالة,الوقت\n";
  msgs.forEach(m => {
    const isBot = m.classList.contains("chat-msg-bot") || m.classList.contains("assistant-msg-bot");
    const body = (m.querySelector(".chat-msg-body, .assistant-msg-body") || m).textContent.trim().replace(/"/g, '""');
    csv += `"${isBot ? "المساعد" : "المستخدم"}","${body}","${new Date().toLocaleTimeString("ar")}"\n`;
  });
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "alforaij-results.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── تتبع تتبع النقرات في لوحة التحكم ──────────────
function getAnalyticsDashboard() {
  const insights = Analytics.getInsights();
  const topClicks = Object.entries(insights.clicks).sort((a,b) => b[1] - a[1]).slice(0, 10);
  const topSearches = Object.entries(insights.searches).sort((a,b) => b[1] - a[1]).slice(0, 10);
  const topPages = Object.entries(insights.pages).sort((a,b) => b[1] - a[1]).slice(0, 10);
  return { totalEvents: insights.total, topClicks, topSearches, topPages };
}

// ── لوحة التحليلات المتقدمة ──────────────────────
(async function _initAnalyticsDashboard() {
  const root = $("analyticsDashboard");
  if (!root) return;

  function _bar(items, maxVal) {
    if (!items || !items.length) return "<p class=\"muted\">لا توجد بيانات</p>";
    const mx = maxVal || Math.max(...items.map(i => i.count));
    return items.map(i => {
      const pct = mx > 0 ? (i.count / mx * 100) : 0;
      const label = i.area || i.source || i.type || i.query || i.transaction || "";
      return `<div class="stat-bar">
        <span class="stat-bar-label">${escapeHtml(label)}</span>
        <div style="flex:1"><div class="stat-bar-fill" style="width:${pct}%"></div></div>
        <span class="stat-bar-count">${i.count}</span>
      </div>`;
    }).join("");
  }

  function _render(d) {
    const o = d.overview || {};
    const sp = d.searchPatterns || {};
    const ms = d.marketStats || {};
    const trends = d.priceTrends || {};
    const daily = d.dailyActivity || {};
    const po = d.priceOverview || {};

    let html = "";

    // ── ملخص عام ──
    html += `<div class="analytics-card">
      <h3>📋 ملخص عام</h3>
      <div class="big-number">${o.totalSearches || 0}</div>
      <div style="color:var(--text-secondary);font-size:0.85rem;margin:4px 0 16px">بحث مسجل</div>
      <div class="stat-row"><span>إعلانات السوق</span><span>${o.totalMarketListings || 0}</span></div>
      <div class="stat-row"><span>المناطق المشمولة</span><span>${o.uniqueAreas || 0}</span></div>
      <div class="stat-row"><span>متوسط سعر البحث</span><span>${(o.avgSearchPrice || 0).toLocaleString()} د.ك</span></div>
    </div>`;

    // ── أسعار السوق ──
    html += `<div class="analytics-card">
      <h3>💰 إحصائيات الأسعار</h3>
      <div class="big-number">${(po.median || 0).toLocaleString()}</div>
      <div style="color:var(--text-secondary);font-size:0.85rem;margin:4px 0 16px">وسيط السعر (د.ك)</div>
      <div class="stat-row"><span>أقل سعر</span><span>${(po.min || 0).toLocaleString()} د.ك</span></div>
      <div class="stat-row"><span>أعلى سعر</span><span>${(po.max || 0).toLocaleString()} د.ك</span></div>
      <div class="stat-row"><span>متوسط</span><span>${(po.avg || 0).toLocaleString()} د.ك</span></div>
      <div class="stat-row"><span>عدد العينات</span><span>${po.count || 0}</span></div>
    </div>`;

    // ── أكثر المناطق بحثًا ──
    html += `<div class="analytics-card">
      <h3>📍 المناطق الأكثر بحثًا</h3>
      ${_bar((sp.topAreas || []).slice(0, 8))}
    </div>`;

    // ── أنواع العقارات ──
    html += `<div class="analytics-card">
      <h3>🏠 أنواع العقارات</h3>
      ${_bar(sp.propertyTypes || [])}
    </div>`;

    // ── أنواع المعاملات ──
    html += `<div class="analytics-card">
      <h3>🔄 أنواع المعاملات</h3>
      ${_bar(sp.transactionTypes || [])}
    </div>`;

    // ── مصادر السوق ──
    html += `<div class="analytics-card">
      <h3>🌐 مصادر الإعلانات</h3>
      ${_bar(ms.topSources || [])}
    </div>`;

    // ── النشاط اليومي ──
    if (daily.dates && daily.dates.length) {
      const maxDaily = Math.max(...daily.searches);
      const bars = daily.searches.map((c, i) => {
        const h = maxDaily > 0 ? (c / maxDaily * 100) : 0;
        return `<div class="analytics-chart-bar" style="height:${h}%" data-tip="${daily.dates[i]}: ${c} بحث"></div>`;
      }).join("");
      const labels = daily.dates.length > 1
        ? `<div class="analytics-chart-labels"><span>${daily.dates[0]}</span><span>${daily.dates[daily.dates.length - 1]}</span></div>`
        : "";
      html += `<div class="analytics-card analytics-wide">
        <h3>📈 النشاط اليومي (آخر 30 يوم)</h3>
        <div class="analytics-chart">${bars}</div>
        ${labels}
      </div>`;
    }

    // ── أسعار حسب المنطقة ──
    const ap = ms.areaPrices || {};
    const apKeys = Object.keys(ap).slice(0, 8);
    if (apKeys.length) {
      const rows = apKeys.map(a => {
        const s = ap[a];
        return `<div class="stat-row">
          <span>${escapeHtml(a)}</span>
          <span>وسيط: ${(s.median || 0).toLocaleString()} د.ك (${s.count} إعلان)</span>
        </div>`;
      }).join("");
      html += `<div class="analytics-card analytics-wide">
        <h3>📊 متوسط الأسعار حسب المنطقة</h3>
        ${rows}
      </div>`;
    }

    root.innerHTML = html;
  }

  async function _load() {
    root.innerHTML = "<p class=\"muted\">جاري تحميل البيانات…</p>";
    try {
      const res = await fetch("/api/analytics-dashboard", { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      const data = await res.json();
      _render(data);
    } catch (err) {
      root.innerHTML = `<p class=\"muted\">تعذر تحميل البيانات: ${escapeHtml(String(err))}</p>`;
    }
  }

  window._refreshAnalytics = _load;

  // تحميل عند فتح التبويب
  const tabs = document.querySelectorAll("[data-main-tab='analytics']");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      if (!root.dataset.loaded) {
        root.dataset.loaded = "1";
        _load();
      }
    });
  });
})();
