const storageKeys = {
  access: "vnfood_access_token",
  refresh: "vnfood_refresh_token",
  user: "vnfood_current_user",
  baseUrl: "vnfood_api_base_url",
};

const state = {
  accessToken: sessionStorage.getItem(storageKeys.access) || "",
  refreshToken: sessionStorage.getItem(storageKeys.refresh) || "",
  user: readStoredUser(),
  analysisJson: "{}",
  previewUrl: "",
};

const elements = {
  apiBase: document.querySelector("#api-base"),
  connectionPill: document.querySelector("#connection-pill"),
  connectionLabel: document.querySelector("#connection-label"),
  apiHealth: document.querySelector("#api-health"),
  apiHealthDetail: document.querySelector("#api-health-detail"),
  dbHealth: document.querySelector("#db-health"),
  dbHealthDetail: document.querySelector("#db-health-detail"),
  sessionHealth: document.querySelector("#session-health"),
  sessionHealthDetail: document.querySelector("#session-health-detail"),
  sessionAvatar: document.querySelector("#session-avatar"),
  sessionName: document.querySelector("#session-name"),
  sessionEmail: document.querySelector("#session-email"),
  accessTokenState: document.querySelector("#access-token-state"),
  refreshTokenState: document.querySelector("#refresh-token-state"),
  registerForm: document.querySelector("#register-form"),
  loginForm: document.querySelector("#login-form"),
  analyzeForm: document.querySelector("#analyze-form"),
  analyzeButton: document.querySelector("#analyze-button"),
  foodImage: document.querySelector("#food-image"),
  fileName: document.querySelector("#file-name"),
  containerType: document.querySelector("#container-type"),
  roundFields: document.querySelector("#round-fields"),
  boxFields: document.querySelector("#box-fields"),
  previewImage: document.querySelector("#preview-image"),
  overlayImage: document.querySelector("#overlay-image"),
  resultPreview: document.querySelector("#result-preview"),
  analysisResult: document.querySelector("#analysis-result"),
  analysisStatus: document.querySelector("#analysis-status"),
  requestLog: document.querySelector("#request-log"),
  toast: document.querySelector("#toast"),
};

let toastTimer;

function readStoredUser() {
  try {
    return JSON.parse(sessionStorage.getItem(storageKeys.user) || "null");
  } catch {
    return null;
  }
}

function apiBaseUrl() {
  return elements.apiBase.value.trim().replace(/\/$/, "");
}

function setInitialValues() {
  elements.apiBase.value = sessionStorage.getItem(storageKeys.baseUrl) || window.location.origin;
  const email = `manual-${Date.now()}@example.com`;
  const password = "Manual-Test-Password-123!";
  elements.registerForm.elements.email.value = email;
  elements.registerForm.elements.password.value = password;
  elements.loginForm.elements.email.value = email;
  elements.loginForm.elements.password.value = password;
}

function tokenLabel(token) {
  if (!token) return "Chưa có";
  if (token.length < 24) return "Đã lưu";
  return `${token.slice(0, 10)}…${token.slice(-6)}`;
}

function persistSession(payload) {
  state.accessToken = payload.access_token || "";
  state.refreshToken = payload.refresh_token || "";
  state.user = payload.user || null;

  sessionStorage.setItem(storageKeys.access, state.accessToken);
  sessionStorage.setItem(storageKeys.refresh, state.refreshToken);
  sessionStorage.setItem(storageKeys.user, JSON.stringify(state.user));
  renderSession();
}

function clearSession() {
  state.accessToken = "";
  state.refreshToken = "";
  state.user = null;
  sessionStorage.removeItem(storageKeys.access);
  sessionStorage.removeItem(storageKeys.refresh);
  sessionStorage.removeItem(storageKeys.user);
  renderSession();
}

function renderSession() {
  const user = state.user;
  const hasSession = Boolean(state.accessToken);
  elements.sessionHealth.textContent = hasSession ? "Đã có access token" : "Chưa đăng nhập";
  elements.sessionHealthDetail.textContent = hasSession
    ? user?.email || "Có thể gọi GET /me"
    : "Không có access token";
  elements.sessionName.textContent = user?.full_name || (hasSession ? "Phiên JWT" : "Chưa đăng nhập");
  elements.sessionEmail.textContent = user?.email || "Hãy đăng ký hoặc đăng nhập";
  elements.sessionAvatar.textContent = (user?.full_name || user?.email || "?").charAt(0).toUpperCase();
  elements.accessTokenState.textContent = tokenLabel(state.accessToken);
  elements.refreshTokenState.textContent = tokenLabel(state.refreshToken);
}

function showToast(message, isError = false) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("is-error", isError);
  elements.toast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 3200);
}

function formatError(error) {
  const detail = error?.payload?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return error?.message || "Request không thành công";
}

