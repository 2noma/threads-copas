const state = {
  profiles: [],
  records: [],
  draftJobId: "",
  draftImageUrl: "",
  productPreview: null,
  channelIds: [],
};

const $ = (selector) => document.querySelector(selector);
const APP_BASE_PATH = window.location.pathname.startsWith("/threads-copas") ? "/threads-copas" : "";
const DEFAULT_COUPANG_CHANNEL_IDS = ["bonggushop", "sinabroai", "sinabroinfo"];

async function api(path, options = {}) {
  const url = path.startsWith("/") ? `${APP_BASE_PATH}${path}` : path;
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    let message = detail || `HTTP ${response.status}`;
    try {
      message = JSON.parse(detail).detail || message;
    } catch (_error) {
      // Keep the raw response body when it is not JSON.
    }
    throw new Error(message);
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
  applySettingsToForm(settings, $("#settings-form"));
  syncCoupangChannelIds();
}

async function saveSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $("#settings-message");
  message.textContent = "saving...";
  const settings = await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify(formToObject(form)),
  });
  applySettingsToForm(settings, form);
  syncCoupangChannelIds();
  message.textContent = "saved";
  clearMessage(message);
}

function applySettingsToForm(settings, form) {
  for (const [key, value] of Object.entries(settings)) {
    if (form.elements[key]) {
      form.elements[key].value = value;
    }
  }
}

function parseChannelIds(value) {
  const channelIds = String(value ?? "")
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return [...new Set(channelIds)];
}

function syncCoupangChannelIds() {
  const field = $("#settings-form").elements.coupang_channel_ids;
  if (!field.value.trim()) {
    field.value = DEFAULT_COUPANG_CHANNEL_IDS.join("\n");
  }
  state.channelIds = parseChannelIds(field.value);
  renderCoupangChannelOptions();
}

function selectedCoupangChannelId() {
  const select = $("#coupang-channel-select");
  return select ? select.value.trim() : "";
}

async function connectProfile(profileKey) {
  const authWindow = window.open("about:blank", "_blank");
  if (authWindow) {
    authWindow.opener = null;
  }
  try {
    const response = await api(`/api/threads/auth/start?profile_key=${encodeURIComponent(profileKey)}`);
    if (authWindow) {
      authWindow.location.href = response.auth_url;
      waitForProfileConnection(profileKey, authWindow);
    } else {
      window.location.href = response.auth_url;
    }
  } catch (error) {
    console.error(error);
    if (authWindow) {
      authWindow.close();
    }
    $("#threads-profile-message").textContent = "Threads 연결을 시작하지 못했습니다.";
  }
}

async function importCurrentProfile() {
  const authWindow = window.open("about:blank", "_blank");
  if (authWindow) {
    authWindow.opener = null;
  }
  const message = $("#threads-profile-message");
  try {
    message.textContent = "Threads 인증을 여는 중...";
    const response = await api("/api/threads/auth/import/start");
    if (authWindow) {
      authWindow.location.href = response.auth_url;
      waitForProfilesChange(authWindow);
    } else {
      window.location.href = response.auth_url;
    }
  } catch (error) {
    console.error(error);
    if (authWindow) {
      authWindow.close();
    }
    message.textContent = "Threads 계정을 가져오지 못했습니다.";
  }
}

async function refreshProfileToken(profileKey) {
  await api(`/api/threads/profiles/${encodeURIComponent(profileKey)}/refresh`, { method: "POST" });
  await refreshProfiles();
}

async function disconnectProfile(profileKey) {
  const confirmed = window.confirm("이 Threads 프로필 연결을 해제할까요?");
  if (!confirmed) return;
  await api(`/api/threads/profiles/${encodeURIComponent(profileKey)}/disconnect`, { method: "POST" });
  await refreshProfiles();
}

