"use strict";

const byId = (id) => document.getElementById(id);
const modelForm = byId("model-form");
const field = (name) => modelForm.elements.namedItem(name);
let token = "";
let models = [];
let epoch = 0;
let testing = false;
let auditBefore = null;
let auditSerial = 0;
let auditAlias = "";
let editingEtag = null;
const pending = new Set();

function notice(message, error = false) {
  byId("notice").textContent = message;
  byId("notice").className = error ? "error" : "";
  byId("notice").hidden = !message;
}

async function api(path, options = {}) {
  const current = epoch;
  const controller = new AbortController();
  pending.add(controller);
  try {
    const response = await fetch(`/api/v1/admin${path}`, {
      ...options, signal: controller.signal,
      headers: { ...options.headers, "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
    });
    const data = await response.json();
    if (current !== epoch) throw new DOMException("Session ended", "AbortError");
    if (!response.ok) {
      const fields = data.error?.fields?.join(", ");
      if (data.error?.code === "configuration_conflict") throw new Error("配置已被修改，或该别名已存在。你的表单内容已保留，请刷新列表并重新点击编辑，核对最新配置后再保存。\n请求 ID：" + data.request_id);
      throw new Error(`${data.error?.message || "请求失败"}${fields ? ` · ${fields}` : ""} [${data.error?.code || response.status}]\n请求 ID：${data.request_id || "—"}`);
    }
    return data;
  } finally { pending.delete(controller); }
}

async function action(button, work) {
  if (button.disabled) return;
  button.disabled = true;
  try { await work(); }
  catch (error) { if (error.name !== "AbortError") notice(error.message, true); }
  finally { button.disabled = false; }
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function selectCapabilities() {
  const model = models.find((item) => item.alias === byId("test-model").value);
  const select = byId("test-capability");
  select.replaceChildren();
  for (const cap of model?.capabilities || []) {
    const option = node("option", cap === "chat" ? "文本对话" : "向量生成");
    option.value = cap;
    select.append(option);
  }
  byId("test-submit").disabled = !model || testing;
}

function renderModels() {
  byId("count-total").textContent = models.length;
  byId("count-enabled").textContent = models.filter((m) => m.enabled).length;
  byId("count-local").textContent = models.filter((m) => m.deployment === "local").length;
  const list = byId("model-list");
  list.replaceChildren();
  if (!models.length) list.append(node("div", "还没有模型连接。添加第一个云端或本地模型，开始测试。", "empty"));
  for (const model of models) {
    const card = node("article", undefined, "model-card");
    const head = node("div", undefined, "card-head");
    head.append(node("h3", model.alias), node("span", model.enabled ? "已启用" : "已禁用", `badge${model.enabled ? "" : " off"}`));
    const subtitle = `${model.deployment === "local" ? "本地" : "云端"} · ${model.provider === "ollama" ? "Ollama" : "兼容 API"} · ${model.model}`;
    const actions = node("div", undefined, "card-actions");
    const edit = node("button", "编辑", "text-button");
    edit.type = "button";
    edit.addEventListener("click", () => editModel(model));
    const test = node("button", "测试", "text-button");
    test.type = "button";
    test.disabled = !model.enabled;
    test.addEventListener("click", () => {
      byId("test-model").value = model.alias;
      selectCapabilities();
      byId("test-input").focus();
    });
    const toggle = node("button", model.enabled ? "禁用" : "启用", "text-button");
    toggle.type = "button";
    toggle.addEventListener("click", () => action(toggle, async () => {
      const { etag, ...config } = model;
      await api(`/models/${encodeURIComponent(model.alias)}`, { method: "PUT", headers: { "If-Match": etag }, body: JSON.stringify({ ...config, enabled: !model.enabled }) });
      await refresh();
      // Keep any open editor's snapshot unchanged; saving it must detect this change.
      notice(`模型 ${model.alias} 已${model.enabled ? "禁用" : "启用"}。`);
    }));
    actions.append(edit, test, toggle);
    card.append(head, node("p", subtitle), actions);
    list.append(card);
  }
  const previous = byId("test-model").value;
  byId("test-model").replaceChildren();
  for (const model of models.filter((m) => m.enabled)) {
    const option = node("option", model.alias);
    option.value = model.alias;
    byId("test-model").append(option);
  }
  if (models.some((m) => m.alias === previous && m.enabled)) byId("test-model").value = previous;
  selectCapabilities();
}

async function refresh() {
  models = await api("/models");
  renderModels();
  await loadAudit();
}

async function loadAudit(append = false) {
  const serial = ++auditSerial;
  if (!append) auditAlias = byId("audit-filter").value.trim();
  const params = new URLSearchParams({ limit: "20" });
  if (auditAlias) params.set("alias", auditAlias);
  if (append && auditBefore) params.set("before", String(auditBefore));
  byId("audit-status").textContent = "正在读取修改记录…";
  try {
    const page = await api(`/audit-events?${params}`);
    if (serial !== auditSerial) return;
    const rows = byId("audit-rows");
    if (!append) rows.replaceChildren();
    const labels = { created: "创建", updated: "修改", enabled: "启用", disabled: "禁用" };
    for (const event of page.data) {
      const row = node("tr");
      row.append(
        node("td", new Date(event.created_at).toLocaleString()),
        node("td", `${event.alias} · ${labels[event.action] || event.action}`),
        node("td", event.changed_fields.join("、")),
        node("td", `${event.actor}\n${event.request_id || "内部操作"}`),
      );
      rows.append(row);
    }
    auditBefore = page.next_before;
    byId("audit-more").hidden = !auditBefore;
    byId("audit-status").textContent = rows.children.length ? `已显示 ${rows.children.length} 条记录${auditBefore ? "" : " · 已到末尾"}` : "暂无修改记录";
  } catch (error) {
    if (serial === auditSerial && error.name !== "AbortError") byId("audit-status").textContent = "读取失败，请重试查询。";
    throw error;
  }
}

function providerFields() {
  const native = field("provider").value === "ollama";
  byId("token-parameter-field").hidden = native;
  if (native) field("token_parameter").value = "max_tokens";
}

function resetModel() {
  editingEtag = null;
  modelForm.reset();
  field("alias").readOnly = false;
  byId("editor-title").textContent = "添加模型";
  providerFields();
}

function editModel(model) {
  resetModel();
  editingEtag = model.etag;
  for (const [key, value] of Object.entries(model)) {
    if (key === "capabilities") continue;
    const input = field(key);
    if (!input) continue;
    if (input.type === "checkbox") input.checked = value;
    else input.value = value ?? "";
  }
  for (const cap of ["chat", "embeddings"]) field(cap).checked = model.capabilities.includes(cap);
  field("alias").readOnly = true;
  byId("editor-title").textContent = `编辑 ${model.alias}`;
  providerFields();
  byId("editor").scrollIntoView({ behavior: "smooth", block: "start" });
}

byId("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(event.submitter, async () => {
    token = byId("token").value.trim();
    try {
      const settings = await api("/settings");
      await refresh();
      byId("allowed-hosts").textContent = `允许的模型主机：${settings.allowed_hosts.join("、")}。容器访问宿主机使用 host.docker.internal；原生部署使用 localhost。`;
      byId("private-workspace").hidden = false;
      byId("login-form").hidden = true;
      byId("logout").hidden = false;
      byId("connection-state").textContent = settings.auth_mode === "tenant"
        ? "已连接 · 企业调用授权模式已启用"
        : "已连接 · 开发模式，全局调用令牌可使用全部启用模型";
      byId("token").value = "";
      notice("");
    } catch (error) { token = ""; throw error; }
  });
});

