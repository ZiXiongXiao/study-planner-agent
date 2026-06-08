const modelOptions = {
  minimax: ["m3", "m2.7"],
  kimi: ["kimi-k2.6", "kimi-k2", "kimi-lite"],
  deepseek: ["deepseek-v4-flash", "deepseek-v4", "deepseek-coder"],
};

const modelLabels = {
  m3: "MiniMax-M3",
  "m2.7": "MiniMax-M2.7",
  "kimi-k2.6": "Kimi k2.6",
  "kimi-k2": "Kimi k2",
  "kimi-lite": "Kimi Lite",
  "deepseek-v4-flash": "DeepSeek V4 Flash",
  "deepseek-v4": "DeepSeek V4",
  "deepseek-coder": "DeepSeek Coder",
};

const knownImageModels = new Set(["m3", "image-01"]);
const runPhases = ["准备运行", "画像与记忆", "资源搜索", "资源评估", "知识整理", "计划生成", "多模态展示"];
const splitStorageKey = "studyPlannerSplit";
const themeStorageKey = "studyPlannerTheme";
const canvasStyleStorageKey = "studyPlannerCanvasStyle";
const defaultGoalPlaceholder = "例如：我今年 30 岁，想在 6 周内系统入门股票投资，目标不是短线暴富，而是建立长期投资框架。";

let currentSession = null;
let latestPlanId = null;
let latestSaved = null;
let previewAssetContext = "session";
let planCache = new Map();
let statusSource = null;
let clarifyState = { active: false, questions: [], answers: {}, index: 0 };
let isDraftReady = false;
let currentThemeChoice = "system";
let currentCanvasStyle = "grid";

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || "请求失败");
  return data;
}

function setStatus(text, step = "") {
  $("runStatus").textContent = text;
  document.querySelectorAll("#stepRail span").forEach((el) => {
    el.classList.toggle("active", el.textContent === step);
  });
}

function setBusy(isBusy) {
  $("composerSubmitBtn").disabled = isBusy;
  $("goalInput").disabled = isBusy;
  const saveBtn = $("saveBtn");
  if (saveBtn) saveBtn.disabled = isBusy || !isDraftReady;
}

function addBubble(role, content) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  el.textContent = content;
  $("chatLog").appendChild(el);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
}

function showError(err) {
  const message = err instanceof Error ? err.message : String(err || "请求失败");
  setStatus(`出错：${message}`, "草稿");
  $("agentStatusPanel").classList.remove("hidden");
  $("agentStatusLabel").textContent = "出错";
  addAgentLogBubble(`ERROR: ${message}`);
  addBubble("assistant", `运行出错：${message}`);
}

function providerChanged() {
  const provider = $("providerSelect").value;
  const select = $("modelSelect");
  const previous = select.value;
  select.innerHTML = "";
  for (const model of modelOptions[provider] || []) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    select.appendChild(option);
  }
  if ([...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
  renderModelList();
}

function renderModelList() {
  const list = $("modelList");
  const select = $("modelSelect");
  if (!list || !select) return;
  const active = select.value;
  list.innerHTML = "";
  [...select.options].forEach((option) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "model-row" + (option.value === active ? " active" : "");
    row.innerHTML = `
      <span class="model-name">${escapeHtml(modelLabels[option.value] || option.value)}</span>
      <span class="model-check">✓</span>
    `;
    row.addEventListener("click", () => {
      select.value = option.value;
      renderModelList();
    });
    list.appendChild(row);
  });
}

function setImageModel(value) {
  const model = value || "m3";
  if (knownImageModels.has(model)) {
    $("imageModel").value = model;
    $("imageModelCustom").value = "";
  } else {
    $("imageModel").value = "custom";
    $("imageModelCustom").value = model;
  }
  syncImageModelCustom();
}

function selectedImageModel() {
  if ($("imageModel").value === "custom") {
    return $("imageModelCustom").value.trim() || "m3";
  }
  return $("imageModel").value || "m3";
}

