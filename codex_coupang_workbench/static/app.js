const state = {
  profiles: [],
  records: [],
  draftJobId: "",
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function checkHealth() {
  const dot = $("#status-dot");
  const text = $("#health-text");
  try {
    const health = await api("/api/health");
    dot.classList.toggle("ok", health.status === "ok");
    text.textContent = health.status === "ok" ? "backend ready" : "backend unknown";
  } catch (error) {
    dot.classList.remove("ok");
    text.textContent = "backend offline";
  }
}

async function loadSettings() {
  const settings = await api("/api/settings");
  const form = $("#settings-form");
  for (const [key, value] of Object.entries(settings)) {
    if (form.elements[key]) {
      form.elements[key].value = value;
    }
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const message = $("#settings-message");
  message.textContent = "saving...";
  await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify(formToObject(event.currentTarget)),
  });
  message.textContent = "saved";
  clearMessage(message);
}

async function saveProfile(event) {
  event.preventDefault();
  const message = $("#threads-profile-message");
  const payload = formToObject(event.currentTarget);
  payload.notes = "";
  message.textContent = "saving...";
  await api("/api/threads/profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  event.currentTarget.reset();
  await refreshProfiles();
  message.textContent = "saved";
  clearMessage(message);
}

async function connectProfile(profileKey) {
  const response = await api(`/api/threads/auth/start?profile_key=${encodeURIComponent(profileKey)}`);
  window.open(response.auth_url, "_blank", "noopener,noreferrer");
}

async function refreshProfileToken(profileKey) {
  await api(`/api/threads/profiles/${encodeURIComponent(profileKey)}/refresh`, { method: "POST" });
  await refreshProfiles();
}

async function generateDraft(event) {
  event.preventDefault();
  const message = $("#threads-draft-message");
  setBusy(true);
  try {
    message.textContent = "generating...";
    const draft = await api("/api/threads/draft", {
      method: "POST",
      body: JSON.stringify(formToObject(event.currentTarget)),
    });
    state.draftJobId = draft.job.id;
    $("#threads-preview").value = draft.text;
    $("#selected-product-label").textContent = draft.job.product_name || "selected product";
    message.textContent = "draft ready";
  } finally {
    setBusy(false);
    clearMessage(message);
  }
}

async function publishDraft() {
  const message = $("#threads-publish-message");
  const profileKey = $("#threads-profile-select").value;
  const text = $("#threads-preview").value.trim();
  if (!profileKey) {
    message.textContent = "프로필을 선택하세요.";
    return;
  }
  if (!state.draftJobId) {
    message.textContent = "먼저 글을 생성하세요.";
    return;
  }
  if (!text) {
    message.textContent = "발행할 글이 비어 있습니다.";
    return;
  }
  setBusy(true);
  try {
    message.textContent = "publishing...";
    const published = await api("/api/threads/publish", {
      method: "POST",
      body: JSON.stringify({
        profile_key: profileKey,
        job_id: state.draftJobId,
        text,
      }),
    });
    message.textContent = `published: ${published.threads_post_id}`;
    state.draftJobId = "";
    $("#threads-preview").value = "";
    $("#selected-product-label").textContent = "no product";
    await refreshRecords();
  } finally {
    setBusy(false);
  }
}

async function refreshProfiles() {
  state.profiles = await api("/api/threads/profiles");
  renderProfiles();
}

async function refreshRecords() {
  state.records = await api("/api/threads/publish-records");
  renderRecords();
}

async function refreshAll() {
  await Promise.all([refreshProfiles(), refreshRecords()]);
}

function renderProfiles() {
  $("#threads-profile-count").textContent = `${state.profiles.length} profiles`;
  const list = $("#threads-profiles-list");
  if (state.profiles.length === 0) {
    list.innerHTML = '<div class="empty-cell">No Threads profiles yet.</div>';
  } else {
    list.innerHTML = state.profiles
      .map((profile) => {
        const username = profile.username ? `@${profile.username}` : profile.profile_key;
        const status = profile.is_connected ? "connected" : "not connected";
        return `
          <div class="profile-row">
            <div>
              <strong>${escapeHtml(profile.display_name)}</strong>
              <span class="link-text">${escapeHtml(username)} · ${escapeHtml(status)}</span>
              ${profile.expires_at ? `<span class="link-text">token until ${escapeHtml(profile.expires_at)}</span>` : ""}
            </div>
            <div class="job-actions">
              <button class="small-button" type="button" data-action="connect" data-key="${escapeAttribute(profile.profile_key)}">Connect</button>
              ${
                profile.is_connected
                  ? `<button class="small-button" type="button" data-action="refresh-token" data-key="${escapeAttribute(profile.profile_key)}">Refresh Token</button>`
                  : ""
              }
            </div>
          </div>
        `;
      })
      .join("");
  }
  renderProfileOptions();
}

function renderProfileOptions() {
  const select = $("#threads-profile-select");
  const current = select.value;
  if (state.profiles.length === 0) {
    select.innerHTML = '<option value="">프로필 없음</option>';
    return;
  }
  select.innerHTML = state.profiles
    .map((profile) => {
      const suffix = profile.is_connected ? "" : " · 연결 필요";
      return `<option value="${escapeAttribute(profile.profile_key)}">${escapeHtml(profile.display_name)}${suffix}</option>`;
    })
    .join("");
  if (current && state.profiles.some((profile) => profile.profile_key === current)) {
    select.value = current;
  }
}

function renderRecords() {
  $("#record-count").textContent = `${state.records.length} records`;
  const body = $("#records-body");
  if (state.records.length === 0) {
    body.innerHTML = '<tr><td colspan="4" class="empty-cell">No publish records yet.</td></tr>';
    return;
  }
  body.innerHTML = state.records
    .map((record) => {
      const profileName = record.display_name || record.profile_key || "";
      const username = record.username ? `@${record.username}` : "";
      return `
        <tr>
          <td>${escapeHtml(record.threads_published_at || "")}</td>
          <td>
            <strong>${escapeHtml(record.product_name || "상품명 없음")}</strong>
            <span class="link-text">${escapeHtml(record.product_url || "")}</span>
          </td>
          <td>
            <strong>${escapeHtml(profileName)}</strong>
            ${username ? `<span class="link-text">${escapeHtml(username)}</span>` : ""}
          </td>
          <td><span class="link-text">${escapeHtml(record.threads_post_id || "")}</span></td>
        </tr>
      `;
    })
    .join("");
}

function setBusy(isBusy) {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

function clearMessage(element) {
  setTimeout(() => {
    element.textContent = "";
  }, 1800);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function bindEvents() {
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#threads-profile-form").addEventListener("submit", saveProfile);
  $("#threads-draft-form").addEventListener("submit", generateDraft);
  $("#threads-publish-button").addEventListener("click", publishDraft);
  $("#refresh-button").addEventListener("click", refreshAll);
  $("#threads-profiles-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "connect") {
      await connectProfile(button.dataset.key);
    }
    if (button.dataset.action === "refresh-token") {
      await refreshProfileToken(button.dataset.key);
    }
  });
}

async function init() {
  bindEvents();
  await checkHealth();
  await loadSettings();
  await refreshAll();
}

init().catch((error) => {
  console.error(error);
  $("#health-text").textContent = "startup error";
});
