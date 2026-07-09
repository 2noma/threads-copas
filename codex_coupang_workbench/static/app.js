const state = {
  profiles: [],
  records: [],
  draftJobId: "",
  draftImageUrl: "",
  hookImageVariant: 0,
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
    populateCodexPrompts({ silent: true });
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

async function previewCoupangProductWithChrome() {
  const form = $("#threads-draft-form");
  const message = $("#coupang-preview-message");
  const productUrl = form.elements.product_url.value.trim();
  if (!productUrl) {
    message.textContent = "쿠팡 URL을 입력하세요.";
    return;
  }
  setBusy(true);
  try {
    message.textContent = "로컬 Chrome에서 상품명 확인 중...";
    const context = await api("/api/coupang/chrome-product-context", {
      method: "POST",
      body: JSON.stringify({
        product_url: productUrl,
      }),
    });
    if (context.product_name) {
      form.elements.product_name.value = context.product_name;
      $("#selected-product-label").textContent = context.product_name;
    }
    message.textContent = "Chrome 확인 완료. 딥링크 생성 중...";
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "Chrome에서 상품명을 확인하지 못했습니다.";
    return;
  } finally {
    setBusy(false);
  }
  await previewCoupangProduct();
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
  if (shouldSkipHookImage(form)) {
    message.textContent = "이미지 없이 글만 만들기가 켜져 있습니다.";
    return;
  }
  const imageBase64 = form.elements.generated_image_base64.value.trim();
  if (!imageBase64) {
    message.textContent = "Base64 이미지를 붙여넣으세요.";
    return;
  }
  setBusy(true);
  try {
    message.textContent = "이미지 URL 생성 중...";
    await uploadHookImageBase64(form, imageBase64);
    message.textContent = "이미지 URL 준비 완료";
    clearMessage(message);
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "이미지 URL을 만들지 못했습니다.";
  } finally {
    setBusy(false);
  }
}

async function uploadHookImageBase64(form, imageBase64) {
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
  return uploaded.image_url || "";
}

async function ensureHookImageForDraft(form) {
  if (shouldSkipHookImage(form)) {
    clearHookImageForTextOnly(form);
    const message = $("#threads-media-message");
    message.textContent = "이미지 없이 글만 생성합니다.";
    clearMessage(message);
    return "";
  }
  const existingImageUrl = form.elements.hook_image_url.value.trim();
  if (existingImageUrl) {
    return existingImageUrl;
  }
  const message = $("#threads-media-message");
  const imageBase64 = form.elements.generated_image_base64.value.trim();
  if (imageBase64) {
    message.textContent = "붙여넣은 이미지 업로드 중...";
    return uploadHookImageBase64(form, imageBase64);
  }
  return generateAutoHookImage(form);
}

function productFactsForHookImage() {
  return Array.isArray(state.productPreview?.facts) ? state.productPreview.facts : [];
}

function productPromptContext() {
  const form = $("#threads-draft-form");
  const productName = form.elements.product_name.value.trim() || state.productPreview?.product_name || "";
  const productUrl = form.elements.partner_url.value.trim() || form.elements.product_url.value.trim();
  const facts = productFactsForHookImage().filter(Boolean).slice(0, 6);
  const factLines = facts.length ? facts.map((fact) => `- ${fact}`).join("\n") : "- 자동 수집된 상세 정보 없음";
  return { form, productName, productUrl, factLines };
}

async function generateAutoHookImage(form, options = {}) {
  const message = $("#threads-media-message");
  const productName = form.elements.product_name.value.trim() || state.productPreview?.product_name || "";
  if (!productName) {
    throw new Error("상품명을 확인한 뒤 후킹 이미지를 만들 수 있습니다.");
  }
  syncImagePromptVariant(form);
  message.textContent = options.status || "Codex로 AI 일러스트 후킹 이미지 생성 중... 몇 분 정도 걸릴 수 있습니다.";
  const generated = await api("/api/threads/auto-hook-image", {
    method: "POST",
    body: JSON.stringify({
      product_url: form.elements.product_url.value.trim(),
      product_name: productName,
      facts: productFactsForHookImage(),
      variant: state.hookImageVariant,
      prompt: form.elements.codex_image_prompt.value.trim(),
    }),
  });
  form.elements.hook_image_url.value = generated.image_url || "";
  state.draftJobId = "";
  state.draftImageUrl = "";
  renderThreadImagePreview(generated.image_url || "", productName);
  message.textContent = "후킹 이미지 준비 완료";
  clearMessage(message);
  return generated.image_url || "";
}

function syncImagePromptVariant(form) {
  const prompt = form.elements.codex_image_prompt.value.trim();
  if (!prompt) return;
  const seedLine = `- variation seed: ${state.hookImageVariant}`;
  form.elements.codex_image_prompt.value = /^- variation seed: \d+$/m.test(prompt)
    ? prompt.replace(/^- variation seed: \d+$/m, seedLine)
    : `${prompt}\n${seedLine}`;
}

async function regenerateHookImage() {
  const form = $("#threads-draft-form");
  const message = $("#threads-media-message");
  if (shouldSkipHookImage(form)) {
    message.textContent = "이미지 생성을 켠 뒤 다시 만들 수 있습니다.";
    return;
  }
  if (!state.productPreview) {
    message.textContent = "먼저 상품 확인을 완료하세요.";
    return;
  }
  const previousVariant = state.hookImageVariant;
  const previousImageUrl = form.elements.hook_image_url.value;
  state.hookImageVariant = previousVariant + 1;
  form.elements.hook_image_url.value = "";
  form.elements.generated_image_base64.value = "";
  renderThreadImagePreview();
  setBusy(true);
  try {
    await generateAutoHookImage(form, { status: "Codex로 AI 일러스트 이미지 다시 생성 중... 몇 분 정도 걸릴 수 있습니다." });
  } catch (error) {
    console.error(error);
    state.hookImageVariant = previousVariant;
    form.elements.hook_image_url.value = previousImageUrl;
    renderThreadImagePreview(
      previousImageUrl,
      form.elements.product_name.value.trim() || state.productPreview?.product_name || ""
    );
    message.textContent = error.message || "후킹 이미지를 다시 만들지 못했습니다.";
  } finally {
    setBusy(false);
  }
}

function shouldSkipHookImage(form) {
  return Boolean(form.elements.skip_hook_image?.checked);
}

function clearHookImageForTextOnly(form) {
  form.elements.hook_image_url.value = "";
  form.elements.generated_image_base64.value = "";
  state.draftJobId = "";
  state.draftImageUrl = "";
  renderThreadImagePreview();
}

function createCodexThreadsPrompt(options = {}) {
  const { form, productName, productUrl, factLines } = productPromptContext();
  const message = $("#codex-threads-prompt-message");
  if (!state.productPreview || !productName) {
    if (!options.silent) message.textContent = "먼저 상품 확인을 완료하세요.";
    return false;
  }
  form.elements.codex_threads_prompt.value = [
    "Codex CLI에 로그인된 계정 인증을 사용해 쿠팡 파트너스 Threads 게시글을 작성해줘.",
    "최종 답변에는 게시글 본문만 출력해. 설명, 마크다운 코드블록, 주석은 쓰지 마.",
    "",
    "스타일:",
    "- 상품 설명이 아니라 사람들이 멈칫하고 댓글을 열어보고 싶게 만드는 Threads 본문",
    "- 짧은 문장과 짧은 문단, 살짝 찝찝하거나 궁금한 상황 후킹",
    "- 방금 본 예시처럼 '이거 뭐지?', '왜 신경 쓰이지?' 느낌",
    "- 작성자 톤: 친근하고 실사용 관점이 있는 한국어 Threads 작성자",
    "",
    "반드시 지킬 것:",
    "- 링크와 고지 문구는 본문에 쓰지 마. 링크와 고지는 별도 댓글에 들어간다.",
    "- '자세한 건 댓글에 남겨둘게요' 같은 댓글 안내 문장 쓰지 않기",
    "- 해시태그 쓰지 않기",
    "- 가격, 할인율, 배송일, 재고, 리뷰 수는 쓰지 않기",
    "- 입력에 없는 효과, 인증, 성능, 호환 모델은 지어내지 않기",
    "- bullet 목록 금지",
    "- 상품명은 본문에 직접 쓰지 마. 브랜드명, 모델명, 정확한 상품명 노출 금지",
    "- 상품 카테고리와 사용 상황만 암시하기",
    "- 설명문처럼 쓰지 마. 사양, 구성, 장점 나열 금지",
    "- 구매 전 같은 표현 쓰지 마. '확인해보세요', '추천', '필요한 분', '비교해볼 만' 같은 문구도 쓰지 마",
    "- 사람들이 해당 상품이 뭔지 궁금해지게 작성하기",
    "- 2~4개 짧은 문단, 280자 이내",
    "- 질문, 의외의 순간, 한 번 신경 쓰이면 계속 거슬리는 감정 중 하나를 반드시 넣기",
    "",
    `내부 참고용 상품명: ${productName}`,
    `쿠팡 URL: ${productUrl}`,
    "상품 정보:",
    factLines,
    "사용자 메모: 없음",
  ].join("\n");
  if (!options.silent) {
    message.textContent = "본문 프롬프트 준비 완료";
    clearMessage(message);
  }
  return true;
}

function createCodexImagePrompt(options = {}) {
  const { form, productName, productUrl, factLines } = productPromptContext();
  const message = $("#codex-image-prompt-message");
  if (!state.productPreview || !productName) {
    if (!options.silent) message.textContent = "먼저 상품 확인을 완료하세요.";
    return false;
  }
  form.elements.codex_image_prompt.value = [
    "Use the image generation tool to create one Threads hook image.",
    "Save the generated bitmap as output.png in the current directory.",
    "Do not draw the image with code. Do not use stock image search. Use image generation.",
    "",
    "Goal:",
    "- 상품명을 보고 카테고리와 사용 상황을 추론한다.",
    "- 상품 카테고리를 자연스럽게 사용하는 장면을 만든다.",
    "- AI 일러스트임이 분명한 non-photorealistic hook image를 만든다.",
    "- fictional stylized characters only. 실제 인물처럼 보이지 않게 만든다.",
    "- 1:1 square composition suitable for Threads preview.",
    "",
    "Must avoid:",
    "- 실제 쿠팡 상품 이미지, 포장, 박스, 쇼핑앱 화면",
    "- 브랜드명, 로고, readable text, 가격표, 워터마크",
    "- 제품을 광고처럼 정면 배치한 카탈로그 컷",
    "- 실사, 사진, 실제 인플루언서/사용 후기처럼 보이는 연출",
    "- 입력에 없는 효능이나 성능을 암시하는 장면",
    "- No text in the image. 앱이 업로드 전에 AI 일러스트 라벨을 직접 추가한다.",
    "",
    "Creative direction:",
    "- 현대적인 에디토리얼 일러스트, semi-flat digital painting, soft shading",
    "- 사람이나 생활 공간 중심의 자연스러운 사용 장면",
    "- 상품 자체가 특정 브랜드처럼 보이지 않게 일반적인 카테고리 소품으로만 표현",
    "- 사용자가 '이 상황 뭐지?' 하고 댓글을 열어보고 싶을 정도의 생활감",
    "- 안전하고 일상적인 장면, 과장되더라도 성능 주장처럼 보이지 않게",
    `- variation seed: ${state.hookImageVariant}`,
    "",
    `상품명: ${productName}`,
    `상품 URL: ${productUrl}`,
    "상품 정보:",
    factLines,
  ].join("\n");
  if (!options.silent) {
    message.textContent = "이미지 프롬프트 준비 완료";
    clearMessage(message);
  }
  return true;
}

function populateCodexPrompts(options = {}) {
  createCodexThreadsPrompt(options);
  createCodexImagePrompt(options);
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
    message.textContent = shouldSkipHookImage(form) ? "텍스트 초안 생성 중..." : "이미지 준비 중...";
    await ensureHookImageForDraft(form);
    message.textContent = "generating...";
    const payload = formToObject(form);
    delete payload.generated_image_base64;
    delete payload.codex_image_prompt;
    payload.skip_hook_image = shouldSkipHookImage(form);
    if (payload.skip_hook_image) {
      payload.hook_image_url = "";
      payload.image_url = "";
    }
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

async function refreshRecordInsights(jobId) {
  const message = $("#threads-publish-message");
  if (!jobId) return;
  setBusy(true);
  try {
    message.textContent = "지표 새로고침 중...";
    const updated = await api(`/api/threads/publish-records/${encodeURIComponent(jobId)}/insights`, {
      method: "POST",
    });
    state.records = state.records.map((record) => (record.job_id === updated.job_id ? updated : record));
    renderRecords();
    message.textContent = "지표 업데이트 완료";
    clearMessage(message);
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "지표를 가져오지 못했습니다.";
  } finally {
    setBusy(false);
  }
}

async function deletePublishRecord(jobId, productName) {
  const message = $("#threads-publish-message");
  if (!jobId) return;
  const label = productName || "이 발행 기록";
  if (!window.confirm(`${label} 기록을 DB에서 삭제할까요?`)) return;
  setBusy(true);
  try {
    message.textContent = "발행 기록 삭제 중...";
    await api(`/api/threads/publish-records/${encodeURIComponent(jobId)}`, {
      method: "DELETE",
    });
    state.records = state.records.filter((record) => record.job_id !== jobId);
    renderRecords();
    message.textContent = "발행 기록을 삭제했습니다.";
    clearMessage(message);
  } catch (error) {
    console.error(error);
    message.textContent = error.message || "발행 기록을 삭제하지 못했습니다.";
  } finally {
    setBusy(false);
  }
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
    body.innerHTML = '<tr><td colspan="11" class="empty-cell">No publish records yet.</td></tr>';
    return;
  }
  body.innerHTML = state.records
    .map((record) => {
      const profileName = record.display_name || record.profile_key || "";
      const username = record.username ? `@${record.username}` : "";
      const insightsAt = record.threads_insights_at ? `갱신 ${record.threads_insights_at}` : "지표 미갱신";
      const insightsError = record.threads_insights_error || "";
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
          <td>${formatMetric(record.threads_views)}</td>
          <td>${formatMetric(record.threads_likes)}</td>
          <td>${formatMetric(record.threads_replies)}</td>
          <td>${formatMetric(record.threads_reposts)}</td>
          <td>${formatMetric(record.threads_quotes)}</td>
          <td>${formatMetric(record.threads_shares)}</td>
          <td>
            <button class="small-button" type="button" data-action="refresh-insights" data-job-id="${escapeAttribute(record.job_id || "")}">지표 새로고침</button>
            <button class="small-button danger-button" type="button" data-action="delete-record" data-job-id="${escapeAttribute(record.job_id || "")}" data-product-name="${escapeAttribute(record.product_name || "")}">삭제</button>
            <span class="link-text">${escapeHtml(insightsAt)}</span>
            ${insightsError ? `<span class="link-text">${escapeHtml(insightsError)}</span>` : ""}
          </td>
        </tr>
      `;
    })
    .join("");
}

function formatMetric(value) {
  const number = Number.parseInt(value, 10);
  if (!Number.isFinite(number)) return "0";
  return number.toLocaleString("ko-KR");
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
  $("#coupang-chrome-preview-button").addEventListener("click", previewCoupangProductWithChrome);
  $("#coupang-deeplink-button").addEventListener("click", createCoupangDeeplink);
  const draftForm = $("#threads-draft-form");
  draftForm.elements.product_url.addEventListener("input", () => {
    state.productPreview = null;
    state.draftJobId = "";
    state.draftImageUrl = "";
    state.hookImageVariant = 0;
    $("#selected-product-label").textContent = "no product";
    $("#product-name-fallback").hidden = true;
    draftForm.elements.product_name.value = "";
    draftForm.elements.image_url.value = "";
    draftForm.elements.hook_image_url.value = "";
    draftForm.elements.generated_image_base64.value = "";
    draftForm.elements.codex_threads_prompt.value = "";
    draftForm.elements.codex_image_prompt.value = "";
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
  draftForm.elements.skip_hook_image.addEventListener("change", () => {
    const message = $("#threads-media-message");
    if (shouldSkipHookImage(draftForm)) {
      clearHookImageForTextOnly(draftForm);
      message.textContent = "이미지 없이 글만 생성합니다.";
    } else {
      message.textContent = "이미지 생성을 다시 사용할 수 있습니다.";
    }
    clearMessage(message);
  });
  draftForm.addEventListener("submit", generateDraft);
  $("#codex-threads-prompt-button").addEventListener("click", createCodexThreadsPrompt);
  $("#codex-image-prompt-button").addEventListener("click", createCodexImagePrompt);
  $("#threads-media-upload-button").addEventListener("click", uploadGeneratedHookImage);
  $("#threads-auto-image-button").addEventListener("click", regenerateHookImage);
  $("#threads-publish-button").addEventListener("click", publishDraft);
  $("#refresh-button").addEventListener("click", refreshAll);
  $("#records-body").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "refresh-insights") {
      await refreshRecordInsights(button.dataset.jobId || "");
    }
    if (button.dataset.action === "delete-record") {
      await deletePublishRecord(button.dataset.jobId || "", button.dataset.productName || "");
    }
  });
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
