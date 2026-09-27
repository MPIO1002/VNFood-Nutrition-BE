const state = {
  file: null,
  previewUrl: null,
  result: null,
  modelReady: false,
  modelInfo: null,
};

const $ = (selector) => document.querySelector(selector);
const form = $("#analysisForm");
const fileInput = $("#imageInput");
const dropzone = $("#dropzone");
const analyzeButton = $("#analyzeButton");
const calibrationMode = $("#calibrationMode");
const calibrationValue = $("#calibrationValue");
const loadingOverlay = $("#loadingOverlay");
const resultsSection = $("#resultsSection");
const SVG_NS = "http://www.w3.org/2000/svg";
const BOX_COLORS = ["#ff7a45", "#c6e95d", "#5271ff", "#ffca58", "#e66bbb"];
const READINESS_LABELS = {
  candidate: "Sẵn sàng đánh giá",
  development: "Đang phát triển",
  training_incomplete: "Train chưa hoàn tất",
  smoke_test: "Chỉ là smoke test",
  class_mismatch: "Sai class map",
  unverified: "Chưa xác minh",
  unknown: "Chưa rõ trạng thái",
};
const BASIS_LABELS = {
  visual_metric_estimate: "Nhìn thấy + có tỷ lệ mét",
  visual_match: "Model nhìn thấy",
  catalog_prior: "Công thức mẫu",
  user_override: "Gram do người dùng sửa",
};
const PORTION_METHOD_LABELS = {
  single_image_serving_prior: "Khẩu phần mặc định từ một ảnh",
  liquid_or_mixed_dish_prior: "Khẩu phần mặc định cho món nước/hỗn hợp",
  mask_area_x_thickness_x_density: "Diện tích × độ dày giả định × mật độ",
  recipe_base_portion_prior: "Khẩu phần chuẩn trong công thức",
};
const ANALYSIS_BASIS_LABELS = {
  visual_components_plus_recipe_catalog: "Thành phần nhìn thấy + công thức mẫu",
  dish_detection_plus_recipe_catalog: "Tên món nhận diện + công thức mẫu",
};
const CALIBRATION_METHOD_LABELS = {
  detected_plate: "Tự tìm đĩa tròn",
  manual_scale: "Tỷ lệ cm/px nhập tay",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function number(value, digits = 1) {
  const parsed = Number(value || 0);
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(parsed);
}

function percent(value, digits = 1) {
  return `${number(Number(value || 0) * 100, digits)}%`;
}

function setMessage(message = "") {
  $("#formMessage").textContent = message;
}

function updateButton() {
  analyzeButton.disabled = !(state.file && state.modelReady);
}

async function loadRuntime() {
  const status = $("#runtimeStatus");
  const banner = $("#modelBanner");
  try {
    const healthResponse = await fetch("/health");
    const health = await healthResponse.json();
    if (!health.model_exists) {
      throw new Error("Chưa tìm thấy best.onnx/best.pt hoặc CALCUCALO_MODEL.");
    }
    const infoResponse = await fetch("/api/v1/model/info");
    const info = await infoResponse.json();
    if (!infoResponse.ok) throw new Error(info.detail || "Không đọc được metadata model.");

    state.modelReady = true;
    state.modelInfo = info;
    status.className = "runtime-status ready";
    status.querySelector("span:last-child").textContent =
      `${info.detector.model_file} · ${info.detector.class_count} lớp · ${info.detector.backend}`;

    const readiness = info.readiness || {};
    const training = info.detector.training || {};
    const metrics = info.detector.metrics || {};
    const completedEpochs = training.completed_epochs;
    const plannedEpochs = training.planned_epochs || training.epochs;
    const progress = completedEpochs && plannedEpochs
      ? `${completedEpochs}/${plannedEpochs}`
      : plannedEpochs || "—";
    const readinessStatus = readiness.status || "unknown";
    const readinessLabel = READINESS_LABELS[readinessStatus] || readinessStatus;
    const subtitle = readinessStatus === "training_incomplete"
      ? "Có thể thử inference, nhưng chưa coi là model cuối cùng."
      : readiness.detector_candidate
        ? "Detector đủ điều kiện để đánh giá sâu hơn; calories vẫn là ước tính."
        : "Hãy đọc cảnh báo trước khi dùng kết quả.";

    banner.hidden = false;
    banner.className = `model-banner ${readiness.detector_candidate ? "ok" : ""}`;
    banner.innerHTML = `
      <div class="model-summary">
        <div>
          <h2>${escapeHtml(info.detector.model_file)} · ${escapeHtml(info.detector.class_count)} lớp</h2>
          <p>${escapeHtml(subtitle)}</p>
        </div>
        <span class="model-status-pill">${escapeHtml(readinessLabel)}</span>
      </div>
      <div class="model-metrics">
        <div class="model-metric"><span>Tiến độ train</span><strong>${escapeHtml(progress)} epoch</strong></div>
        <div class="model-metric"><span>Dữ liệu train</span><strong>${training.fraction ? percent(training.fraction, 0) : "—"}</strong></div>
        <div class="model-metric"><span>Precision</span><strong>${metrics["metrics/precision(B)"] !== undefined ? percent(metrics["metrics/precision(B)"], 1) : "—"}</strong></div>
        <div class="model-metric"><span>Recall</span><strong>${metrics["metrics/recall(B)"] !== undefined ? percent(metrics["metrics/recall(B)"], 1) : "—"}</strong></div>
        <div class="model-metric"><span>mAP50–95</span><strong>${metrics["metrics/mAP50-95(B)"] !== undefined ? percent(metrics["metrics/mAP50-95(B)"], 1) : "—"}</strong></div>
      </div>
      ${(readiness.warnings || []).map((warning) => `<div class="model-warning">• ${escapeHtml(warning)}</div>`).join("")}`;
  } catch (error) {
    state.modelReady = false;
    state.modelInfo = null;
    status.className = "runtime-status error";
    status.querySelector("span:last-child").textContent = "Model chưa sẵn sàng";
    banner.hidden = false;
    banner.className = "model-banner error";
    banner.innerHTML = `<strong>Không thể khởi tạo model</strong><span>${escapeHtml(error.message)}</span>`;
  }
  updateButton();
}

function chooseFile(file) {
  setMessage();
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    setMessage("Vui lòng chọn một file ảnh JPG, PNG hoặc WebP.");
    return;
  }
  if (file.size > 15 * 1024 * 1024) {
    setMessage("Ảnh vượt quá giới hạn 15 MB.");
    return;
  }
  state.file = file;
  state.result = null;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(file);
  const previewImage = $("#previewImage");
  previewImage.onload = () => {
    const fileMeta = $("#fileMeta");
    fileMeta.hidden = false;
    fileMeta.innerHTML = `
      <span>${escapeHtml(file.type || "image")}</span>
      <span>${number(file.size / 1024 / 1024, 2)} MB</span>
      <span>${previewImage.naturalWidth} × ${previewImage.naturalHeight} px</span>`;
  };
  previewImage.src = state.previewUrl;
  $("#previewStage").hidden = false;
  $("#previewEmpty").hidden = true;
  $("#overlay").replaceChildren();
  $("#dropTitle").textContent = file.name;
  $("#dropHint").textContent = `${number(file.size / 1024 / 1024, 2)} MB · bấm để đổi ảnh`;
  $("#detectionCount").textContent = "Sẵn sàng phân tích";
  $("#jsonMessage").textContent = "Dùng khi tích hợp API hoặc kiểm tra calculation trace.";
  resultsSection.hidden = true;
  updateButton();
}