function redactPayload(value) {
  if (Array.isArray(value)) return value.map(redactPayload);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => {
      const normalized = key.toLowerCase();
      if (normalized.includes("token") || normalized.includes("password")) {
        return [key, "[redacted]"];
      }
      if (normalized === "visual_base64") {
        return [key, `[base64 image: ${String(item).length} chars]`];
      }
      return [key, redactPayload(item)];
    }),
  );
}

function addLog(method, path, response, elapsedMs, payload) {
  const empty = elements.requestLog.querySelector(".empty-log");
  if (empty) empty.remove();

  const entry = document.createElement("article");
  entry.className = "log-entry";
  entry.dataset.ok = String(response.ok);

  const methodNode = document.createElement("span");
  methodNode.className = "log-method";
  methodNode.textContent = method;

  const pathNode = document.createElement("code");
  pathNode.textContent = path;
  pathNode.title = JSON.stringify(redactPayload(payload));

  const metaNode = document.createElement("span");
  metaNode.className = "log-meta";
  metaNode.textContent = `${response.status} · ${Math.round(elapsedMs)} ms`;

  entry.append(methodNode, pathNode, metaNode);
  elements.requestLog.prepend(entry);

  while (elements.requestLog.children.length > 12) {
    elements.requestLog.lastElementChild.remove();
  }
}

async function apiRequest(path, options = {}) {
  const started = performance.now();
  const method = options.method || "GET";
  let response;
  let payload;

  try {
    response = await fetch(`${apiBaseUrl()}${path}`, options);
    const contentType = response.headers.get("content-type") || "";
    payload = contentType.includes("application/json") ? await response.json() : await response.text();
  } catch (error) {
    const networkResponse = { ok: false, status: "NETWORK" };
    addLog(method, path, networkResponse, performance.now() - started, { error: error.message });
    throw new Error(`Không thể kết nối tới ${apiBaseUrl()}`);
  }

  addLog(method, path, response, performance.now() - started, payload);
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function jsonOptions(body, token = "") {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return { method: "POST", headers, body: JSON.stringify(body) };
}

async function refreshHealth() {
  elements.connectionPill.dataset.state = "pending";
  elements.connectionLabel.textContent = "Đang kiểm tra API";
  elements.apiHealth.textContent = "Đang kiểm tra…";
  elements.dbHealth.textContent = "Đang kiểm tra…";

  const [apiResult, dbResult] = await Promise.allSettled([
    apiRequest("/health"),
    apiRequest("/api/v1/auth/health"),
  ]);

  if (apiResult.status === "fulfilled") {
    elements.apiHealth.textContent = "Hoạt động";
    elements.apiHealthDetail.textContent = apiResult.value.model_configured
      ? "API online · model configured"
      : "API online · chưa có best model";
  } else {
    elements.apiHealth.textContent = "Không kết nối";
    elements.apiHealthDetail.textContent = formatError(apiResult.reason);
  }

  if (dbResult.status === "fulfilled") {
    elements.dbHealth.textContent = "Có thể truy cập";
    elements.dbHealthDetail.textContent = "Neon database reachable";
  } else {
    elements.dbHealth.textContent = "Không kết nối";
    elements.dbHealthDetail.textContent = formatError(dbResult.reason);
  }

  const healthy = apiResult.status === "fulfilled" && dbResult.status === "fulfilled";
  elements.connectionPill.dataset.state = healthy ? "ok" : "error";
  elements.connectionLabel.textContent = healthy ? "API và DB sẵn sàng" : "Cần kiểm tra backend";
}

async function runButtonAction(button, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Đang xử lý…";
  try {
    await action();
  } catch (error) {
    showToast(formatError(error), true);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

elements.registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  await runButtonAction(button, async () => {
    const form = new FormData(elements.registerForm);
    const body = Object.fromEntries(form.entries());
    const payload = await apiRequest("/api/v1/auth/register", jsonOptions(body));
    persistSession(payload);
    elements.loginForm.elements.email.value = body.email;
    elements.loginForm.elements.password.value = body.password;
    showToast("Đăng ký thành công và đã lưu phiên JWT");
  });
});

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  await runButtonAction(button, async () => {
    const body = Object.fromEntries(new FormData(elements.loginForm).entries());
    const payload = await apiRequest("/api/v1/auth/login", jsonOptions(body));
    persistSession(payload);
    showToast("Đăng nhập thành công");
  });
});

document.querySelector("#load-me").addEventListener("click", async (event) => {
  await runButtonAction(event.currentTarget, async () => {
    if (!state.accessToken) throw new Error("Chưa có access token");
    const user = await apiRequest("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${state.accessToken}` },
    });
    state.user = user;
    sessionStorage.setItem(storageKeys.user, JSON.stringify(user));
    renderSession();
    showToast("Đã tải thông tin user hiện tại");
  });
});

