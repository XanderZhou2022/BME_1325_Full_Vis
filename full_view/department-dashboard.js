const deptTabs = document.getElementById("deptTabs");
const deptCount = document.getElementById("deptCount");
const deptRefresh = document.getElementById("deptRefresh");
const deptTitle = document.getElementById("deptTitle");
const deptMeta = document.getElementById("deptMeta");
const deptStatus = document.getElementById("deptStatus");
const deptApiList = document.getElementById("deptApiList");
const deptRecent = document.getElementById("deptRecent");
const deptRecentCount = document.getElementById("deptRecentCount");
const scenarioRun = document.getElementById("scenarioRun");
const scenarioStatus = document.getElementById("scenarioStatus");
const scenarioLog = document.getElementById("scenarioLog");

const state = {
  departments: [],
  activeDepartmentId: window.location.hash.replace("#", "") || "outpatient",
  capabilities: null,
  schemas: {},
  examples: {},
  recent: [],
  results: {},
  scenarioRunning: false,
  scenarioEntries: [],
};

deptRefresh.addEventListener("click", () => loadDashboard());
scenarioRun.addEventListener("click", () => runClosedLoopScenario());
deptTabs.addEventListener("click", (event) => {
  const button = event.target.closest("[data-department-id]");
  if (!button) return;
  selectDepartment(button.dataset.departmentId);
});
deptApiList.addEventListener("click", async (event) => {
  const sendButton = event.target.closest("[data-send-request]");
  const copyButton = event.target.closest("[data-copy-curl]");
  if (sendButton) {
    await sendRequest(sendButton.dataset.sendRequest);
    return;
  }
  if (copyButton) {
    await copyCurl(copyButton.dataset.copyCurl);
  }
});

await loadDashboard();

async function loadDashboard() {
  deptStatus.textContent = "Loading";
  const data = await fetchJson("./api/v1/departments");
  state.departments = data.departments || [];
  if (!state.departments.some((item) => item.id === state.activeDepartmentId)) {
    state.activeDepartmentId = state.departments[0]?.id || "outpatient";
  }
  renderTabs();
  await loadDepartment(state.activeDepartmentId);
}

async function selectDepartment(departmentId) {
  state.activeDepartmentId = departmentId;
  window.location.hash = departmentId;
  state.results = {};
  renderTabs();
  await loadDepartment(departmentId);
}

async function loadDepartment(departmentId) {
  deptStatus.textContent = "Loading handler";
  const [capabilities, schemas, examples, recent] = await Promise.all([
    fetchJson(`./api/v1/departments/${departmentId}/capabilities`),
    fetchJson(`./api/v1/departments/${departmentId}/schemas`),
    fetchJson(`./api/v1/departments/${departmentId}/examples`),
    fetchJson(`./api/v1/departments/${departmentId}/requests/recent`),
  ]);
  state.capabilities = capabilities.data;
  state.schemas = schemas.data || {};
  state.examples = examples.data || {};
  state.recent = recent.data?.requests || [];
  renderDepartment();
  deptStatus.textContent = "Ready";
}

function renderTabs() {
  deptCount.textContent = `${state.departments.length}`;
  deptTabs.innerHTML = state.departments.map((department) => `
    <button class="dept-tab${department.id === state.activeDepartmentId ? " is-active" : ""}" type="button" data-department-id="${escapeAttr(department.id)}">
      <strong>${escapeHtml(department.label)}</strong>
      <span>${escapeHtml(department.producer)}</span>
      <em>${department.enabledRequestTypes.length} APIs</em>
    </button>
  `).join("");
}

function renderDepartment() {
  const capabilities = state.capabilities;
  if (!capabilities) return;
  deptTitle.textContent = capabilities.label;
  deptMeta.textContent = `${capabilities.producer} · ${capabilities.architecture}`;
  deptApiList.innerHTML = capabilities.requestTypes.map((requestType) => renderApiCard(requestType)).join("");
  renderRecent();
}