fileInput.addEventListener("change", () => chooseFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  });
});
dropzone.addEventListener("drop", (event) => chooseFile(event.dataTransfer.files[0]));

calibrationMode.addEventListener("change", () => {
  const mode = calibrationMode.value;
  const help = $("#calibrationHelp");
  calibrationValue.disabled = mode === "none";
  calibrationValue.value = "";
  if (mode === "plate") {
    $("#calibrationLabel").textContent = "Đường kính";
    $("#calibrationUnit").textContent = "cm";
    calibrationValue.placeholder = "25";
    help.textContent = "Nhập đường kính thật của đĩa. Hệ thống sẽ thử tìm hình tròn để quy đổi pixel sang cm.";
  } else if (mode === "scale") {
    $("#calibrationLabel").textContent = "Tỷ lệ";
    $("#calibrationUnit").textContent = "cm/px";
    calibrationValue.placeholder = "0.042";
    help.textContent = "Dùng khi bạn đã biết chính xác mỗi pixel tương ứng bao nhiêu cm.";
  } else {
    $("#calibrationLabel").textContent = "Giá trị";
    $("#calibrationUnit").textContent = "—";
    calibrationValue.placeholder = "";
    help.textContent = "Không hiệu chuẩn: gram dựa chủ yếu vào khẩu phần mẫu, không phải phép đo vật lý từ ảnh.";
  }
});

