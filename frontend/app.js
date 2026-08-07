const state = {
  mode: "search_and_value",
  report: null,
  chatMessages: [],
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// تحويل علامات **النص** إلى خط عريض بعد تأمين HTML (بدون مخاطرة XSS)
function formatSummary(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
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

async function postJson(path, payload) {
  const response = await fetch(path, {
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

async function sendChat() {
  const input = $("chatInput");
  if (!input) return;
  const text = input.value && input.value.trim();
  if (!text) return;
  const scope = document.querySelector('input[name="scope"]:checked')?.value || "company";
  const includeExternal = !!($("includeExternal") && $("includeExternal").checked);

  addChatMessage('user', `<div class="bubble user">${escapeHtml(text)}<div class="meta">نطاق: ${escapeHtml(scope)} | مصادر خارجية: ${includeExternal ? 'نعم' : 'لا'}</div></div>`);
  input.value = "";
  addChatMessage('assistant', `<div class="bubble assistant">جاري البحث والتقييم... <div class="meta">(${new Date().toLocaleTimeString()})</div></div>`);

  try {
    const payload = { text, mode: state.mode, includeExternal, scope };
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
        last.innerHTML = `<div class="bubble assistant">
          <strong>النتيجة:</strong>
          ${scopeText}
          <p>${formatSummary(report.summary || 'تم الحصول على نتائج.')}</p>
          <div class="chat-results-preview">${report.results && report.results.length ? `<strong>عدد النتائج:</strong> ${report.results.length} — أفضل توصية: ${Math.round(report.results[0].recommendationScore || 0)}/100` : 'لا توجد نتائج.'}</div>
          <div class="meta">${new Date().toLocaleTimeString()}</div>
        </div>`;
      }
    }

    renderReport(report);
    state.chatMessages.push({ role: 'assistant', text: report.summary || '', report });
  } catch (err) {
    console.error(err);
    addChatMessage('assistant', `<div class="bubble assistant error">تعذر الحصول على النتائج: ${escapeHtml(err.message)}</div>`);
  }
}

function renderSources(report) {
  const root = $("sourceStatus");
  if (!root) return;
  root.innerHTML = "";
  let connected = 0;
  for (const source of report.sourceStatus || []) {
    if (source.status === "success") connected += 1;
    const response = source.responseMs ? ` | ${source.responseMs}ms` : "";
    const available = source.availableCount ? ` | متاح بالموقع: ${source.availableCount}` : "";
    const candidates = source.candidates !== undefined ? ` | مفحوص: ${source.candidates}` : "";
    const url = source.url ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">فتح المصدر المفحوص</a>` : "";
    const item = document.createElement("div");
    item.className = `source-card ${source.status}`;
    item.innerHTML = `
      <strong>${escapeHtml(source.name)}</strong>
      <span>${escapeHtml(source.status)} | دخل التقييم: ${escapeHtml(source.records)}${escapeHtml(candidates)}${escapeHtml(response)}${escapeHtml(available)}</span>
      <p>${escapeHtml(source.note)}</p>
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
      const a = document.createElement("a");
      a.className = "external-link";
      a.href = link.url;
      a.target = "_blank";
      a.rel = "noreferrer";
      a.textContent = `بحث في ${link.name}`;
      a.title = link.evidenceStatus;
      linksRoot.appendChild(a);
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

function breakdownItem(item) {
  return `
    <div class="breakdown-item">
      <strong>${escapeHtml(item.name)}</strong>
      <span>${escapeHtml(item.points)} نقطة</span>
      <p>${escapeHtml(item.reason || `القيمة ${item.value ?? ""} - الوزن ${item.weight ?? ""}`)}</p>
    </div>
  `;
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

function renderReport(report) {
  const summaryEl = $("summaryText");
  if (summaryEl) summaryEl.innerHTML = formatSummary(report.summary || "");
  const scopeEl = $("searchScopeNote");
  if (scopeEl) {
    scopeEl.textContent = (report.searchScope && report.searchScope.note) || "";
    scopeEl.hidden = !report.searchScope;
  }
  const badge = $("analysisBadge");
  if (badge) {
    badge.textContent = analysisBadge(report.analysisMethod);
    badge.classList.toggle("ai", report.analysisMethod === "ai");
    badge.classList.toggle("local", report.analysisMethod === "local");
  }
  renderSources(report);
  renderMethod(report);

  const results = report.results || [];
  const resultCountEl = $("resultCount");
  if (resultCountEl) resultCountEl.textContent = results.length;
  const topScoreEl = $("topScore");
  if (topScoreEl) topScoreEl.textContent = results[0] ? `${Math.round(results[0].recommendationScore)} / 100` : "-";
  const persistenceEl = $("persistenceStatus");
  if (persistenceEl) persistenceEl.textContent = persistenceLabel(report.persistence);

  const root = $("results");
  if (!root) return;
  root.innerHTML = "";
  if (!results.length) {
    root.innerHTML = '<div class="empty">لا توجد نتائج كافية حسب الفلاتر الحالية.</div>';
    return;
  }

  const template = $("resultTemplate");
  if (!template) return;
  results.forEach((item, index) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".rank-cell").textContent = index + 1;
    node.querySelector("h3").textContent = `${item.code} - ${item.area || "منطقة غير محددة"}`;
    node.querySelector(".meta").textContent = `${item.source || "مصدر غير محدد"} | ${item.governorate || ""} | ${item.transaction || ""} | ${item.propertyType || item.detailClass || ""} | ${item.listingType || "غير محدد"}`;
    node.querySelector(".verdict-label").textContent = item.valuationLabel || "بدون حكم";
    node.querySelector(".recommendation").textContent = `توصية ${Math.round(item.recommendationScore || 0)} / 100`;
    node.querySelector(".score-grid").innerHTML = [
      scoreItem("السعر", item.priceText || item.price),
      scoreItem("المساحة", item.space ? `${item.space} م²` : "غير مذكورة"),
      scoreItem("وسيط المقارنات", formatMoney(item.marketMedian)),
      scoreItem("نسبة السعر للوسيط", item.priceRatio ? `${Math.round(item.priceRatio * 100)}%` : "غير كافية"),
      scoreItem("مطابقة الطلب", `${Math.round(item.matchScore || 0)} / 100`),
      scoreItem("الثقة", `${Math.round((item.confidence || 0) * 100)}%`, "confidence"),
      scoreItem("تاريخ النشر", item.publishedDate),
    ].join("");
    node.querySelector(".valuation-reason").textContent = item.valuationReason || "لا يوجد سبب تقييم كاف.";
    node.querySelector(".description").textContent = item.summary || item.features || "";

    const financingBlock = node.querySelector(".financing-info");
    if (item.financing && item.financing.monthly_payment) {
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
    const comps = node.querySelector(".comparables");
    comps.innerHTML = (item.comparables || []).map((comp) => {
      const price = comp.priceText || comp.price || "غير معلن";
      const href = comp.url ? ` href="${escapeHtml(comp.url)}" target="_blank" rel="noreferrer"` : "";
      return `<a class="comp"${href}>${escapeHtml(comp.code)} | ${escapeHtml(comp.area)} | ${escapeHtml(price)}</a>`;
    }).join("") || '<span class="comp">لا توجد مقارنات كافية</span>';

    const sources = item.numberSources || {};
    node.querySelector(".number-sources").innerHTML = [
      sourceItem("السعر المطلوب", sources.price),
      sourceItem("المساحة", sources.space),
      sourceItem("سعر المتر المطلوب", sources.pricePerSqm),
      sourceItem("وسيط أسعار المقارنات", sources.marketMedian),
      sourceItem("وسيط سعر المتر", sources.medianPerSqm),
      sourceItem("التقييم الرسمي للمنطقة", sources.officialValue),
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

    const link = node.querySelector(".open-link");
    link.href = item.originalUrl || "#";
    link.hidden = !item.originalUrl;
    root.appendChild(node);
  });
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
    const response = await fetch("/api/report-pdf", {
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
  tier: "daily",
  gov: "",
  area: "",
  type: "",
  minPrice: null,
  maxPrice: null,
  minScore: null,
};

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
  const minPrice = parseFloat($("oppMinPrice")?.value) || null;
  const maxPrice = parseFloat($("oppMaxPrice")?.value) || null;
  const minScore = parseFloat($("oppMinScore")?.value) || null;
  Object.assign(oppState, { gov, area, type, minPrice, maxPrice, minScore });
}

function oppFilteredItems(items) {
  return (items || []).filter((item) => {
    if (oppState.gov && item.governorate !== oppState.gov) return false;
    if (oppState.area && item.area !== oppState.area) return false;
    if (oppState.type && (item.propertyType || "") !== oppState.type) return false;
    if (oppState.minPrice != null && (item.price ?? 0) < oppState.minPrice) return false;
    if (oppState.maxPrice != null && (item.price ?? Infinity) > oppState.maxPrice) return false;
    if (oppState.minScore != null && (item.score ?? 0) < oppState.minScore) return false;
    return true;
  });
}

function oppClientChips(item) {
  if (!item.clients || !item.clients.length) return "";
  return `<div class="opp-clients">
    <strong>عملاء محتملون (${item.clients.length}):</strong>
    ${item.clients.map((client) => `
      <div class="opp-client">
        <span>${escapeHtml(client.area || "")} ${escapeHtml(client.type || "")} — تطابق ${client.matchScore}/100 (${escapeHtml((client.reasons || []).join("، "))})</span>
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

function oppCard(item, index) {
  const price = item.priceText || oppMoney(item.price);
  const days = item.daysAgo != null ? `${item.daysAgo} يوم` : "—";
  return `<article class="result-card opp-card">
    <div class="rank-cell opp-rank">${index + 1}</div>
    <div class="result-body">
      <div class="result-head">
        <div>
          <h3>${escapeHtml(item.code)} — ${escapeHtml(item.area || "غير محددة")}</h3>
          <p class="meta">${escapeHtml(item.source || "")} | ${escapeHtml(item.governorate || "")} | ${escapeHtml(item.transaction || "")} | ${escapeHtml(item.propertyType || "")} | نُشر منذ ${escapeHtml(days)}</p>
        </div>
        <div class="verdict opp-verdict">
          <span class="verdict-label">فرصة ${item.score}/100</span>
          <strong class="recommendation">${escapeHtml(item.valuationLabel || "")}</strong>
        </div>
      </div>
      <div class="score-grid">
        ${scoreItem("السعر", price)}
        ${scoreItem("المساحة", item.space ? `${item.space} م²` : "—")}
        ${scoreItem("سعر المتر", item.pricePerSqm ? `${item.pricePerSqm} د.ك/م²` : "—")}
        ${scoreItem("وسيط المقارنات", oppMoney(item.marketMedian))}
        ${scoreItem("التقييم", oppMoney(item.officialValue))}
        ${scoreItem("أساس التقييم", oppSourceKindLabel(item))}
        ${scoreItem("مقارنات", item.comparablesCount)}
        ${scoreItem("الثقة", `${Math.round((item.confidence || 0) * 100)}%`, "confidence")}
        ${scoreItem("جاذبية السعر", `${Math.round(item.dealScore || 0)}/100`)}
      </div>
      <p class="valuation-reason">${escapeHtml(item.valuationReason || "")}</p>
      ${oppClientChips(item)}
      ${item.url ? `<a class="open-link" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">فتح الإعلان الأصلي</a>` : ""}
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

function renderHistoryTab(root) {
  const data = oppState.history;
  if (!data || !data.series || !data.series.length) {
    root.innerHTML = '<div class="empty">لا توجد لقطات تاريخية كافية بعد. حدّث «أفضل الفرص» بانتظام لتُبنى سلسلة الأداء مع الوقت.</div>';
    return;
  }
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
  root.innerHTML = `
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

function renderOppTier() {
  const root = $("oppList");
  if (!root || !oppState.data) return;
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
  const tier = (oppState.data.tiers || {})[oppState.tier];
  if (!tier) {
    root.innerHTML = '<div class="empty">لا توجد بيانات.</div>';
    return;
  }
  const items = oppFilteredItems(tier.items);
  root.innerHTML = `<p class="scope-note">${escapeHtml(tier.label)} — ${escapeHtml(tier.description)} (يعرض ${items.length} من أصل ${(tier.items || []).length})</p>` +
    (items.length ? items.map(oppCard).join("") : '<div class="empty">لا توجد فرص مطابقة للفلاتر الحالية.</div>');
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

async function loadOpportunities(forceRefresh = false) {
  const root = $("oppList");
  if (!root) return;
  root.innerHTML = '<div class="empty">جاري تحميل أفضل الفرص...</div>';
  try {
    const response = await fetch(`/api/opportunities${forceRefresh ? "?refresh=1" : ""}`);
    if (!response.ok) throw new Error(await response.text());
    oppState.data = await response.json();

    const allItems = Object.values(oppState.data.tiers || {}).flatMap((tier) => tier.items || []);
    fillOppSelect("oppGovFilter", allItems.map((item) => item.governorate));
    fillOppSelect("oppAreaFilter", allItems.map((item) => item.area));
    fillOppSelect("oppTypeFilter", allItems.map((item) => item.propertyType));

    renderOppMeta();
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
      const res = await fetch("/api/clients");
      if (!res.ok) throw new Error(await res.text());
      const payload = await res.json();
      oppState.clients = payload.clients || [];
      renderClientsTab(root);
    } else if (tier === "alerts") {
      const res = await fetch("/api/whatsapp-alerts");
      if (!res.ok) throw new Error(await res.text());
      const payload = await res.json();
      oppState.alerts = payload.alerts || [];
      oppState.alertsNote = payload.note || "";
      renderAlertsTab(root);
    } else if (tier === "history") {
      const res = await fetch("/api/opportunities/history");
      if (!res.ok) throw new Error(await res.text());
      oppState.history = await res.json();
      renderHistoryTab(root);
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
      if (["clients", "alerts", "history"].includes(oppState.tier)) {
        loadOpportunityTab(oppState.tier);
      } else {
        renderOppTier();
      }
    });
  });
  const refreshBtn = $("oppRefreshBtn");
  if (refreshBtn) refreshBtn.addEventListener("click", () => loadOpportunities(true));
  ["oppGovFilter", "oppAreaFilter", "oppTypeFilter", "oppMinPrice", "oppMaxPrice", "oppMinScore"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("change", () => { collectOppFilters(); renderOppTier(); });
  });
}

function bind() {
  // ربط آمن: يتخطى أي زر غير موجود في الصفحة الحالية
  const on = (id, fn) => {
    const el = $(id);
    if (el) el.addEventListener("click", fn);
  };
  on("sendChatBtn", sendChat);
  on("clearChatBtn", clearChat);
  on("downloadReportBtn", downloadReport);
  on("downloadReportBtnTop", downloadReport);
  on("downloadPdfBtn", () => downloadPdfReport("downloadPdfBtn"));
  on("downloadPdfBtnTop", () => downloadPdfReport("downloadPdfBtnTop"));

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

async function boot() {
  bind();
  bindOppEvents();
  loadOpportunities();
  // تحديث أول بأول: أول تحميل يدمج المصادر الحية (لأن الكاش فارغ)، ثم تحديث محلي سريع كل 5 دقائق
  // (الفحص الحي المتكرر كل دقائق قد يُحظر من المواقع الخارجية — لذلك يكون صريحًا فقط)
  setInterval(() => {
    if (!document.hidden) loadOpportunities(false);
  }, 5 * 60 * 1000);
  try {
    const health = await fetch("/api/health").then((r) => r.json());
    const aiStatus = health.aiAnalysis ? "AI متاح" : "AI غير مضبوط (تحليل محلي)";
    setStatus(`البيانات: ${health.records} إعلان | Supabase: ${health.supabase ? "متصل" : "غير مضبوط"} | ${aiStatus}`);
  } catch {
    setStatus("تعذر فحص البيانات");
  }
}

boot();
