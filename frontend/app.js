const state = {
  mode: "search_and_value",
  parsed: null,
  report: null,
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

function setStatus(text) {
  $("healthStatus").textContent = text;
}

function fillFields(request) {
  state.parsed = request;
  $("transactionField").value = request.transaction || "";
  $("typeField").value = request.property_type || "";
  $("areasField").value = (request.areas || []).join(", ");
  $("minAreaField").value = request.min_area ?? "";
  $("maxAreaField").value = request.max_area ?? "";
  $("budgetField").value = request.budget ?? "";
  $("rentBudgetField").value = request.rent_budget ?? "";
  $("bedroomsField").value = request.bedrooms ?? "";
}

function currentRequestText() {
  const text = $("requestText").value.trim();
  if (!state.parsed) return text;
  const additions = [
    $("transactionField").value && `العملية: ${$("transactionField").value}`,
    $("typeField").value && `نوع العقار: ${$("typeField").value}`,
    $("areasField").value && `المناطق: ${$("areasField").value}`,
    $("minAreaField").value && `المساحة من ${$("minAreaField").value}`,
    $("maxAreaField").value && `إلى ${$("maxAreaField").value} متر`,
    $("budgetField").value && `الميزانية ${$("budgetField").value} د.ك`,
    $("rentBudgetField").value && `الإيجار ${$("rentBudgetField").value} د.ك`,
    $("bedroomsField").value && `${$("bedroomsField").value} غرف`,
  ].filter(Boolean);
  return `${text}\n${additions.join("، ")}`;
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

async function parseRequest() {
  $("analyzeBtn").disabled = true;
  try {
    const data = await postJson("/api/parse", { text: $("requestText").value });
    fillFields(data.request);
  } finally {
    $("analyzeBtn").disabled = false;
  }
}

async function runAnalysis() {
  $("runBtn").disabled = true;
  $("summaryText").textContent = "جاري البحث والتقييم...";
  try {
    const report = await postJson("/api/analyze", { text: currentRequestText(), mode: state.mode });
    state.report = report;
    renderReport(report);
  } catch (error) {
    $("summaryText").textContent = "تعذر تشغيل التحليل. راجع نافذة الطرفية للتفاصيل.";
    console.error(error);
  } finally {
    $("runBtn").disabled = false;
  }
}

function renderSources(report) {
  const root = $("sourceStatus");
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
  $("connectedSources").textContent = connected || "-";

  const planRoot = $("externalSourcePlan");
  planRoot.innerHTML = "";
  for (const source of report.externalSourcePlan || []) {
    const item = document.createElement("div");
    item.className = "source-card pending";
    item.innerHTML = `
      <strong>${escapeHtml(source.name)}</strong>
      <span>${escapeHtml(source.status)}</span>
      <p>${escapeHtml(source.action)}</p>
    `;
    planRoot.appendChild(item);
  }

  const registryRoot = $("sourceRegistry");
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

  const linksRoot = $("externalLinks");
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
  $("externalBtn").disabled = !(report.externalSearchLinks || []).length;
}

function renderMethod(report) {
  const method = report.rankingMethod;
  if (!method) return;
  const weights = method.weights || {};
  $("rankingMethod").innerHTML = `
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

function renderReport(report) {
  $("summaryText").textContent = report.summary;
  renderSources(report);
  renderMethod(report);

  const results = report.results || [];
  $("resultCount").textContent = results.length;
  $("topScore").textContent = results[0] ? `${Math.round(results[0].recommendationScore)} / 100` : "-";

  const root = $("results");
  root.innerHTML = "";
  if (!results.length) {
    root.innerHTML = '<div class="empty">لا توجد نتائج كافية حسب الفلاتر الحالية.</div>';
    return;
  }

  const template = $("resultTemplate");
  results.forEach((item, index) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".rank-cell").textContent = index + 1;
    node.querySelector("h3").textContent = `${item.code} - ${item.area || "منطقة غير محددة"}`;
    node.querySelector(".meta").textContent = `${item.source || "مصدر غير محدد"} | ${item.governorate || ""} | ${item.transaction || ""} | ${item.propertyType || item.detailClass || ""}`;
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
      sourceItem("السعر", sources.price),
      sourceItem("المساحة", sources.space),
      sourceItem("وسيط المقارنات", sources.marketMedian),
      sourceItem("نسبة السعر للوسيط", sources.priceRatio),
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

function bind() {
  document.querySelectorAll(".mode").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".mode").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.mode = button.dataset.mode;
    });
  });
  $("analyzeBtn").addEventListener("click", parseRequest);
  $("runBtn").addEventListener("click", runAnalysis);
  $("printBtn").addEventListener("click", () => window.print());
  $("downloadReportBtn").addEventListener("click", downloadReport);
  $("externalBtn").addEventListener("click", () => {
    for (const link of state.report?.externalSearchLinks || []) {
      window.open(link.url, "_blank", "noreferrer");
    }
  });
}

async function boot() {
  bind();
  try {
    const health = await fetch("/api/health").then((r) => r.json());
    setStatus(`البيانات: ${health.records} إعلان`);
  } catch {
    setStatus("تعذر فحص البيانات");
  }
}

boot();