async function analyze(overrides = null) {
  if (!state.file) return;
  const mode = calibrationMode.value;
  if (mode !== "none" && !(Number(calibrationValue.value) > 0)) {
    setMessage("Hãy nhập giá trị hiệu chuẩn lớn hơn 0.");
    return;
  }

  setMessage();
  loadingOverlay.hidden = false;
  analyzeButton.disabled = true;
  const payload = new FormData();
  payload.append("image", state.file);
  payload.append("response_format", "full");
  if (mode === "plate") payload.append("plate_diameter_cm", calibrationValue.value);
  if (mode === "scale") payload.append("cm_per_pixel", calibrationValue.value);
  if (overrides && Object.keys(overrides).length) {
    payload.append("component_overrides_json", JSON.stringify(overrides));
  }

  try {
    const response = await fetch("/api/v1/food/analyze", { method: "POST", body: payload });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `API trả lỗi ${response.status}`);
    state.result = data;
    renderResult(data);
  } catch (error) {
    setMessage(error.message || "Không thể phân tích ảnh.");
  } finally {
    loadingOverlay.hidden = true;
    updateButton();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  analyze();
});

function drawBoxes(result) {
  const overlay = $("#overlay");
  overlay.replaceChildren();
  overlay.setAttribute("viewBox", `0 0 ${result.image.width} ${result.image.height}`);
  (result.items || []).forEach((item, index) => {
    const [x1, y1, x2, y2] = item.bbox_xyxy;
    const color = BOX_COLORS[index % BOX_COLORS.length];
    const group = document.createElementNS(SVG_NS, "g");
    const rectangle = document.createElementNS(SVG_NS, "rect");
    rectangle.setAttribute("x", x1);
    rectangle.setAttribute("y", y1);
    rectangle.setAttribute("width", Math.max(1, x2 - x1));
    rectangle.setAttribute("height", Math.max(1, y2 - y1));
    rectangle.setAttribute("fill", "none");
    rectangle.setAttribute("stroke", color);
    rectangle.setAttribute("stroke-width", Math.max(2, result.image.width / 300));
    rectangle.setAttribute("vector-effect", "non-scaling-stroke");

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", x1 + 4);
    label.setAttribute("y", Math.max(16, y1 - 5));
    label.setAttribute("fill", color);
    label.setAttribute("font-size", Math.max(12, result.image.width / 42));
    label.setAttribute("font-weight", "800");
    label.setAttribute("paint-order", "stroke");
    label.setAttribute("stroke", "#102219");
    label.setAttribute("stroke-width", "3");
    label.textContent = `${item.label} ${number(item.detection_confidence * 100, 0)}%`;
    group.append(rectangle, label);
    overlay.append(group);
  });
}

function aggregateTotals(foods) {
  return foods.reduce((totals, food) => {
    const item = food.estimated_totals || {};
    totals.calories_kcal += Number(item.calories_kcal || 0);
    totals.protein_g += Number(item.protein_g || 0);
    totals.fat_g += Number(item.fat_g || 0);
    totals.carb_g += Number(item.carb_g || 0);
    return totals;
  }, { calories_kcal: 0, protein_g: 0, fat_g: 0, carb_g: 0 });
}

function renderQuality(report = {}) {
  const issueLabels = {
    low_resolution: "độ phân giải thấp",
    likely_blurry: "ảnh có thể bị mờ",
    too_dark: "ảnh quá tối",
    too_bright: "ảnh quá sáng",
  };
  const status = report.status || "unknown";
  const badge = $("#qualityBadge");
  badge.className = `quality-badge ${status}`;
  badge.textContent = status === "good"
    ? `Ảnh tốt · ${number((report.score || 0) * 100, 0)}%`
    : `Nên kiểm tra ảnh · ${number((report.score || 0) * 100, 0)}%`;

  const signals = report.signals || {};
  const issueText = (report.issues || []).length
    ? `Phát hiện: ${(report.issues || []).map((issue) => issueLabels[issue] || issue).join(", ")}.`
    : "Không phát hiện vấn đề rõ ràng về sáng, nét hoặc độ phân giải.";
  $("#qualityPanel").innerHTML = `
    <div><h3>Chất lượng đầu vào</h3><p>${escapeHtml(issueText)}</p></div>
    <div class="quality-signals">
      <span class="signal-chip">${escapeHtml(signals.width_px)} × ${escapeHtml(signals.height_px)} px</span>
      <span class="signal-chip">Độ sáng ${escapeHtml(signals.brightness_mean)}</span>
      <span class="signal-chip">Độ nét ${escapeHtml(signals.blur_variance)}</span>
    </div>`;
}