async function previewCoupangProduct() {
  const form = $("#threads-draft-form");
  const message = $("#coupang-preview-message");
  const productUrl = form.elements.product_url.value.trim();
  const manualPartnerUrl = form.elements.partner_url.value.trim();
  state.productPreview = null;
  form.elements.image_url.value = "";
  renderProductPreview();
  if (!productUrl) {
    message.textContent = "쿠팡 URL을 입력하세요.";
    return;
  }
  setBusy(true);
  try {
    message.textContent = "상품 확인 중...";
    const preview = await api("/api/coupang/product-preview", {
      method: "POST",
      body: JSON.stringify({
        product_url: productUrl,
        product_name: form.elements.product_name.value.trim(),
        sub_id: selectedCoupangChannelId(),
      }),
    });
    state.productPreview = preview;
    form.elements.partner_url.value = manualPartnerUrl || preview.partner_url || "";
    form.elements.image_url.value = "";
    if (preview.product_name) {
      form.elements.product_name.value = preview.product_name;
    }
    renderProductPreview();
    $("#selected-product-label").textContent = preview.product_name || form.elements.product_name.value.trim() || "상품명 직접 입력 필요";
    if (preview.needs_product_name) {
      message.textContent = "딥링크 생성 완료. 상품명을 직접 입력하면 글을 만들 수 있습니다.";
    } else {
      message.textContent = "상품 확인 완료";
      clearMessage(message);
    }
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "상품을 확인하지 못했습니다.";
  } finally {
    setBusy(false);
  }
}

async function createCoupangDeeplink() {
  const form = $("#threads-draft-form");
  const message = $("#coupang-preview-message");
  const productUrl = form.elements.product_url.value.trim();
  if (!productUrl) {
    message.textContent = "쿠팡 URL을 입력하세요.";
    return;
  }
  setBusy(true);
  try {
    message.textContent = "딥링크 생성 중...";
    const deeplink = await api("/api/coupang/deeplink", {
      method: "POST",
      body: JSON.stringify({
        product_url: productUrl,
        sub_id: selectedCoupangChannelId(),
      }),
    });
    form.elements.partner_url.value = deeplink.partner_url || "";
    if (state.productPreview) {
      state.productPreview = {
        ...state.productPreview,
        partner_url: deeplink.partner_url || state.productPreview.partner_url,
        product_url: deeplink.product_url || state.productPreview.product_url,
        resolved_url: deeplink.resolved_url || state.productPreview.resolved_url,
        original_url: deeplink.original_url || state.productPreview.original_url,
      };
      renderProductPreview();
    }
    message.textContent = "딥링크 생성 완료";
    clearMessage(message);
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "딥링크를 만들지 못했습니다.";
  } finally {
    setBusy(false);
  }
}

async function uploadGeneratedHookImage() {
  const form = $("#threads-draft-form");
  const message = $("#threads-media-message");
  const imageBase64 = form.elements.generated_image_base64.value.trim();
  if (!imageBase64) {
    message.textContent = "Base64 이미지를 붙여넣으세요.";
    return;
  }
  setBusy(true);
  try {
    message.textContent = "이미지 URL 생성 중...";
    const uploaded = await api("/api/threads/media", {
      method: "POST",
      body: JSON.stringify({
        filename: "threads-hook-image.png",
        content_type: detectImageContentType(imageBase64),
        image_base64: imageBase64,
      }),
    });
    form.elements.hook_image_url.value = uploaded.image_url || "";
    state.draftJobId = "";
    state.draftImageUrl = "";
    renderThreadImagePreview(
      uploaded.image_url || "",
      form.elements.product_name.value.trim() || state.productPreview?.product_name || ""
    );
    message.textContent = "이미지 URL 준비 완료";
    clearMessage(message);
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "이미지 URL을 만들지 못했습니다.";
  } finally {
    setBusy(false);
  }
}

async function generateDraft(event) {
  event.preventDefault();
  const message = $("#threads-draft-message");
  const form = event.currentTarget;
  const productName = form.elements.product_name.value.trim();
  const partnerUrl = form.elements.partner_url.value.trim();
  if (!state.productPreview) {
    message.textContent = "먼저 상품 확인을 완료하세요.";
    if (!$("#product-name-fallback").hidden) {
      form.elements.product_name.focus();
    }
    return;
  }
  if (state.productPreview.needs_product_name && (!productName || !partnerUrl)) {
    message.textContent = "상품명을 입력하면 생성할 수 있습니다.";
    form.elements.product_name.focus();
    return;
  }
  if (!productName) {
    message.textContent = "확인된 상품명이 없습니다.";
    form.elements.product_name.focus();
    return;
  }
  setBusy(true);
  try {
    message.textContent = "generating...";
    const payload = formToObject(form);
    delete payload.generated_image_base64;
    const draft = await api("/api/threads/draft", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.draftJobId = draft.job.id;
    state.draftImageUrl = draft.publish_image_url || "";
    $("#threads-preview").value = draft.text;
    $("#threads-comment-preview").value = draft.comment_text || "";
    $("#selected-product-label").textContent = draft.job.product_name || "selected product";
    renderThreadImagePreview(state.draftImageUrl, draft.job.product_name || "");
    message.textContent = "draft ready";
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "글 생성에 실패했습니다.";
  } finally {
    setBusy(false);
  }
}

async function publishDraft() {
  const message = $("#threads-publish-message");
  const profileKey = $("#threads-profile-select").value;
  const text = $("#threads-preview").value.trim();
  const commentText = $("#threads-comment-preview").value.trim();
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
        comment_text: commentText,
      }),
    });
    message.textContent = `published: ${published.threads_post_id}`;
    state.draftJobId = "";
    state.draftImageUrl = "";
    $("#threads-preview").value = "";
    $("#threads-comment-preview").value = "";
    $("#selected-product-label").textContent = "no product";
    renderThreadImagePreview();
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