document.querySelector("#refresh-token").addEventListener("click", async (event) => {
  await runButtonAction(event.currentTarget, async () => {
    if (!state.refreshToken) throw new Error("Chưa có refresh token");
    const payload = await apiRequest(
      "/api/v1/auth/refresh",
      jsonOptions({ refresh_token: state.refreshToken }),
    );
    persistSession(payload);
    showToast("Token đã được rotation thành công");
  });
});

document.querySelector("#logout").addEventListener("click", async (event) => {
  await runButtonAction(event.currentTarget, async () => {
    if (!state.refreshToken) throw new Error("Chưa có refresh token");
    await apiRequest("/api/v1/auth/logout", jsonOptions({ refresh_token: state.refreshToken }));
    clearSession();
    showToast("Đã logout và thu hồi refresh token");
  });
});

document.querySelector("#logout-all").addEventListener("click", async (event) => {
  await runButtonAction(event.currentTarget, async () => {
    if (!state.accessToken) throw new Error("Chưa có access token");
    await apiRequest("/api/v1/auth/logout-all", {
      method: "POST",
      headers: { Authorization: `Bearer ${state.accessToken}` },
    });
    clearSession();
    showToast("Đã thu hồi mọi refresh token của tài khoản");
  });
});

document.querySelector("#clear-session").addEventListener("click", () => {
  clearSession();
  showToast("Đã xóa token khỏi tab hiện tại");
});

elements.containerType.addEventListener("change", () => {
  const isBox = elements.containerType.value === "hop";
  elements.roundFields.classList.toggle("is-hidden", isBox);
  elements.boxFields.classList.toggle("is-hidden", !isBox);
});

elements.foodImage.addEventListener("change", () => {
  const [file] = elements.foodImage.files;
  if (!file) return;
  elements.fileName.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(file);
  elements.previewImage.src = state.previewUrl;
  elements.previewImage.hidden = false;
  elements.overlayImage.hidden = true;
  const placeholder = elements.resultPreview.querySelector("p");
  if (placeholder) placeholder.hidden = true;
});

elements.analyzeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runButtonAction(elements.analyzeButton, async () => {
    try {
      const [file] = elements.foodImage.files;
      if (!file) throw new Error("Hãy chọn ảnh món ăn");

      const form = new FormData();
      const values = new FormData(elements.analyzeForm);
      const containerType = String(values.get("container_type"));
      form.append("image", file);
      form.append("container_type", containerType);
      form.append("response_format", String(values.get("response_format")));

      if (containerType === "hop") {
        form.append("container_length_cm", String(values.get("container_length_cm")));
        form.append("container_width_cm", String(values.get("container_width_cm")));
      } else {
        const cmPerPixel = String(values.get("cm_per_pixel") || "").trim();
        if (cmPerPixel) {
          form.append("cm_per_pixel", cmPerPixel);
        } else {
          form.append("container_diameter_cm", String(values.get("container_diameter_cm")));
        }
      }

      elements.analysisStatus.textContent = "Đang chạy pipeline…";
      const payload = await apiRequest("/api/v1/food/analyze", { method: "POST", body: form });
      const displayPayload = { ...payload };
      const overlay = displayPayload.visual_base64;
      if (overlay) {
        delete displayPayload.visual_base64;
        elements.overlayImage.src = `data:image/jpeg;base64,${overlay}`;
        elements.overlayImage.hidden = false;
        elements.previewImage.hidden = true;
      }
      state.analysisJson = JSON.stringify(displayPayload, null, 2);
      elements.analysisResult.textContent = state.analysisJson;
      elements.analysisStatus.textContent = "Phân tích thành công";
      showToast("Pipeline đã trả kết quả");
    } catch (error) {
      elements.analysisStatus.textContent = "Request thất bại — xem log để kiểm tra";
      throw error;
    }
  });
});

document.querySelector("#copy-result").addEventListener("click", async () => {
  await navigator.clipboard.writeText(state.analysisJson);
  showToast("Đã copy JSON");
});

document.querySelector("#refresh-health").addEventListener("click", () => {
  refreshHealth().catch((error) => showToast(formatError(error), true));
});

document.querySelector("#clear-log").addEventListener("click", () => {
  elements.requestLog.replaceChildren();
  const empty = document.createElement("p");
  empty.className = "empty-log";
  empty.textContent = "Request mới sẽ xuất hiện ở đây. Token luôn được che khỏi log.";
  elements.requestLog.append(empty);
});

elements.apiBase.addEventListener("change", () => {
  sessionStorage.setItem(storageKeys.baseUrl, apiBaseUrl());
  refreshHealth().catch((error) => showToast(formatError(error), true));
});

setInitialValues();
renderSession();
refreshHealth().catch((error) => showToast(formatError(error), true));