function renderDetections(items = []) {
  const list = $("#detectionList");
  if (!items.length) {
    list.innerHTML = `<p class="measurement-note">Không có vùng nào vượt ngưỡng confidence. Hãy thử ảnh rõ hơn, gần hơn hoặc đổi góc chụp.</p>`;
    return;
  }

  list.innerHTML = items.map((item) => {
    const portion = item.portion || {};
    const range = portion.range_g || [];
    const portionMethod = PORTION_METHOD_LABELS[portion.method] || portion.method || "Chưa có";
    const confidence = Number(item.detection_confidence || 0);
    const relation = item.component_of ? ` · thành phần của ${item.component_of}` : "";
    const rangeText = range.length === 2
      ? `${number(range[0])}–${number(range[1])} g`
      : "chưa có khoảng";
    return `
      <div class="detection-row">
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <small>Lớp ${escapeHtml(item.class_id)}${escapeHtml(relation)} · ${escapeHtml(portionMethod)}</small>
          <small>Khẩu phần ${number(portion.weight_g)} g · khoảng ${escapeHtml(rangeText)}</small>
        </div>
        <span class="confidence ${confidence < 0.5 ? "review" : ""}">${percent(confidence, 0)}</span>
      </div>`;
  }).join("");
}

function renderMeasurement(result) {
  const calibration = result.calibration;
  const trace = result.calculation_trace || {};
  const methods = [...new Set((result.items || [])
    .map((item) => item.portion?.method)
    .filter(Boolean))]
    .map((method) => PORTION_METHOD_LABELS[method] || method)
    .join(", ") || "Chưa có";
  const calibrationLabel = calibration
    ? `${CALIBRATION_METHOD_LABELS[calibration.method] || calibration.method} (${number(calibration.cm_per_pixel, 6)} cm/px)`
    : "Không có";
  const metricScale = trace.metric_scale_available ? "Có" : "Không";
  const depth = trace.depth_measurement_available ? "Có" : "Không — đang giả định";

  $("#measurementPanel").innerHTML = `
    <div class="measurement-list">
      <div class="measurement-item"><span>Tỷ lệ kích thước thật</span><strong>${escapeHtml(metricScale)}</strong></div>
      <div class="measurement-item"><span>Hiệu chuẩn</span><strong>${escapeHtml(calibrationLabel)}</strong></div>
      <div class="measurement-item"><span>Chiều sâu trực tiếp</span><strong>${escapeHtml(depth)}</strong></div>
      <div class="measurement-item"><span>Cách tính gram</span><strong>${escapeHtml(methods)}</strong></div>
    </div>
    <p class="measurement-note">Gram là ước lượng, không phải số cân đo. Ảnh gần vuông góc từ trên xuống và có vật chuẩn sẽ giảm sai số phối cảnh.</p>`;
}

function renderFoods(foods) {
  const list = $("#foodList");
  if (!foods.length) {
    list.innerHTML = `<div class="model-banner"><strong>Chưa có món phù hợp</strong><span>Model có thể chưa nhận ra món hoặc catalog chưa có công thức tương ứng.</span></div>`;
    $("#correctionBar").hidden = true;
    return;
  }

  list.innerHTML = foods.map((food) => {
    const totals = food.estimated_totals || {};
    const analysisBasis = ANALYSIS_BASIS_LABELS[food.analysis_basis] || food.analysis_basis;
    const matched = Number(food.visual_components_matched || 0);
    const matchedInstances = Number(food.visual_instances_matched || 0);
    const componentCount = (food.estimated_components || []).length;
    const components = (food.estimated_components || []).map((component) => {
      const instances = Number(component.visual_instance_count || 0);
      const instanceText = instances > 0
        ? `<br><small>${instances} vùng nhìn thấy</small>`
        : "";
      return `
      <tr>
        <td><strong>${escapeHtml(component.name)}</strong><br><span class="basis ${escapeHtml(component.basis)}">${escapeHtml(BASIS_LABELS[component.basis] || component.basis)}</span>${instanceText}</td>
        <td><input class="component-grams" type="number" min="1" step="1"
          data-food-id="${escapeHtml(food.food_id)}"
          data-component-id="${escapeHtml(component.ingredient_id)}"
          value="${escapeHtml(component.estimated_g)}" aria-label="Gram của ${escapeHtml(component.name)}"></td>
        <td>${number(component.calories_kcal)} kcal</td>
        <td>${number(component.protein_g)} g</td>
      </tr>`;
    }).join("");
    return `
      <article class="food-card">
        <header class="food-card-header">
          <div>
            <h3>${escapeHtml(food.name)}</h3>
            <p>${escapeHtml(food.food_id)} · ${number(food.estimated_portion_g)} g · ${escapeHtml(analysisBasis)}</p>
            <p>Model khớp trực tiếp ${matched}/${componentCount} loại thành phần (${matchedInstances} vùng) · chất lượng catalog: ${escapeHtml(food.data_quality || "chưa ghi")}</p>
          </div>
          <div class="food-total"><strong>${number(totals.calories_kcal)} kcal</strong><span>Tổng ước tính</span></div>
        </header>
        <table class="component-table">
          <thead><tr><th>Thành phần / cơ sở</th><th>Khối lượng</th><th>Calories</th><th>Protein</th></tr></thead>
          <tbody>${components}</tbody>
        </table>
      </article>`;
  }).join("");
  $("#correctionBar").hidden = false;
}

