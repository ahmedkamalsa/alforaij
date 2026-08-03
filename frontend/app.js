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

function numberOrNull(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
    `نمط العملية: ${state.mode}`,
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

function renderSources(sources) {
  const root = $("sourceStatus");
  root.innerHTML = "";
  for (const source of sources || []) {
    const item = document.createElement("div");
    item.className = `badge ${source.status}`;
    item.textContent = `${source.name}: ${source.records} سجل - ${source.status}`;
    root.appendChild(item);
  }
}

function fact(label, value) {
  if (value === null || value === undefined || value === "") return "";
  return `<span class="fact">${escapeHtml(label)}: ${escapeHtml(value)}</span>`;
}

function renderReport(report) {
  $("summaryText").textContent = report.summary;
  renderSources(report.sourceStatus);

  const results = report.results || [];
  $("resultCount").textContent = `${results.length} نتيجة`;
  const root = $("results");
  root.innerHTML = "";
  if (!results.length) {
    root.innerHTML = '<div class="empty">لا توجد نتائج كافية حسب الفلاتر الحالية.</div>';
    return;
  }

  const template = $("resultTemplate");
  for (const item of results) {
    const node = template.content.cloneNode(true);
    node.querySelector("h3").textContent = `${item.code} - ${item.area || "منطقة غير محددة"}`;
    node.querySelector(".meta").textContent = `${item.governorate || ""} | ${item.transaction || ""} | ${item.propertyType || item.detailClass || ""}`;
    node.querySelector(".score").textContent = `${item.valuationLabel} (${Math.round((item.confidence || 0) * 100)}%)`;
    node.querySelector(".facts").innerHTML = [
      fact("السعر", item.priceText || item.price),
      fact("المساحة", item.space ? `${item.space} م²` : "غير مذكورة"),
      fact("تاريخ النشر", item.publishedDate),
      fact("درجة المطابقة", item.matchScore),
    ].join("");
    node.querySelector(".description").textContent = item.summary || item.features || "";
    node.querySelector(".reasons").innerHTML = (item.reasons || []).map((reason) => `<span class="reason">${escapeHtml(reason)}</span>`).join("");
    const comps = node.querySelector(".comparables");
    comps.innerHTML = (item.comparables || []).map((comp) => {
      const price = comp.priceText || comp.price || "غير معلن";
      return `<span class="comp">${escapeHtml(comp.code)} | ${escapeHtml(comp.area)} | ${escapeHtml(price)}</span>`;
    }).join("") || '<span class="comp">لا توجد مقارنات كافية</span>';
    const link = node.querySelector(".open-link");
    link.href = item.originalUrl || "#";
    link.hidden = !item.originalUrl;
    root.appendChild(node);
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