function renderProductPreview() {
  const container = $("#coupang-product-preview");
  const preview = state.productPreview;
  const fallback = $("#product-name-fallback");
  const form = $("#threads-draft-form");
  if (!preview) {
    container.hidden = true;
    container.innerHTML = "";
    fallback.hidden = true;
    form.elements.image_url.value = "";
    return;
  }
  const facts = Array.isArray(preview.facts) ? preview.facts.filter(Boolean) : [];
  const partnerUrl = form.elements.partner_url.value.trim() || preview.partner_url;
  const manualProductName = form.elements.product_name.value.trim();
  const displayProductName = preview.product_name || manualProductName || "상품명 직접 입력 필요";
  fallback.hidden = !preview.needs_product_name;
  $("#selected-product-label").textContent = displayProductName;
  container.hidden = false;
  container.innerHTML = `
    <div class="product-preview-thumb">
      ${
        preview.image_url
          ? `<img src="${escapeAttribute(preview.image_url)}" alt="${escapeAttribute(displayProductName || "쿠팡 상품")}" />`
          : '<div class="product-preview-placeholder">이미지 없음</div>'
      }
    </div>
    <div class="product-preview-info">
      <strong>${escapeHtml(displayProductName)}</strong>
      ${preview.product_id ? `<span class="link-text">상품 ID: ${escapeHtml(preview.product_id)}</span>` : ""}
      ${preview.item_id ? `<span class="link-text">Item ID: ${escapeHtml(preview.item_id)}</span>` : ""}
      ${facts.length ? `<span class="link-text">${facts.map(escapeHtml).join(" · ")}</span>` : ""}
      ${partnerUrl ? `<span class="link-text">${escapeHtml(partnerUrl)}</span>` : ""}
      ${
        preview.needs_product_name
          ? '<span class="link-text">딥링크는 생성됐습니다. 상품명을 직접 입력하면 바로 글을 만들 수 있습니다.</span>'
          : ""
      }
    </div>
  `;
}

function renderThreadImagePreview(imageUrl = "", productName = "") {
  const container = $("#threads-image-preview");
  const url = String(imageUrl || "").trim();
  container.classList.toggle("is-empty", !url);
  if (!url) {
    container.innerHTML = '<div class="thread-image-empty">이미지 없음 · 텍스트로만 발행</div>';
    return;
  }
  const alt = productName ? `${productName} 후킹 이미지` : "Threads 후킹 이미지";
  container.innerHTML = `
    <figure>
      <img src="${escapeAttribute(url)}" alt="${escapeAttribute(alt)}" />
      <figcaption>발행 이미지 · ${escapeHtml(url)}</figcaption>
    </figure>
  `;
}

