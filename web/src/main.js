import { createClient } from "@supabase/supabase-js";
import "./style.css";

const form = document.querySelector("#audit-form");
const fields = document.querySelector("#audit-fields");
const submitButton = document.querySelector("#submit-button");
const pendingNote = document.querySelector("#pending-note");
const formMessage = document.querySelector("#form-message");
const activeSection = document.querySelector("#active-audit");
const activeHeading = document.querySelector("#active-heading");
const statusBadge = document.querySelector("#status-badge");
const statusDescription = document.querySelector("#status-description");
const progressTrack = document.querySelector(".progress-track");
const progressFill = document.querySelector("#progress-fill");
const stepsList = document.querySelector("#steps-list");
const eventsList = document.querySelector("#events-list");
const artifactsPanel = document.querySelector("#artifacts-panel");
const artifactsList = document.querySelector("#artifacts-list");
const historyList = document.querySelector("#history-list");

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const terminalStatuses = new Set(["completed", "failed", "interrupted", "cancelled"]);
const statusCopy = {
  queued: "Your request is safely queued. You can leave this page and return later.",
  dispatching: "Preparing a dedicated audit worker. No action is needed from you.",
  running: "The live audit is collecting and comparing evidence. This page updates without reloading.",
  completed: "Your audit is ready. Download the report and supporting files below.",
  failed: "This audit could not finish. Your session and any available diagnostics were kept.",
  interrupted: "The audit worker stopped unexpectedly. It will not restart and repeat paid requests automatically.",
  cancelled: "This audit was cancelled.",
};
const artifactLabels = {
  zip_archive: "Complete ZIP",
  pdf_report: "PDF report",
  markdown_report: "Markdown",
  json_report: "Structured JSON",
  reddit_social: "Reddit data",
  log: "Run log",
  raw_json: "Raw data",
};

let config;
let supabase;
let storagePrefix;
let currentAuditId = null;
let currentAuditStatus = null;
let pollTimer = null;
let requestInFlight = false;