function syncImageModelCustom() {
  $("imageModelCustom").classList.toggle("hidden", $("imageModel").value !== "custom");
}

async function loadSettings() {
  const settings = await api("/api/settings");
  $("providerSelect").value = settings.provider || "minimax";
  providerChanged();
  $("modelSelect").value = settings.model_id || modelOptions[$("providerSelect").value][0];
  renderModelList();
  $("deepThinking").checked = (settings.deep_thinking ?? "on") !== "off";
  $("mainKey").value = settings.main_api_key || "";
  setImageModel(settings.image_model || "m3");
  $("imageKey").value = settings.minimax_image_key || "";
  $("tavilyKey").value = settings.tavily_key || "";
  $("globalMemory").value = settings.global_memory || "";
}

async function saveSettings(e) {
  e.preventDefault();
  const settings = {
    provider: $("providerSelect").value,
    model_id: $("modelSelect").value,
    main_api_key: $("mainKey").value,
    image_model: selectedImageModel(),
    minimax_image_key: $("imageKey").value,
    tavily_key: $("tavilyKey").value,
    global_memory: $("globalMemory").value,
    deep_thinking: $("deepThinking").checked ? "on" : "off",
  };
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify(settings) });
    closeSettings();
    setStatus("设置已保存，可以开始规划。", "目标");
  } catch (err) {
    showError(err);
  }
}

async function loadPlans() {
  const data = await api("/api/plans");
  planCache = new Map((data.plans || []).map((plan) => [plan.id, plan]));
  $("planCount").textContent = String(data.plans?.length || 0);
  renderPlanList(data.plans || []);
}

function renderPlanList(plans) {
  const box = $("planList");
  box.innerHTML = "";
  if (!plans.length) {
    box.innerHTML = `<div class="empty">还没有保存计划。</div>`;
    return;
  }
  for (const plan of plans) {
    const row = document.createElement("div");
    row.className = "plan-row" + (plan.id === latestPlanId ? " active" : "");
    row.dataset.planId = plan.id;
    row.innerHTML = `
      <button class="plan-item" type="button">
        <strong>${escapeHtml(plan.title)}</strong>
        <span>${escapeHtml(plan.model)}${plan.has_package ? " · 有执行包" : ""}</span>
      </button>
      <button class="plan-more" type="button" aria-label="更多操作">...</button>
      <div class="plan-menu">
        <button class="plan-delete" type="button">删除</button>
      </div>
    `;
    row.querySelector(".plan-item").addEventListener("click", () => openPlan(plan.id));
    row.querySelector(".plan-more").addEventListener("click", (event) => togglePlanMenu(plan.id, event));
    row.querySelector(".plan-delete").addEventListener("click", (event) => deletePlan(plan.id, event));
    box.appendChild(row);
  }
}

function closePlanMenus() {
  document.querySelectorAll(".plan-row.open").forEach((row) => row.classList.remove("open"));
}

function togglePlanMenu(id, event) {
  event.stopPropagation();
  const row = document.querySelector(`.plan-row[data-plan-id="${escapeCss(id)}"]`);
  const willOpen = !row?.classList.contains("open");
  closePlanMenus();
  if (row && willOpen) row.classList.add("open");
}

function markActivePlan(id) {
  document.querySelectorAll(".plan-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.planId === id);
  });
}

