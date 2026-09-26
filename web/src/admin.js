import { createClient } from "@supabase/supabase-js";
import "./admin.css";

const $ = (selector) => document.querySelector(selector);
const loginView = $("#login-view");
const dashboardView = $("#dashboard-view");
const form = $("#workshop-form");
let config;
let supabase;
let session;
let data = { workspaces: [], workshops: [] };
let selectedId = null;

function message(target, value) {
  target.textContent = value || "";
  target.hidden = !value;
}

function localDate(value) {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function isoDate(value) {
  return value ? new Date(value).toISOString() : null;
}

function workshopState(workshop) {
  const now = Date.now();
  if (workshop.opens_at && new Date(workshop.opens_at).getTime() > now) return "UPCOMING";
  if (workshop.closes_at && new Date(workshop.closes_at).getTime() <= now) return "CLOSED";
  if (workshop.used_audits >= workshop.max_total_audits) return "FULL";
  return "OPEN";
}

async function api(path, options = {}) {
  const { data: authData, error: authError } = await supabase.auth.getSession();
  if (authError || !authData.session) throw new Error("Your organizer session has ended. Sign in again.");
  session = authData.session;
  const response = await fetch(`${config.api_url}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The server could not complete this request.");
  return body;
}

function renderList() {
  const list = $("#workshop-list");
  list.replaceChildren();
  if (!data.workshops.length) {
    const empty = document.createElement("p");
    empty.className = "rail-empty";
    empty.textContent = "No workshop yet. Create one to get a participant link.";
    list.append(empty);
    return;
  }
  for (const workshop of data.workshops) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `workshop-row${workshop.id === selectedId ? " selected" : ""}`;
    const title = document.createElement("strong");
    title.textContent = workshop.name;
    const details = document.createElement("span");
    details.textContent = `${workshopState(workshop)} · ${workshop.used_audits}/${workshop.max_total_audits} used`;
    button.append(title, details);
    button.addEventListener("click", () => selectWorkshop(workshop.id));
    list.append(button);
  }
}

function selectWorkshop(id) {
  selectedId = id;
  const workshop = data.workshops.find((row) => row.id === id);
  const creating = !workshop;
  $("#empty-editor").hidden = true;
  $("#editor").hidden = false;
  $("#editor-index").textContent = creating ? "NEW / WORKSHOP" : `EDIT / ${workshop.slug.toUpperCase()}`;
  $("#editor-title").textContent = creating ? "New workshop." : workshop.name;
  $("#editor-state").textContent = creating ? "DRAFT" : workshopState(workshop);
  $("#editor-state").dataset.state = creating ? "DRAFT" : workshopState(workshop);
  $("#workshop-metrics").hidden = creating;
  $("#participant-link-row").hidden = creating;
  $("#slug-field").hidden = !creating;
  $("#workspace-field").hidden = !creating;
  form.elements.namedItem("slug").disabled = !creating;
  form.elements.namedItem("workspace_id").disabled = !creating;
  form.reset();
  const workspaceSelect = form.elements.namedItem("workspace_id");
  workspaceSelect.replaceChildren();
  for (const workspace of data.workspaces) {
    const option = document.createElement("option");
    option.value = workspace.id;
    option.textContent = workspace.name;
    workspaceSelect.append(option);
  }
  if (workshop) {
    form.elements.namedItem("name").value = workshop.name;
    form.elements.namedItem("opens_at").value = localDate(workshop.opens_at);
    form.elements.namedItem("closes_at").value = localDate(workshop.closes_at);
    form.elements.namedItem("max_total_audits").value = workshop.max_total_audits;
    form.elements.namedItem("max_concurrent_audits").value = workshop.max_concurrent_audits;
    form.elements.namedItem("max_audits_per_user").value = workshop.max_audits_per_user;
    $("#metric-used").textContent = `${workshop.used_audits} / ${workshop.max_total_audits}`;
    $("#metric-remaining").textContent = `${Math.max(0, workshop.max_total_audits - workshop.used_audits)} available`;
    $("#metric-active").textContent = `${workshop.active_audits} / ${workshop.max_concurrent_audits}`;
    $("#metric-queued").textContent = `${workshop.queued_audits} waiting in queue`;
    $("#metric-completed").textContent = workshop.completed_audits;
    const link = `${location.origin}/?workshop=${encodeURIComponent(workshop.slug)}`;
    $("#participant-link").href = link;
    $("#participant-link").textContent = link;
  }
  renderList();
}

async function refresh() {
  message($("#dashboard-message"), "");
  try {
    data = await api("/admin/workshops");
    if (selectedId && data.workshops.some((workshop) => workshop.id === selectedId)) selectWorkshop(selectedId);
    else if (data.workshops.length) selectWorkshop(data.workshops[0].id);
    else selectWorkshop(null);
  } catch (error) {
    message($("#dashboard-message"), error.message);
    $("#editor").hidden = true;
    $("#empty-editor").hidden = false;
  }
}

async function showSession() {
  const { data: authData, error } = await supabase.auth.getSession();
  if (error) throw error;
  session = authData.session;
  loginView.hidden = Boolean(session);
  dashboardView.hidden = !session;
  $("#sign-out").hidden = !session;
  if (session) {
    $("#signed-in-as").textContent = session.user.email || "Google account";
    await refresh();
  }
}

async function saveWorkshop(event) {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = $("#save-workshop");
  button.disabled = true;
  message($("#dashboard-message"), "");
  try {
    const values = new FormData(form);
    const settings = {
      name: String(values.get("name") || "").trim(),
      opens_at: isoDate(values.get("opens_at")),
      closes_at: isoDate(values.get("closes_at")),
      max_total_audits: Number(values.get("max_total_audits")),
      max_concurrent_audits: Number(values.get("max_concurrent_audits")),
      max_audits_per_user: Number(values.get("max_audits_per_user")),
    };
    if (settings.opens_at && settings.closes_at && settings.opens_at >= settings.closes_at) {
      throw new Error("Closing time must be after opening time.");
    }
    const response = selectedId
      ? await api(`/admin/workshops/${selectedId}`, { method: "PATCH", body: JSON.stringify(settings) })
      : await api("/admin/workshops", {
          method: "POST",
          body: JSON.stringify({
            ...settings,
            slug: String(values.get("slug") || "").trim(),
            workspace_id: values.get("workspace_id"),
          }),
        });
    selectedId = response.id;
    await refresh();
    message($("#dashboard-message"), "Saved. Participant links and new admissions now use these settings.");
  } catch (error) {
    message($("#dashboard-message"), error.message);
  } finally {
    button.disabled = false;
  }
}

async function initialize() {
  try {
    const response = await fetch("/config.json", { cache: "no-store" });
    if (!response.ok) throw new Error("App configuration is missing.");
    config = await response.json();
    if (!config.api_url || !config.supabase_url || !config.supabase_publishable_key) {
      throw new Error("Organizer configuration is incomplete.");
    }
    supabase = createClient(config.supabase_url, config.supabase_publishable_key, {
      auth: {
        storageKey: "competitive-visibility-organizer-auth",
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
    $("#google-sign-in").addEventListener("click", async () => {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${location.origin}/admin` },
      });
      if (error) message($("#login-message"), error.message);
    });
    $("#sign-out").addEventListener("click", async () => {
      await supabase.auth.signOut();
      session = null;
      loginView.hidden = false;
      dashboardView.hidden = true;
      $("#sign-out").hidden = true;
    });
    $("#refresh").addEventListener("click", refresh);
    $("#new-workshop").addEventListener("click", () => selectWorkshop(null));
    $("#copy-participant-link").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("#participant-link").href);
        $("#copy-participant-link").textContent = "Copied ✓";
      } catch {
        $("#copy-participant-link").textContent = "Copy from link ↗";
      }
    });
    form.addEventListener("submit", saveWorkshop);
    await showSession();
  } catch (error) {
    message($("#login-message"), error.message);
  }
}

initialize();