function renderResult(result) {
  const foods = result.foods || [];
  const totals = aggregateTotals(foods);
  drawBoxes(result);
  renderDetections(result.items || []);
  renderMeasurement(result);
  $("#detectionCount").textContent = `${(result.items || []).length} vùng phát hiện`;
  $("#macroGrid").innerHTML = [
    ["Calories ước tính", totals.calories_kcal, "kcal"],
    ["Protein", totals.protein_g, "g"],
    ["Chất béo", totals.fat_g, "g"],
    ["Tinh bột", totals.carb_g, "g"],
  ].map(([label, value, unit]) => `
    <div class="macro-card"><span>${label}</span><strong>${number(value)}</strong><small>${unit}</small></div>`).join("");

  renderQuality(result.image_quality || {});
  const warnings = result.warnings || [];
  const warningPanel = $("#warningPanel");
  warningPanel.hidden = !warnings.length;
  warningPanel.innerHTML = warnings.length
    ? `<h3>Lưu ý trước khi dùng kết quả</h3><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
    : "";
  renderFoods(foods);
  $("#jsonOutput").textContent = JSON.stringify(result, null, 2);
  $("#jsonMessage").textContent = "JSON đã sẵn sàng để sao chép hoặc tải xuống.";
  resultsSection.hidden = false;
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("#recalculateButton").addEventListener("click", () => {
  const overrides = {};
  document.querySelectorAll(".component-grams").forEach((input) => {
    const grams = Number(input.value);
    if (!(grams > 0)) return;
    const foodId = input.dataset.foodId;
    overrides[foodId] ||= {};
    overrides[foodId][input.dataset.componentId] = grams;
  });
  analyze(overrides);
});

$("#newAnalysisButton").addEventListener("click", () => {
  form.reset();
  calibrationMode.dispatchEvent(new Event("change"));
  fileInput.value = "";
  state.file = null;
  state.result = null;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  $("#previewImage").removeAttribute("src");
  $("#previewStage").hidden = true;
  $("#previewEmpty").hidden = false;
  $("#overlay").replaceChildren();
  $("#dropTitle").textContent = "Kéo ảnh vào đây hoặc chọn file";
  $("#dropHint").textContent = "JPG, PNG, WebP · tối đa 15 MB";
  $("#detectionCount").textContent = "Chưa có ảnh";
  $("#fileMeta").hidden = true;
  $("#fileMeta").replaceChildren();
  resultsSection.hidden = true;
  setMessage("Đã xóa kết quả cũ. Hãy chọn ảnh mới.");
  updateButton();
  $("#workspace").scrollIntoView({ behavior: "smooth", block: "start" });
});

$("#copyJsonButton").addEventListener("click", async () => {
  if (!state.result) return;
  const json = JSON.stringify(state.result, null, 2);
  try {
    await navigator.clipboard.writeText(json);
    $("#jsonMessage").textContent = "Đã sao chép JSON vào clipboard.";
  } catch (_error) {
    const textarea = document.createElement("textarea");
    textarea.value = json;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    $("#jsonMessage").textContent = "Đã sao chép JSON bằng chế độ tương thích.";
  }
});

$("#downloadJsonButton").addEventListener("click", () => {
  if (!state.result) return;
  const blob = new Blob([JSON.stringify(state.result, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const timestamp = new Date().toISOString().replaceAll(":", "-").replace(".", "-");
  link.href = url;
  link.download = `calcucalo-analysis-${timestamp}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  $("#jsonMessage").textContent = "Đã tạo file JSON để tải xuống.";
});

loadRuntime();