function renderApiCard(requestType) {
  const example = state.examples[requestType.id] || {};
  const schema = state.schemas[requestType.id] || {};
  const currentResult = state.results[requestType.id];
  const path = requestType.path;
  return `
    <article class="dept-api-card" data-request-card="${escapeAttr(requestType.id)}">
      <div class="dept-api-card__head">
        <div>
          <h3>${escapeHtml(requestType.label)}</h3>
          <p>${escapeHtml(requestType.description)}</p>
        </div>
        <code>${escapeHtml(requestType.method)} ${escapeHtml(path)}</code>
      </div>

      <div class="dept-api-card__grid">
        <section>
          <h4>Request JSON</h4>
          <textarea class="dept-json-input" spellcheck="false" data-request-payload="${escapeAttr(requestType.id)}">${escapeHtml(JSON.stringify(example, null, 2))}</textarea>
          <label class="dept-idempotency">
            <span>Idempotency-Key</span>
            <input data-idempotency-key="${escapeAttr(requestType.id)}" type="text" value="debug-${escapeAttr(state.activeDepartmentId)}-${escapeAttr(requestType.id)}" />
          </label>
          <div class="dept-actions">
            <button class="console-submit" type="button" data-send-request="${escapeAttr(requestType.id)}">Send Request</button>
            <button class="console-link" type="button" data-copy-curl="${escapeAttr(requestType.id)}">Copy curl</button>
          </div>
        </section>

        <section>
          <h4>Schema</h4>
          <pre class="dept-code">${escapeHtml(JSON.stringify(schema, null, 2))}</pre>
          ${renderAllowedRules(requestType.allowedRules || [])}
        </section>

        <section class="dept-result-panel">
          <h4>Result</h4>
          ${currentResult ? renderResult(currentResult) : `<div class="console-detail-empty">No request sent yet.</div>`}
        </section>
      </div>
    </article>
  `;
}