byId("logout").addEventListener("click", () => {
  epoch += 1;
  auditSerial += 1;
  auditBefore = null;
  byId("audit-rows").replaceChildren();
  byId("audit-filter").value = "";
  byId("audit-status").textContent = "尚未加载记录";
  byId("audit-more").hidden = true;
  token = "";
  for (const controller of pending) controller.abort();
  models = [];
  renderModels();
  resetModel();
  byId("private-workspace").hidden = true;
  byId("login-form").hidden = false;
  byId("logout").hidden = true;
  byId("connection-state").textContent = "已断开连接，请重新输入管理员令牌。";
  byId("test-result").textContent = "保存模型配置后，在这里查看回答、用量与耗时。";
  byId("test-status").textContent = "等待测试";
  byId("test-input").value = "请用一句话介绍你能提供的帮助。";
  notice("");
});
byId("refresh").addEventListener("click", (event) => action(event.currentTarget, refresh));
byId("new-model").addEventListener("click", () => { resetModel(); field("alias").focus(); });
byId("reset-model").addEventListener("click", resetModel);
field("provider").addEventListener("change", providerFields);
byId("test-model").addEventListener("change", selectCapabilities);

modelForm.addEventListener("submit", (event) => {
  event.preventDefault();
  action(event.submitter, async () => {
    const config = {};
    for (const name of ["alias", "model", "provider", "base_url", "deployment", "token_parameter"]) config[name] = field(name).value.trim();
    config.api_key_env = field("api_key_env").value.trim() || null;
    config.capabilities = ["chat", "embeddings"].filter((cap) => field(cap).checked);
    if (!config.capabilities.length) throw new Error("至少选择一种模型能力。");
    for (const name of ["max_output_tokens", "timeout_seconds"]) config[name] = Number(field(name).value);
    for (const name of ["enabled", "supports_temperature"]) config[name] = field(name).checked;
    const headers = editingEtag ? { "If-Match": editingEtag } : { "If-None-Match": "*" };
    const saved = await api(`/models/${encodeURIComponent(config.alias)}`, { method: "PUT", headers, body: JSON.stringify(config) });
    await refresh();
    editModel(saved);
    notice(`模型 ${saved.alias} 已保存。可在右侧发送测试请求验证能力。`);
  });
});

byId("test-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(event.submitter, async () => {
    const alias = byId("test-model").value;
    testing = true;
    byId("test-status").textContent = `正在请求 ${alias}，请稍候…`;
    byId("test-result").textContent = "";
    try {
      const data = await api(`/models/${encodeURIComponent(alias)}/test`, { method: "POST", body: JSON.stringify({ capability: byId("test-capability").value, input: byId("test-input").value }) });
      const result = data.result;
      byId("test-status").textContent = `${data.model} · ${data.elapsed_ms} ms · 输入 ${result.usage.input_tokens ?? "未知"} / 输出 ${result.usage.output_tokens ?? "未知"} token · 请求 ${data.request_id}`;
      byId("test-result").textContent = data.capability === "chat" ? result.content : `向量维度：${result.dimensions}\n向量数量：${result.vectors.length}\n前 12 维预览：\n${JSON.stringify(result.vectors[0].slice(0, 12), null, 2)}`;
      notice("测试请求成功。该结果仅验证本次请求，不代表模型所有能力均已验证。");
    } catch (error) {
      if (error.name !== "AbortError") {
        byId("test-status").textContent = "测试失败";
        byId("test-result").textContent = error.message;
      }
      throw error;
    } finally {
      testing = false;
      selectCapabilities();
    }
  });
});
providerFields();

byId("audit-filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(event.submitter, () => loadAudit());
});
byId("audit-more").addEventListener("click", (event) => action(event.currentTarget, () => loadAudit(true)));