function auditIdFromHash() {
  return location.hash.match(/^#audit\/([0-9a-f-]{36})$/i)?.[1] || null;
}

function syncView() {
  const auditId = auditIdFromHash();
  document.body.dataset.view = auditId ? "audit" : location.hash === "#history" ? "history" : "home";
  if (auditId && config && auditId !== currentAuditId) void showAudit(auditId);
  window.scrollTo(0, 0);
}

syncView();
window.addEventListener("hashchange", syncView);

function showFormMessage(message) {
  formMessage.textContent = message;
  formMessage.hidden = !message;
}

function readStored(key) {
  try {
    return JSON.parse(localStorage.getItem(`${storagePrefix}:${key}`) || "null");
  } catch {
    return null;
  }
}

function saveStored(key, value) {
  localStorage.setItem(`${storagePrefix}:${key}`, JSON.stringify(value));
}

function clearStored(key) {
  localStorage.removeItem(`${storagePrefix}:${key}`);
}

function setFormState(mode) {
  const pending = mode === "pending";
  const running = mode === "running";
  fields.disabled = pending || running;
  submitButton.disabled = running || requestInFlight;
  pendingNote.hidden = !pending;
  submitButton.querySelector("span").textContent = pending
    ? "Retry safely"
    : running
      ? "Audit in progress"
      : "Run visibility audit";
}

function collectRequest() {
  const data = new FormData(form);
  return {
    client_request_id: crypto.randomUUID(),
    company_name: String(data.get("company_name") || "").trim(),
    company_domain: String(data.get("company_domain") || "").trim(),
    audit_focus: String(data.get("audit_focus") || "").trim(),
    country_code: String(data.get("country_code") || "US").trim().toUpperCase(),
    search_engine: String(data.get("search_engine") || "auto"),
    include_reddit_analysis: data.get("include_reddit_analysis") === "on",
    workshop_id: config.workshop_id,
  };
}

function restoreRequest(request) {
  for (const [name, value] of Object.entries(request)) {
    const control = form.elements.namedItem(name);
    if (!control) continue;
    if (control.type === "checkbox") control.checked = Boolean(value);
    else control.value = value;
  }
}

async function currentSession(createIfNeeded = false) {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  if (data.session) return data.session;
  if (!createIfNeeded) return null;
  const signedIn = await supabase.auth.signInAnonymously();
  if (signedIn.error || !signedIn.data.session) {
    throw new Error(signedIn.error?.message || "Could not start a workshop session");
  }
  return signedIn.data.session;
}

async function apiRequest(path, options = {}) {
  const session = await currentSession(false);
  if (!session) throw new Error("This audit belongs to a session on this browser. Start here to create one.");
  const response = await fetch(`${config.api_url}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
    cache: "no-store",
  });
  let body;
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (!response.ok) {
    const error = new Error(typeof body.detail === "string" ? body.detail : "The server could not complete this request.");
    error.status = response.status;
    throw error;
  }
  return body;
}

async function submitAudit(event) {
  event.preventDefault();
  if (requestInFlight) return;
  showFormMessage("");
  let request = readStored("pending");
  if (!request) {
    if (!form.reportValidity()) return;
    request = collectRequest();
    saveStored("pending", request);
  }
  requestInFlight = true;
  setFormState("pending");
  submitButton.disabled = true;
  try {
    await currentSession(true);
    const accepted = await apiRequest("/audits", {
      method: "POST",
      body: JSON.stringify(request),
    });
    clearStored("pending");
    saveStored("last-audit", accepted.audit_id);
    setFormState("running");
    location.hash = `audit/${accepted.audit_id}`;
    await showAudit(accepted.audit_id);
    await loadHistory();
  } catch (error) {
    if (error.status === 400 || error.status === 422) {
      clearStored("pending");
      setFormState("ready");
    }
    showFormMessage(error.message || "The audit could not be submitted. Try again safely.");
  } finally {
    requestInFlight = false;
    if (readStored("pending")) setFormState("pending");
    else if (currentAuditId && !terminalStatuses.has(currentAuditStatus)) setFormState("running");
    else setFormState("ready");
  }
}

function formatDate(value) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return "";
  }
}

function renderLines(target, rows, emptyText, makeLine) {
  target.replaceChildren();
  if (!rows.length) {
    const li = document.createElement("li");
    li.textContent = emptyText;
    target.append(li);
    return;
  }
  for (const row of rows) target.append(makeLine(row));
}

function renderAudit(audit) {
  activeSection.hidden = false;
  const status = audit.status || "queued";
  currentAuditStatus = status;
  activeHeading.textContent = `${audit.company_name || "Your company"} — visibility audit`;
  statusBadge.textContent = status.toUpperCase();
  statusBadge.className = `status-badge ${status}`;
  statusDescription.textContent = statusCopy[status] || "Checking the audit status.";
  progressTrack.classList.toggle("running", status === "running" || status === "dispatching");
  progressFill.style.width = status === "completed" ? "100%" : status === "queued" ? "7%" : "35%";
  const steps = audit.steps || [];
  renderLines(stepsList, steps, "Waiting for the first stage…", (step) => {
    const li = document.createElement("li");
    const title = document.createElement("span");
    const state = document.createElement("span");
    title.textContent = step.label;
    state.textContent = step.status;
    li.append(title, state);
    return li;
  });
  renderLines(eventsList, audit.events || [], "Progress notes will appear here.", (entry) => {
    const li = document.createElement("li");
    li.textContent = entry.message;
    const time = document.createElement("small");
    time.textContent = formatDate(entry.created_at);
    li.append(time);
    return li;
  });
  const artifacts = audit.artifacts || [];
  artifactsPanel.hidden = artifacts.length === 0;
  artifactsList.replaceChildren();
  for (const artifact of artifacts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "artifact-button";
    button.textContent = `${artifactLabels[artifact.kind] || "File"} ↗`;
    button.addEventListener("click", () => downloadArtifact(audit.id, artifact.id, button));
    artifactsList.append(button);
  }
  setFormState(terminalStatuses.has(status) ? "ready" : "running");
}

async function downloadArtifact(auditId, artifactId, button) {
  button.disabled = true;
  try {
    const result = await apiRequest(`/audits/${auditId}/artifacts/${artifactId}/download`);
    window.location.assign(result.url);
  } catch (error) {
    showFormMessage(error.message || "Could not prepare the download.");
  } finally {
    button.disabled = false;
  }
}

async function refreshAudit() {
  if (!currentAuditId || document.hidden) return false;
  try {
    const audit = await apiRequest(`/audits/${currentAuditId}`);
    renderAudit(audit);
    if (terminalStatuses.has(audit.status)) {
      clearInterval(pollTimer);
      pollTimer = null;
      await loadHistory();
      return true;
    }
  } catch (error) {
    if (error.status === 404) {
      clearStored("last-audit");
      currentAuditId = null;
      currentAuditStatus = null;
      activeSection.hidden = true;
      setFormState("ready");
      showFormMessage("This audit is not available in your current workshop session.");
      return true;
    }
    statusDescription.textContent = error.message || "Could not refresh. We'll try again shortly.";
  }
  return false;
}

async function showAudit(auditId) {
  if (!uuidPattern.test(auditId)) return;
  currentAuditId = auditId;
  currentAuditStatus = null;
  activeSection.hidden = false;
  activeHeading.textContent = "Loading your audit…";
  clearInterval(pollTimer);
  const isTerminal = await refreshAudit();
  if (!isTerminal && !pollTimer) pollTimer = setInterval(refreshAudit, 8000);
}

async function loadHistory() {
  const session = await currentSession(false);
  if (!session) return;
  const { data, error } = await supabase
    .from("audits")
    .select("id,company_name,status,created_at")
    .order("created_at", { ascending: false })
    .limit(20);
  if (error) {
    historyList.textContent = "History is temporarily unavailable. Your audits are still saved.";
    return;
  }
  historyList.replaceChildren();
  if (!data.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Your audits will appear here after your first run.";
    historyList.append(empty);
    return;
  }
  for (const audit of data) {
    const row = document.createElement("button");
    row.className = "history-item";
    row.type = "button";
    const title = document.createElement("span");
    title.className = "history-title";
    title.textContent = audit.company_name;
    const date = document.createElement("span");
    date.className = "history-date";
    date.textContent = formatDate(audit.created_at);
    const state = document.createElement("span");
    state.className = "history-state";
    state.textContent = audit.status;
    const arrow = document.createElement("span");
    arrow.className = "history-arrow";
    arrow.textContent = "↗";
    arrow.setAttribute("aria-hidden", "true");
    row.append(title, date, state, arrow);
    row.addEventListener("click", async () => {
      location.hash = `audit/${audit.id}`;
      await showAudit(audit.id);
    });
    historyList.append(row);
  }
}

async function initialize() {
  try {
    const response = await fetch("/config.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Workshop configuration is missing");
    config = await response.json();
    if (!config.supabase_url || !config.supabase_publishable_key || !config.api_url || !uuidPattern.test(config.workshop_id || "")) {
      throw new Error("Workshop configuration is incomplete");
    }
    const workshopSlug = new URLSearchParams(location.search).get("workshop");
    if (workshopSlug) {
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(workshopSlug)) throw new Error("Invalid workshop link");
      const workshopResponse = await fetch(`${config.api_url}/workshops/${encodeURIComponent(workshopSlug)}`, { cache: "no-store" });
      if (!workshopResponse.ok) throw new Error("This workshop link is not available");
      const workshop = await workshopResponse.json();
      if (!uuidPattern.test(workshop.id || "")) throw new Error("Invalid workshop configuration");
      config.workshop_id = workshop.id;
      document.querySelector(".issue-label").textContent = workshop.name;
    }
    supabase = createClient(config.supabase_url, config.supabase_publishable_key, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
    });
    storagePrefix = `competitive-visibility:${config.workshop_id}`;
    const pending = readStored("pending");
    if (pending) {
      restoreRequest(pending);
      setFormState("pending");
    }
    form.addEventListener("submit", submitAudit);
    document.querySelector("#copy-link").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(location.href);
        document.querySelector("#copy-link").textContent = "Copied ✓";
      } catch {
        document.querySelector("#copy-link").textContent = "Use address bar ↗";
      }
    });
    document.addEventListener("visibilitychange", refreshAudit);
    await loadHistory();
    const hashAuditId = auditIdFromHash();
    const savedAuditId = readStored("last-audit");
    const auditId = hashAuditId || savedAuditId;
    if (auditId && !pending) await showAudit(auditId);
    syncView();
  } catch (error) {
    fields.disabled = true;
    submitButton.disabled = true;
    showFormMessage(`This workshop is not ready yet: ${error.message}`);
  }
}

initialize();