function renderProfiles() {
  $("#threads-profile-count").textContent = `${state.profiles.length} profiles`;
  const list = $("#threads-profiles-list");
  if (state.profiles.length === 0) {
    list.innerHTML = '<div class="empty-cell">Import Current Account로 Threads 계정을 연결하세요.</div>';
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
                  ? `
                    <button class="small-button" type="button" data-action="refresh-token" data-key="${escapeAttribute(profile.profile_key)}">Refresh Token</button>
                    <button class="small-button" type="button" data-action="disconnect" data-key="${escapeAttribute(profile.profile_key)}">Disconnect</button>
                  `
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

function renderCoupangChannelOptions() {
  const select = $("#coupang-channel-select");
  if (!select) return;
  const current = select.value;
  if (state.channelIds.length === 0) {
    select.innerHTML = '<option value="">기본 Sub ID</option>';
    return;
  }
  select.innerHTML = state.channelIds
    .map((channelId) => `<option value="${escapeAttribute(channelId)}">${escapeHtml(channelId)}</option>`)
    .join("");
  if (current && state.channelIds.includes(current)) {
    select.value = current;
  } else {
    select.value = state.channelIds[0];
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

function detectImageContentType(imageBase64) {
  const rawValue = String(imageBase64).trim();
  const dataUrlMatch = rawValue.match(/^data:([^;,]+)[;,]/i);
  if (dataUrlMatch) {
    return dataUrlMatch[1].toLowerCase();
  }
  const compact = rawValue.replace(/\s/g, "");
  if (compact.startsWith("/9j/")) {
    return "image/jpeg";
  }
  if (compact.startsWith("UklGR")) {
    return "image/webp";
  }
  return "image/png";
}

function bindEvents() {
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#settings-form").elements.coupang_channel_ids.addEventListener("input", syncCoupangChannelIds);
  $("#threads-import-button").addEventListener("click", importCurrentProfile);
  $("#coupang-preview-button").addEventListener("click", previewCoupangProduct);
  $("#coupang-deeplink-button").addEventListener("click", createCoupangDeeplink);
  const draftForm = $("#threads-draft-form");
  draftForm.elements.product_url.addEventListener("input", () => {
    state.productPreview = null;
    state.draftJobId = "";
    state.draftImageUrl = "";
    $("#selected-product-label").textContent = "no product";
    $("#product-name-fallback").hidden = true;
    draftForm.elements.product_name.value = "";
    draftForm.elements.image_url.value = "";
    draftForm.elements.hook_image_url.value = "";
    draftForm.elements.generated_image_base64.value = "";
    draftForm.elements.partner_url.value = "";
    renderThreadImagePreview();
    renderProductPreview();
  });
  draftForm.elements.product_name.addEventListener("input", renderProductPreview);
  draftForm.elements.partner_url.addEventListener("input", renderProductPreview);
  draftForm.elements.hook_image_url.addEventListener("input", () => {
    state.draftJobId = "";
    state.draftImageUrl = "";
    renderThreadImagePreview(
      draftForm.elements.hook_image_url.value.trim(),
      draftForm.elements.product_name.value.trim() || state.productPreview?.product_name || ""
    );
  });
  draftForm.addEventListener("submit", generateDraft);
  $("#threads-media-upload-button").addEventListener("click", uploadGeneratedHookImage);
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
    if (button.dataset.action === "disconnect") {
      await disconnectProfile(button.dataset.key);
    }
  });
  window.addEventListener("focus", () => {
    refreshAll().catch((error) => console.error(error));
  });
}

function waitForProfileConnection(profileKey, authWindow) {
  let attempts = 0;
  const timer = setInterval(async () => {
    attempts += 1;
    if (attempts > 60 || authWindow.closed) {
      clearInterval(timer);
    }
    try {
      await refreshProfiles();
      const profile = state.profiles.find((item) => item.profile_key === profileKey);
      if (profile?.is_connected) {
        clearInterval(timer);
        $("#threads-profile-message").textContent = "Threads 연결 완료";
        clearMessage($("#threads-profile-message"));
      }
    } catch (error) {
      console.error(error);
    }
  }, 2000);
}

function waitForProfilesChange(authWindow) {
  const initialConnections = new Map(
    state.profiles.map((profile) => [profile.profile_key, profile.is_connected])
  );
  let attempts = 0;
  const timer = setInterval(async () => {
    attempts += 1;
    if (attempts > 60 || authWindow.closed) {
      clearInterval(timer);
    }
    try {
      await refreshProfiles();
      const imported = state.profiles.find(
        (profile) => profile.is_connected && initialConnections.get(profile.profile_key) !== true
      );
      if (imported) {
        clearInterval(timer);
        $("#threads-profile-message").textContent = `${imported.display_name} 가져오기 완료`;
        clearMessage($("#threads-profile-message"));
      }
    } catch (error) {
      console.error(error);
    }
  }, 2000);
}

async function init() {
  bindEvents();
  renderThreadImagePreview();
  await checkHealth();
  await loadSettings();
  await refreshAll();
}

init().catch((error) => {
  console.error(error);
  $("#health-text").textContent = "startup error";
});