function renderAllowedRules(rules) {
  if (!rules.length) {
    return `<div class="dept-rule-list is-empty">No movement rule required.</div>`;
  }
  return `
    <div class="dept-rule-list">
      <h4>Allowed Rule IDs</h4>
      ${rules.map((rule) => `
        <div class="dept-rule-chip">
          <code>${escapeHtml(rule.eventId || rule.event_id)}</code>
          <span>${escapeHtml(rule.name || "")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderResult(result) {
  const status = result.ok && result.data?.accepted ? "accepted" : result.ok ? "rejected" : "error";
  const core = result.data?.coreResponse || {};
  return `
    <div class="dept-result is-${escapeAttr(status)}">
      <strong>${escapeHtml(status.toUpperCase())}</strong>
      <span>${escapeHtml(result.error?.code || core.reasonCode || core.eventId || core.event_id || "")}</span>
      <p>${escapeHtml(result.error?.message || core.message || "Response received.")}</p>
      <pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>
    </div>
  `;
}

function renderRecent() {
  deptRecentCount.textContent = `${state.recent.length}`;
  deptRecent.innerHTML = state.recent.length ? state.recent.map((request) => `
    <article class="dept-recent-item is-${escapeAttr(request.status || "unknown")}">
      <strong>${escapeHtml(request.requestType || request.request_type)}</strong>
      <span>${escapeHtml(request.status)} · ${escapeHtml(request.errorCode || request.error_code || "ok")}</span>
      <p>${escapeHtml(request.correlationId || request.correlation_id || "")}</p>
      <time>${escapeHtml(request.createdAt || request.created_at || "")}</time>
    </article>
  `).join("") : `<div class="console-detail-empty">No department requests yet.</div>`;
}

async function sendRequest(requestType) {
  const payloadElement = document.querySelector(`[data-request-payload="${CSS.escape(requestType)}"]`);
  const keyElement = document.querySelector(`[data-idempotency-key="${CSS.escape(requestType)}"]`);
  if (!payloadElement) return;
  let payload;
  try {
    payload = JSON.parse(payloadElement.value);
    payloadElement.classList.remove("is-invalid");
  } catch (error) {
    payloadElement.classList.add("is-invalid");
    state.results[requestType] = { ok: false, error: { code: "INVALID_JSON", message: error.message } };
    renderDepartment();
    return;
  }

  deptStatus.textContent = "Sending";
  const response = await fetch(`./api/v1/departments/${encodeURIComponent(state.activeDepartmentId)}/requests/${encodeURIComponent(requestType)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": keyElement?.value || "",
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  state.results[requestType] = result;
  await loadRecentOnly();
  renderDepartment();
  deptStatus.textContent = result.ok ? "Ready" : "Rejected";
}

async function loadRecentOnly() {
  const recent = await fetchJson(`./api/v1/departments/${state.activeDepartmentId}/requests/recent`);
  state.recent = recent.data?.requests || [];
}

async function copyCurl(requestType) {
  const payloadElement = document.querySelector(`[data-request-payload="${CSS.escape(requestType)}"]`);
  const keyElement = document.querySelector(`[data-idempotency-key="${CSS.escape(requestType)}"]`);
  const endpoint = `${window.location.origin}${window.location.pathname.replace(/department-dashboard\.html$/, "")}api/v1/departments/${state.activeDepartmentId}/requests/${requestType}`;
  const command = [
    `curl -X POST '${endpoint}'`,
    `  -H 'Content-Type: application/json'`,
    `  -H 'Idempotency-Key: ${keyElement?.value || ""}'`,
    `  --data '${compactJson(payloadElement?.value || "{}")}'`,
  ].join(" \\\n");
  await navigator.clipboard.writeText(command);
  deptStatus.textContent = "curl copied";
}

async function runClosedLoopScenario() {
  if (state.scenarioRunning) return;
  state.scenarioRunning = true;
  scenarioRun.disabled = true;
  state.scenarioEntries = [];
  renderScenarioLog();
  const runId = timestampRunId();
  scenarioStatus.textContent = `Running ${runId}`;
  window.open("./index.html", "fullview-map");

  try {
    const scenarioResponse = await fetchJson("./api/v1/debug/scenarios/closed-loop");
    const scenario = scenarioResponse.data;
    const context = buildScenarioContext(scenario, runId);
    appendScenarioEntry({ status: "running", text: `${scenario.label} started`, detail: scenario.description });

    for (const [index, step] of scenario.steps.entries()) {
      const payload = resolveScenarioPayload(step.payload, context, runId);
      const idempotencyKey = `${scenario.defaults?.idempotencyPrefix || "debug-closed-loop"}-${runId}-${String(index + 1).padStart(2, "0")}`;
      appendScenarioEntry({
        status: "running",
        text: `${index + 1}/${scenario.steps.length} ${step.title}`,
        detail: `${step.departmentId}.${step.requestType} · ${step.description}`,
      });
      const result = await postDepartmentRequest(step.departmentId, step.requestType, payload, idempotencyKey);
      updateScenarioContext(context, step, payload, result);
      const accepted = Boolean(result.data?.accepted);
      appendScenarioEntry({
        status: accepted ? "accepted" : "rejected",
        text: `${step.title} ${accepted ? "accepted" : "rejected"}`,
        detail: scenarioResultDetail(result),
      });
      if (!accepted) throw new Error(`${step.title}: ${result.error?.code || result.data?.coreResponse?.reasonCode || "REQUEST_REJECTED"}`);
      await delay(step.waitMs ?? scenario.defaults?.stepDelayMs ?? 1200);
    }

    appendScenarioEntry({
      status: "accepted",
      text: "Closed-loop test completed",
      detail: Object.values(context.patients).map((patient) => `${patient.patientId}: ${patient.discharged ? "discharged" : patient.currentRoom || "active"}`).join(" · "),
    });
    scenarioStatus.textContent = `Completed ${runId}`;
    await loadRecentOnly();
    renderDepartment();
  } catch (error) {
    appendScenarioEntry({ status: "rejected", text: "Closed-loop test stopped", detail: error.message });
    scenarioStatus.textContent = "Stopped";
  } finally {
    state.scenarioRunning = false;
    scenarioRun.disabled = false;
  }
}

function buildScenarioContext(scenario, runId) {
  const patients = {};
  (scenario.patients || []).forEach((patient) => {
    patients[patient.key] = {
      key: patient.key,
      label: patient.label,
      patientId: `P-DBG-${patient.key.toUpperCase()}-${runId}`,
      encounterId: `E-DBG-${patient.key.toUpperCase()}-${runId}`,
      currentRoom: "",
      bedRoom: "",
      discharged: false,
    };
  });
  return { patients };
}

function resolveScenarioPayload(payload, context, runId) {
  if (Array.isArray(payload)) return payload.map((item) => resolveScenarioPayload(item, context, runId));
  if (payload && typeof payload === "object") {
    return Object.fromEntries(Object.entries(payload).map(([key, value]) => [key, resolveScenarioPayload(value, context, runId)]));
  }
  if (typeof payload !== "string") return payload;
  return payload.replace(/\{\{([^}]+)\}\}/g, (_, token) => {
    if (token === "runId") return runId;
    const [patientKey, field] = token.split(".");
    if (context.patients[patientKey]) return context.patients[patientKey][field] || "";
    return "";
  });
}

async function postDepartmentRequest(departmentId, requestType, payload, idempotencyKey) {
  const response = await fetch(`./api/v1/departments/${encodeURIComponent(departmentId)}/requests/${encodeURIComponent(requestType)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`${departmentId}.${requestType}: HTTP ${response.status}`);
  return response.json();
}

function updateScenarioContext(context, step, payload, result) {
  const patient = context.patients[step.patientKey];
  if (!patient) return;
  patient.patientId = payload.patient_id || patient.patientId;
  patient.encounterId = payload.encounter_id || patient.encounterId;
  if (payload.room_id) patient.currentRoom = payload.room_id;

  const core = result.data?.coreResponse || {};
  const plan = core.animationPlan || core.animation_plan || {};
  const status = core.statusUpdates || core.status_updates || {};
  const bedRoom = status.bedRoomId || status.bed_room_id || status.previousRoomId || status.previous_room_id;
  if (bedRoom && step.requestType !== "discharge_request") patient.bedRoom = bedRoom;
  if (plan.toRoomId || plan.to_room_id) patient.currentRoom = plan.toRoomId || plan.to_room_id;
  if (status.bedRoomId || status.bed_room_id) patient.bedRoom = status.bedRoomId || status.bed_room_id;
  if (step.requestType === "discharge_request" && core.accepted) {
    patient.currentRoom = "";
    patient.discharged = true;
  }
}

function scenarioResultDetail(result) {
  const core = result.data?.coreResponse || {};
  const eventSeq = core.eventSeq || core.event_seq || "";
  const eventId = core.eventId || core.event_id || "";
  const reason = result.error?.code || core.reasonCode || core.message || "";
  return [`#${eventSeq}`, eventId, reason].filter(Boolean).join(" · ");
}

function appendScenarioEntry(entry) {
  state.scenarioEntries.unshift({ ...entry, time: new Date().toLocaleTimeString() });
  state.scenarioEntries = state.scenarioEntries.slice(0, 80);
  renderScenarioLog();
}

function renderScenarioLog() {
  scenarioLog.innerHTML = state.scenarioEntries.length ? state.scenarioEntries.map((entry) => `
    <article class="dept-scenario-entry is-${escapeAttr(entry.status)}">
      <strong>${escapeHtml(entry.text)}</strong>
      <span>${escapeHtml(entry.time || "")}</span>
      <p>${escapeHtml(entry.detail || "")}</p>
    </article>
  `).join("") : `<div class="console-detail-empty">No scenario run yet.</div>`;
}

function timestampRunId() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function compactJson(value) {
  try {
    return JSON.stringify(JSON.parse(value));
  } catch {
    return "{}";
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}