async function deletePlan(id, event) {
  event?.stopPropagation();
  const plan = planCache.get(id);
  if (!plan) return;
  const ok = window.confirm(`删除「${plan.title}」？\n这会同时删除本地保存的报告、图片和执行包。`);
  if (!ok) return;
  try {
    await api("/api/plan/delete", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    if (latestPlanId === id || latestSaved?.plan_id === id) {
      latestPlanId = null;
      latestSaved = null;
      previewAssetContext = "session";
      renderFolderWorkspace(null);
      renderMarkdown("");
      renderResources([]);
    }
    closePlanMenus();
    await loadPlans();
    setStatus("已删除保存的学习计划。", "目标");
  } catch (err) {
    showError(err);
  }
}

async function openPlan(id) {
  try {
    const plan = planCache.get(id) || { id };
    closePlanMenus();
    closeStatusStream();
    currentSession = null;
    clarifyState = { active: false, questions: [], answers: {}, index: 0 };
    setDraftReady(false);
    $("clarifyPanel").classList.add("hidden");
    latestPlanId = id;
    latestSaved = null;
    previewAssetContext = "plan";
    renderFolderWorkspace(plan);
    const data = await api(`/api/plan?id=${encodeURIComponent(id)}`);
    renderMarkdown(data.content || "");
    markActivePlan(id);
    switchTab("preview");
  } catch (err) {
    showError(err);
  }
}

async function openGeneratedFolder() {
  const id = latestSaved?.plan_id || latestPlanId;
  if (!id) {
    setStatus("还没有可打开的生成文件夹。", "保存");
    return;
  }
  try {
    const data = await api("/api/open-folder", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    setStatus(`已请求打开文件夹：${data.folder_path}`, "保存");
  } catch (err) {
    showError(err);
  }
}

async function handleComposerSubmit(e) {
  e.preventDefault();
  if (clarifyState.active) {
    handleDirectClarifyAnswer();
    return;
  }
  if (isDraftReady) {
    await submitFeedbackFromComposer();
    return;
  }
  await startPlanning();
}

async function startPlanning() {
  const goal = $("goalInput").value.trim();
  if (!goal) return;
  closeStatusStream();
  setDraftReady(false);
  addBubble("user", goal);
  setStatus("正在生成澄清问题...", "澄清");
  renderFolderWorkspace(null);
  latestPlanId = null;
  latestSaved = null;
  previewAssetContext = "session";
  setBusy(true);
  const payload = {
    goal,
    provider: $("providerSelect").value,
    model_id: $("modelSelect").value,
    main_api_key: $("mainKey").value,
    image_model: selectedImageModel(),
    minimax_image_key: $("imageKey").value,
    tavily_key: $("tavilyKey").value,
    global_memory: $("globalMemory").value,
    deep_thinking: $("deepThinking").checked ? "on" : "off",
  };
  try {
    const data = await api("/api/session/start", { method: "POST", body: JSON.stringify(payload) });
    currentSession = data.session_id;
    addBubble("assistant", "我先问几个问题，把计划调准。");
    beginClarification(data.questions || []);
  } catch (err) {
    setBusy(false);
    showError(err);
  }
}

function beginClarification(questions) {
  clarifyState = { active: true, questions, answers: {}, index: 0 };
  setBusy(false);
  $("goalInput").value = "";
  $("goalInput").placeholder = "Or reply directly...";
  $("composerSubmitBtn").textContent = "提交当前回答";
  $("clarifyPanel").classList.remove("hidden");
  if (!questions.length) {
    finishClarification();
    return;
  }
  renderClarifyCard();
}

function renderClarifyCard() {
  const question = clarifyState.questions[clarifyState.index];
  if (!question) return;
  const key = question.question;
  const selected = clarifyState.answers[key] || "";
  $("clarifyQuestion").textContent = key;
  $("clarifyCounter").textContent = `${clarifyState.index + 1} of ${clarifyState.questions.length}`;
  $("clarifyPrevBtn").disabled = clarifyState.index === 0;
  $("clarifyNextBtn").disabled = clarifyState.index >= clarifyState.questions.length - 1 && !selected;

  const box = $("clarifyOptions");
  box.innerHTML = "";
  question.options.forEach((opt, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "clarify-option" + (selected === opt ? " active" : "");
    btn.innerHTML = `
      <span class="option-index">${idx + 1}</span>
      <span class="option-text">${escapeHtml(opt)}</span>
      <span class="option-arrow">→</span>
    `;
    btn.addEventListener("click", () => chooseClarifyAnswer(opt));
    box.appendChild(btn);
  });
}

function chooseClarifyAnswer(answer) {
  const question = clarifyState.questions[clarifyState.index];
  if (!question) return;
  clarifyState.answers[question.question] = answer;
  advanceClarify();
}

function handleDirectClarifyAnswer() {
  const value = $("goalInput").value.trim();
  if (value) {
    chooseClarifyAnswer(value);
  } else {
    skipClarify();
  }
}

function skipClarify() {
  const question = clarifyState.questions[clarifyState.index];
  if (question) {
    delete clarifyState.answers[question.question];
  }
  advanceClarify();
}

function advanceClarify() {
  $("goalInput").value = "";
  if (clarifyState.index >= clarifyState.questions.length - 1) {
    finishClarification();
    return;
  }
  clarifyState.index += 1;
  renderClarifyCard();
}

function previousClarify() {
  if (!clarifyState.active || clarifyState.index <= 0) return;
  clarifyState.index -= 1;
  $("goalInput").value = "";
  renderClarifyCard();
}

function finishClarification() {
  const answers = { ...clarifyState.answers };
  clarifyState.active = false;
  $("clarifyPanel").classList.add("hidden");
  $("goalInput").value = "";
  $("goalInput").placeholder = defaultGoalPlaceholder;
  $("composerSubmitBtn").textContent = "生成澄清问题";
  addBubble("assistant", "收到，我开始运行多智能体生成计划。");
  submitAnswers(answers, "");
}

function cancelClarification() {
  clarifyState.active = false;
  $("clarifyPanel").classList.add("hidden");
  $("goalInput").value = "";
  $("goalInput").placeholder = defaultGoalPlaceholder;
  $("composerSubmitBtn").textContent = "生成澄清问题";
  setStatus("已取消澄清，可以重新输入学习目标。", "目标");
}

async function submitAnswers(answers, extra = "") {
  if (!currentSession) return;
  setBusy(true);
  setStatus("正在运行多智能体生成计划...", "草稿");
  initAgentTimeline();
  try {
    const data = await api("/api/session/answer", {
      method: "POST",
      body: JSON.stringify({ session_id: currentSession, answers, extra }),
    });
    currentSession = data.session_id;
    connectStatusStream(currentSession);
  } catch (err) {
    setBusy(false);
    showError(err);
  }
}

function initAgentTimeline() {
  $("agentStatusPanel").classList.remove("hidden");
  $("agentStatusLabel").textContent = "运行中";
  $("agentTimeline").innerHTML = runPhases.map((phase) => `
    <div class="agent-step" data-phase="${escapeAttr(phase)}" data-status="pending">
      <span class="agent-dot"></span>
      <strong>${escapeHtml(phase)}</strong>
      <small>等待中</small>
    </div>
  `).join("");
}

function updatePhase(phase, status) {
  let row = [...document.querySelectorAll(".agent-step")].find((el) => el.dataset.phase === phase);
  if (!row) {
    row = document.createElement("div");
    row.className = "agent-step";
    row.dataset.phase = phase;
    row.innerHTML = `<span class="agent-dot"></span><strong>${escapeHtml(phase)}</strong><small></small>`;
    $("agentTimeline").appendChild(row);
  }
  row.dataset.status = status;
  row.querySelector("small").textContent = statusText(status);
}

function statusText(status) {
  return ({ pending: "等待中", running: "运行中", done: "已完成", error: "出错" })[status] || status;
}

function addAgentLogBubble(text) {
  const clean = String(text || "").trim();
  if (!clean) return;
  addBubble("assistant agent-log", clean);
}

function parseEventData(event) {
  try {
    return JSON.parse(event.data || "{}");
  } catch (err) {
    return {};
  }
}

function connectStatusStream(sessionId) {
  closeStatusStream();
  const source = new EventSource(`/api/session/events?session_id=${encodeURIComponent(sessionId)}`);
  statusSource = source;

  source.addEventListener("phase", (event) => {
    const data = parseEventData(event);
    updatePhase(data.phase || "运行中", data.status || "running");
  });
  source.addEventListener("log", (event) => {
    const data = parseEventData(event);
    addAgentLogBubble(data.text || "");
  });
  source.addEventListener("result", (event) => {
    const data = parseEventData(event);
    closeStatusStream();
    setBusy(false);
    $("agentStatusLabel").textContent = "已完成";
    setStatus("计划草稿已生成，可以反馈或保存。", "草稿");
    renderSession(data);
    setDraftReady(true);
    addBubble("assistant", "计划草稿已生成。你可以继续反馈，或保存最终文件。");
  });
  source.addEventListener("error", (event) => {
    const data = parseEventData(event);
    closeStatusStream();
    setBusy(false);
    showError(data.message || "运行失败");
  });
  source.addEventListener("heartbeat", () => {});
  source.onerror = () => {
    if (statusSource === source) {
      closeStatusStream();
      setBusy(false);
      showError("状态连接中断，请检查后端服务。");
    }
  };
}

function closeStatusStream() {
  if (statusSource) {
    statusSource.close();
    statusSource = null;
  }
}

function setDraftReady(ready) {
  isDraftReady = Boolean(ready);
  $("draftActionBar").classList.toggle("hidden", !isDraftReady);
  $("goalInput").placeholder = isDraftReady
    ? "继续反馈这个计划，例如：换成中文免费资源，或把周期压缩到 4 周。"
    : defaultGoalPlaceholder;
  $("composerSubmitBtn").textContent = isDraftReady ? "提交反馈" : "生成澄清问题";
  const saveBtn = $("saveBtn");
  if (saveBtn) saveBtn.disabled = !isDraftReady;
  if (isDraftReady) scrollChatPaneToActions();
}

function scrollChatPaneToActions() {
  const pane = document.querySelector(".chat-pane");
  if (!pane) return;
  requestAnimationFrame(() => {
    pane.scrollTo({ top: pane.scrollHeight, behavior: "smooth" });
  });
}

async function submitFeedbackFromComposer() {
  if (!currentSession) return;
  const feedback = $("goalInput").value.trim();
  if (!feedback) return;
  addBubble("user", feedback);
  $("goalInput").value = "";
  setStatus("正在按反馈调整计划...", "草稿");
  setBusy(true);
  try {
    const data = await api("/api/session/feedback", {
      method: "POST",
      body: JSON.stringify({ session_id: currentSession, feedback }),
    });
    renderSession(data);
    setDraftReady(true);
  } catch (err) {
    showError(err);
  } finally {
    setBusy(false);
  }
}

async function saveFinal() {
  if (!currentSession) return;
  setStatus("正在保存最终报告与执行包...", "保存");
  setBusy(true);
  try {
    const data = await api("/api/session/save", {
      method: "POST",
      body: JSON.stringify({ session_id: currentSession }),
    });
    latestSaved = data.saved || null;
    latestPlanId = latestSaved?.plan_id || latestPlanId;
    renderSession(data);
    const saved = latestSaved;
    await loadPlans();
    resetToNewPlanAfterSave(saved);
  } catch (err) {
    showError(err);
  } finally {
    setBusy(false);
  }
}

function renderSession(data) {
  currentSession = data.session_id;
  previewAssetContext = latestSaved ? "plan" : "session";
  if (data.markdown) renderMarkdown(data.markdown);
  renderResources(data.resources || []);
  if (data.is_running || data.status === "running") return;
  const last = data.messages?.[data.messages.length - 1];
  if (last?.role === "assistant") {
    addBubble("assistant", summarizeLog(last.content));
  }
}

function summarizeLog(text) {
  const lines = String(text || "").split("\n").filter(Boolean);
  const useful = lines.filter((line) =>
    /(领域|画像|搜索到|完成评估|资源评估|学习计划已生成|视觉编排完成|已根据|反馈调整)/.test(line)
  );
  return useful.slice(-10).join("\n") || "已完成当前步骤。";
}

function renderFolderWorkspace(meta) {
  const hasFolder = Boolean(meta?.folder_path);
  $("folderTitle").textContent = meta?.title || (hasFolder ? "最终学习文件夹" : "等待生成最终文件");
  $("folderSubtitle").textContent = hasFolder
    ? "报告、图片资产和学习执行包已经写入本地。"
    : "确认保存后，会生成报告、assets 图片和 package 执行包。";
  $("folderPath").textContent = meta?.folder_path || "尚未保存";
  $("reportPath").textContent = basename(meta?.report_path) || "等待保存";
  $("packageDir").textContent = basename(meta?.package_dir) || "等待保存";
  $("openFolderBtn").disabled = !(meta?.plan_id || meta?.id || latestPlanId);

  const chips = $("packageChips");
  const files = meta?.package_files || [];
  if (!files.length) {
    chips.innerHTML = `<span>plan.md</span><span>daily-checklist.md</span><span>review-log.md</span><span>quiz.md</span>`;
    chips.classList.toggle("muted", !hasFolder);
    return;
  }
  chips.classList.remove("muted");
  chips.innerHTML = files.map((name) => `<span>${escapeHtml(name)}</span>`).join("");
}

function renderMarkdown(md) {
  $("preview").innerHTML = markdownToHtml(md || "暂无内容");
}

function renderResources(resources) {
  const box = $("resourceList");
  if (!resources.length) {
    box.textContent = "推荐资源会显示在这里。";
    box.className = "resource-list empty";
    return;
  }
  box.className = "resource-list";
  box.innerHTML = resources.map((r) => `
    <article class="resource-card">
      <h4>${escapeHtml(r.title || "资源")}</h4>
      <a href="${escapeAttr(r.url || "#")}" target="_blank">${escapeHtml(r.url || "")}</a>
      <div class="badges">
        ${r.language ? `<span>${escapeHtml(r.language)}</span>` : ""}
        ${r.cost ? `<span>${escapeHtml(r.cost)}</span>` : ""}
        ${r.difficulty ? `<span>${escapeHtml(r.difficulty)}</span>` : ""}
        ${r.fit_score ? `<span>适合度 ${escapeHtml(String(r.fit_score))}</span>` : ""}
      </div>
      <p>${escapeHtml(r.why || r.reason || "")}</p>
      ${r.use_hint ? `<p><strong>用法：</strong>${escapeHtml(r.use_hint)}</p>` : ""}
    </article>
  `).join("");
}

function markdownToHtml(md) {
  const lines = md.split("\n");
  let html = "";
  let inList = false;
  for (const line of lines) {
    const image = line.match(/^!\[(.*?)\]\((.*?)\)$/);
    if (image) {
      html += `<figure><img src="${escapeAttr(assetUrl(image[2]))}" alt="${escapeAttr(image[1])}"><figcaption>${escapeHtml(image[1])}</figcaption></figure>`;
      continue;
    }
    if (/^\|.*\|$/.test(line)) {
      html += `<pre>${escapeHtml(line)}</pre>`;
      continue;
    }
    if (line.startsWith("# ")) html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
    else if (line.startsWith("## ")) html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
    else if (line.startsWith("### ")) html += `<h3>${escapeHtml(line.slice(4))}</h3>`;
    else if (line.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${inlineMd(line.slice(2))}</li>`;
      continue;
    } else if (line.trim() === "") {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
    } else {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      html += `<p>${inlineMd(line)}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function assetUrl(path) {
  const p = String(path || "");
  if (/^https?:\/\//.test(p)) return p;
  if (previewAssetContext === "plan" && latestPlanId) {
    return `/api/asset?id=${encodeURIComponent(latestPlanId)}&path=${encodeURIComponent(p)}`;
  }
  if (currentSession) {
    return `/api/session/asset?session_id=${encodeURIComponent(currentSession)}&path=${encodeURIComponent(p)}`;
  }
  return p;
}

function inlineMd(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/&lt;(https?:\/\/.*?)&gt;/g, '<a href="$1" target="_blank">$1</a>');
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  document.querySelectorAll(".tab-page").forEach((page) => page.classList.toggle("active", page.id === `tab-${name}`));
}

function openSettings() {
  $("settingsModal").classList.remove("hidden");
  $("settingsModal").setAttribute("aria-hidden", "false");
}

function closeSettings() {
  $("settingsModal").classList.add("hidden");
  $("settingsModal").setAttribute("aria-hidden", "true");
}

function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

function normalizedTheme(choice) {
  return ["light", "dark", "system"].includes(choice) ? choice : "system";
}

function resolvedTheme(choice) {
  return normalizedTheme(choice) === "system" ? systemTheme() : normalizedTheme(choice);
}

function updateThemeControls() {
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    const active = button.dataset.themeChoice === currentThemeChoice;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function applyTheme(choice, persist = true) {
  currentThemeChoice = normalizedTheme(choice);
  document.documentElement.dataset.theme = resolvedTheme(currentThemeChoice);
  document.documentElement.dataset.themeChoice = currentThemeChoice;
  updateThemeControls();
  if (persist) {
    try {
      localStorage.setItem(themeStorageKey, currentThemeChoice);
    } catch (err) {
      // Theme switching should still work when local storage is blocked.
    }
  }
}

function initTheme() {
  let saved = "system";
  try {
    saved = localStorage.getItem(themeStorageKey) || "system";
  } catch (err) {
    saved = "system";
  }
  applyTheme(saved, false);
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  media?.addEventListener?.("change", () => {
    if (currentThemeChoice === "system") applyTheme("system", false);
  });
}

function normalizedCanvasStyle(style) {
  return ["plain", "grid", "paper", "texture"].includes(style) ? style : "grid";
}

function updateCanvasStyleControls() {
  document.querySelectorAll("[data-canvas-style]").forEach((button) => {
    const active = button.dataset.canvasStyle === currentCanvasStyle;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function applyCanvasStyle(style, persist = true) {
  currentCanvasStyle = normalizedCanvasStyle(style);
  document.documentElement.dataset.canvasStyle = currentCanvasStyle;
  updateCanvasStyleControls();
  if (persist) {
    try {
      localStorage.setItem(canvasStyleStorageKey, currentCanvasStyle);
    } catch (err) {
      // Canvas style switching should still work when local storage is blocked.
    }
  }
}

function initCanvasStyle() {
  let saved = "grid";
  try {
    saved = localStorage.getItem(canvasStyleStorageKey) || "grid";
  } catch (err) {
    saved = "grid";
  }
  applyCanvasStyle(saved, false);
}

function initResizableSplit() {
  const main = document.querySelector(".main");
  const resizer = $("splitResizer");
  if (!main || !resizer) return;

  const defaultRatio = 0.47;
  const minChatWidth = 380;
  const minWorkspaceWidth = 460;
  const splitterAndGaps = 34;

  const clampSplitRatio = (ratio, rect = main.getBoundingClientRect()) => {
    const width = rect.width || main.clientWidth || 0;
    const value = Number(ratio) || defaultRatio;
    if (!width) return defaultRatio;
    const minRatio = minChatWidth / width;
    const maxRatio = (width - minWorkspaceWidth - splitterAndGaps) / width;
    const lower = Math.max(0.28, minRatio);
    const upper = Math.min(0.72, Math.max(lower, maxRatio));
    return Math.min(upper, Math.max(lower, value));
  };

  const currentRatio = () => {
    try {
      const saved = Number(localStorage.getItem(splitStorageKey));
      if (saved) return saved;
    } catch (err) {
      // Local storage may be unavailable; fall back to the default split.
    }
    const rect = main.getBoundingClientRect();
    const width = parseFloat(getComputedStyle(main).getPropertyValue("--chat-width"));
    return rect.width && width ? width / rect.width : defaultRatio;
  };

  const setRatio = (ratio, persist = true) => {
    const rect = main.getBoundingClientRect();
    const next = clampSplitRatio(ratio, rect);
    main.style.setProperty("--chat-width", `${Math.round(rect.width * next)}px`);
    resizer.setAttribute("aria-valuenow", String(Math.round(next * 100)));
    if (persist) {
      try {
        localStorage.setItem(splitStorageKey, String(next));
      } catch (err) {
        // Local storage can be disabled; resizing should still work for this session.
      }
    }
  };

  try {
    const saved = Number(localStorage.getItem(splitStorageKey));
    setRatio(saved || defaultRatio, false);
  } catch (err) {
    setRatio(defaultRatio, false);
  }
  window.addEventListener("resize", () => setRatio(currentRatio(), false));

  let dragging = false;
  const move = (event) => {
    if (!dragging) return;
    const rect = main.getBoundingClientRect();
    if (rect.width < 900) return;
    setRatio((event.clientX - rect.left) / rect.width);
  };
  const stop = () => {
    dragging = false;
    document.body.classList.remove("resizing");
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", stop);
  };

  resizer.addEventListener("pointerdown", (event) => {
    dragging = true;
    resizer.setPointerCapture?.(event.pointerId);
    document.body.classList.add("resizing");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  });
  resizer.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const delta = event.key === "ArrowLeft" ? -0.03 : 0.03;
    setRatio(currentRatio() + delta);
  });
}

function resetRunUi() {
  closeStatusStream();
  clarifyState = { active: false, questions: [], answers: {}, index: 0 };
  setDraftReady(false);
  $("clarifyPanel").classList.add("hidden");
  $("agentStatusPanel").classList.add("hidden");
  $("agentTimeline").innerHTML = "";
  $("goalInput").disabled = false;
  $("goalInput").value = "";
  $("composerSubmitBtn").disabled = false;
}

function resetToNewPlan(statusText = "输入新的学习目标。") {
  currentSession = null;
  latestPlanId = null;
  latestSaved = null;
  previewAssetContext = "session";
  resetRunUi();
  renderFolderWorkspace(null);
  renderMarkdown("");
  renderResources([]);
  markActivePlan("");
  setStatus(statusText, "目标");
  $("goalInput").focus();
}

function resetToNewPlanAfterSave(saved) {
  const suffix = saved?.folder_path ? `已保存到：${saved.folder_path}。` : "已保存最终学习计划。";
  resetToNewPlan(`${suffix} 可以继续新建学习规划。`);
}

function basename(path) {
  const p = String(path || "").replace(/\\/g, "/");
  return p ? p.split("/").filter(Boolean).pop() : "";
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[m]));
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/`/g, "&#96;");
}

function escapeCss(text) {
  if (window.CSS?.escape) return CSS.escape(String(text));
  return String(text).replace(/["\\]/g, "\\$&");
}

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initCanvasStyle();
  providerChanged();
  initResizableSplit();
  renderFolderWorkspace(null);
  await loadSettings();
  await loadPlans();

  $("providerSelect").addEventListener("change", providerChanged);
  $("imageModel").addEventListener("change", syncImageModelCustom);
  $("settingsForm").addEventListener("submit", saveSettings);
  $("settingsButton").addEventListener("click", openSettings);
  $("settingsBackdrop").addEventListener("click", closeSettings);
  $("closeSettingsBtn").addEventListener("click", closeSettings);
  document.addEventListener("click", closePlanMenus);
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeChoice));
  });
  document.querySelectorAll("[data-canvas-style]").forEach((button) => {
    button.addEventListener("click", () => applyCanvasStyle(button.dataset.canvasStyle));
  });
  $("goalForm").addEventListener("submit", handleComposerSubmit);
  $("clarifyPrevBtn").addEventListener("click", previousClarify);
  $("clarifyNextBtn").addEventListener("click", advanceClarify);
  $("clarifySkipBtn").addEventListener("click", skipClarify);
  $("clarifyCloseBtn").addEventListener("click", cancelClarification);
  $("saveBtn").addEventListener("click", saveFinal);
  $("openFolderBtn").addEventListener("click", openGeneratedFolder);
  $("newPlanBtn").addEventListener("click", () => {
    resetToNewPlan();
  });
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
});
