/* =====================================================
 * 智能知识问答系统 前端逻辑（零依赖原生 JS）
 * ===================================================== */
"use strict";

/* ---------- 基础工具 ---------- */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const TOKEN_KEY = "ragqa_token";
const USER_KEY = "ragqa_username";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  username: localStorage.getItem(USER_KEY) || "",
  kbs: [],
  currentKb: 0,
  conversations: [],
  currentConv: 0,
  streaming: false,
};

function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  return fetch(path, { ...options, headers }).then(async (res) => {
    if (res.status === 401) { logout(); throw new Error("登录已过期"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
    return data;
  });
}

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast ${isError ? "error" : ""}`;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------- 视图切换 ---------- */
function switchView(view) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  ["chat", "kb", "stats"].forEach((v) => {
    $("#view-" + v).classList.toggle("hidden", v !== view);
  });
  if (view === "kb") loadKbs();
  if (view === "stats") loadStats();
  if (view === "chat") refreshChatView();
}

/* ---------- 认证 ---------- */
let authMode = "login";
function showAuth() {
  $("#authPage").classList.remove("hidden");
  $("#app").classList.add("hidden");
}
function enterApp() {
  $("#authPage").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#usernameLabel").textContent = state.username;
  loadKbs().then(() => { if (!$("#kbSelect").value) $("#kbSelect").value = "0"; });
  loadConversations();
}
function logout() {
  state.token = "";
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  showAuth();
}

function initAuth() {
  $$(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      authMode = tab.dataset.tab;
      $$(".auth-tab").forEach((t) => t.classList.toggle("active", t === tab));
      $("#authSubmit").textContent = authMode === "login" ? "登录" : "注册";
      $("#authError").textContent = "";
    });
  });
  $("#authSubmit").addEventListener("click", async () => {
    const username = $("#authUsername").value.trim();
    const password = $("#authPassword").value;
    if (!username || !password) { $("#authError").textContent = "请输入用户名和密码"; return; }
    try {
      const data = await api(`/api/auth/${authMode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      state.token = data.access_token;
      state.username = data.username;
      localStorage.setItem(TOKEN_KEY, state.token);
      localStorage.setItem(USER_KEY, state.username);
      enterApp();
    } catch (e) {
      $("#authError").textContent = e.message;
    }
  });
}

/* ---------- 知识库 ---------- */
async function loadKbs() {
  const kbs = await api("/api/kb");
  state.kbs = kbs;
  renderKbSelect();
  renderKbList();
  return kbs;
}

function renderKbSelect() {
  const sel = $("#kbSelect");
  const prev = sel.value;
  sel.innerHTML = `<option value="0">全部知识库</option>` +
    state.kbs.map((k) => `<option value="${k.id}">${escapeHtml(k.name)}</option>`).join("");
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  else sel.value = state.currentKb || "0";
}

function renderKbList() {
  const wrap = $("#kbList");
  if (!state.kbs.length) {
    wrap.innerHTML = `<div class="empty-tip" style="grid-column:1/-1">暂无知识库，点击右上角「新建知识库」开始</div>`;
    return;
  }
  wrap.innerHTML = state.kbs.map((kb) => `
    <div class="kb-card">
      <div class="kb-card-head">
        <div>
          <div class="kb-card-name">${escapeHtml(kb.name)}</div>
          <div class="kb-card-desc">${escapeHtml(kb.description || "暂无描述")}</div>
        </div>
        <div class="kb-actions">
          <label class="btn btn-sm upload-btn">上传文档
            <input type="file" accept=".pdf,.docx,.md,.txt" data-kbid="${kb.id}">
          </label>
          <button class="btn btn-ghost btn-sm" data-del-kb="${kb.id}" title="删除知识库">删除</button>
        </div>
      </div>
      <div class="kb-meta">
        <span>文档 ${kb.doc_count}</span><span>文本块 ${kb.chunk_count}</span>
      </div>
      <ul class="doc-list" id="docList-${kb.id}">加载中...</ul>
    </div>`).join("");

  // 绑定上传与删除
  $$('input[type="file"][data-kbid]').forEach((input) => {
    input.addEventListener("change", () => uploadDoc(Number(input.dataset.kbid), input.files[0], input));
  });
  $$("[data-del-kb]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.delKb);
      if (!confirm(`确定删除知识库「${state.kbs.find(k => k.id === id)?.name || ""}」及其所有文档？`)) return;
      try { await api(`/api/kb/${id}`, { method: "DELETE" }); toast("已删除"); await loadKbs(); }
      catch (e) { toast(e.message, true); }
    });
  });
  state.kbs.forEach((kb) => loadDocs(kb.id));
}

async function loadDocs(kbId) {
  const wrap = $("#docList-" + kbId);
  if (!wrap) return;
  try {
    const docs = await api(`/api/kb/${kbId}/docs`);
    if (!docs.length) { wrap.innerHTML = `<li style="border:none">暂无文档</li>`; return; }
    wrap.innerHTML = docs.map((d) => `
      <li>
        <span class="badge ${d.status}">${d.status === "ready" ? "可用" : d.status === "failed" ? "失败" : "处理中"}</span>
        <span class="doc-name" title="${escapeHtml(d.error_msg)}">${escapeHtml(d.filename)}</span>
        <span style="flex-shrink:0">${d.chunk_count} 块</span>
        ${d.status === "failed" ? `<button class="doc-op" data-reproc="${d.id}" data-kb="${kbId}">重试</button>` : ""}
        <button class="doc-op" data-del-doc="${d.id}" data-kb="${kbId}">删除</button>
      </li>`).join("");
    wrap.querySelectorAll("[data-del-doc]").forEach((b) => {
      b.addEventListener("click", async () => {
        if (!confirm("确定删除该文档？")) return;
        try { await api(`/api/kb/${kbId}/docs/${b.dataset.delDoc}`, { method: "DELETE" }); toast("已删除"); loadKbs(); }
        catch (e) { toast(e.message, true); }
      });
    });
    wrap.querySelectorAll("[data-reproc]").forEach((b) => {
      b.addEventListener("click", async () => {
        try { toast("正在重新处理..."); await api(`/api/kb/${kbId}/docs/${b.dataset.reproc}/reprocess`, { method: "POST" }); toast("完成"); loadKbs(); }
        catch (e) { toast(e.message, true); }
      });
    });
  } catch (e) {
    wrap.innerHTML = `<li style="border:none;color:var(--red)">${escapeHtml(e.message)}</li>`;
  }
}

async function uploadDoc(kbId, file, input) {
  if (!file) return;
  if (!/\.(pdf|docx|md|txt)$/i.test(file.name)) { toast("仅支持 PDF/DOCX/MD/TXT", true); return; }
  const fd = new FormData();
  fd.append("file", file);
  try {
    toast(`正在解析「${file.name}」...`);
    await fetch(`/api/kb/${kbId}/docs`, {
      method: "POST",
      headers: { Authorization: `Bearer ${state.token}` },
      body: fd,
    }).then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "上传失败");
      return data;
    });
    toast("上传并解析成功");
    loadKbs();
  } catch (e) {
    toast(e.message, true);
  } finally {
    input.value = "";
  }
}

/* ---------- 会话 ---------- */
async function loadConversations() {
  state.conversations = await api("/api/chat/conversations");
  renderConvList();
}

function renderConvList() {
  const ul = $("#convList");
  if (!state.conversations.length) {
    ul.innerHTML = `<li style="color:var(--text-3);cursor:default">暂无会话，点击「新对话」开始</li>`;
    return;
  }
  ul.innerHTML = state.conversations.map((c) => `
    <li class="${c.id === state.currentConv ? "active" : ""}" data-conv="${c.id}">
      <span class="conv-title">${escapeHtml(c.title)}</span>
      <button class="conv-del" data-del-conv="${c.id}">×</button>
    </li>`).join("");
  ul.querySelectorAll("[data-conv]").forEach((li) => {
    li.addEventListener("click", (e) => {
      if (e.target.closest(".conv-del")) return;
      openConversation(Number(li.dataset.conv));
    });
  });
  ul.querySelectorAll("[data-del-conv]").forEach((b) => {
    b.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("删除该会话？")) return;
      try { await api(`/api/chat/conversations/${b.dataset.delConv}`, { method: "DELETE" }); loadConversations(); }
      catch (err) { toast(err.message, true); }
    });
  });
}

async function openConversation(convId) {
  state.currentConv = convId;
  renderConvList();
  const msgs = await api(`/api/chat/conversations/${convId}/messages`);
  renderMessages(msgs);
}

async function newConversation() {
  const kbId = Number($("#kbSelect").value || 0);
  const conv = await api("/api/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ kb_id: kbId, title: "新对话" }),
  });
  state.currentConv = conv.id;
  await loadConversations();
  renderMessages([]);
  renderWelcome();
}

function renderWelcome() {
  const list = $("#msgList");
  list.innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">?</div>
      <h2>有什么可以帮您？</h2>
      <p>上传文档构建领域知识库，即可基于资料进行智能问答，回答附带可追溯的引用来源。</p>
    </div>`;
}

function renderMessages(msgs) {
  const list = $("#msgList");
  list.innerHTML = "";
  if (!msgs.length) { renderWelcome(); return; }
  msgs.forEach((m) => list.appendChild(renderMessageEl(m.role, m.content, m.sources || [])));
  list.scrollTop = list.scrollHeight;
}

function renderMessageEl(role, content, sources) {
  const div = document.createElement("div");
  div.className = `msg ${role === "user" ? "user" : "assistant"}`;
  const avatar = role === "user" ? "我" : "AI";
  let body = escapeHtml(content);
  // 引用编号高亮：[1] -> 可点击 chip
  body = body.replace(/\[(\d+)\]/g, (m, n) =>
    `<span class="cite" data-cite="${n - 1}">[${n}]</span>`);
  const sourceBar = sources && sources.length
    ? `<div class="source-bar">${sources.map((s, i) =>
        `<span class="source-chip" data-cite="${i}">来源 ${i + 1}${s.heading ? " · " + escapeHtml(String(s.heading).slice(0, 12)) : ""}</span>`).join("")}</div>`
    : "";
  div.innerHTML = `
    <div class="avatar">${avatar}</div>
    <div>
      <div class="bubble">${body}</div>
      ${sourceBar}
    </div>`;
  div.querySelectorAll("[data-cite]").forEach((el) => {
    el.addEventListener("click", () => openSources(sources, Number(el.dataset.cite)));
  });
  return div;
}

function openSources(sources, idx) {
  $("#sourceBody").innerHTML = sources.length
    ? sources.map((s, i) => `
      <div class="source-item" style="${i === idx ? "border-color:var(--primary);" : ""}">
        <div class="src-meta">
          <span>#${i + 1}</span>
          <span>相似度 ${(s.score || 0).toFixed(3)}</span>
          ${s.heading ? `<span>${escapeHtml(String(s.heading))}</span>` : ""}
          ${s.page ? `<span>第${s.page}页</span>` : ""}
        </div>
        <div class="src-text">${escapeHtml(s.content)}</div>
      </div>`).join("")
    : `<div class="empty-tip">无引用来源</div>`;
  $("#sourceDrawer").classList.remove("hidden");
}

/* ---------- 流式问答 ---------- */
async function ask(query) {
  const kbId = Number($("#kbSelect").value || 0);
  state.streaming = true;
  $("#sendBtn").disabled = true;

  // 渲染用户消息
  $("#msgList").appendChild(renderMessageEl("user", query, []));
  // 渲染助手占位
  const assistantEl = renderMessageEl("assistant", "", []);
  const bubble = assistantEl.querySelector(".bubble");
  bubble.innerHTML = `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;
  $("#msgList").appendChild(assistantEl);
  $("#msgList").scrollTop = $("#msgList").scrollHeight;

  let sources = [];
  let answerText = "";

  try {
    const resp = await fetch("/api/chat/ask-stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ query, kb_id: kbId, stream: true }),
    });
    if (!resp.ok) throw new Error(`请求失败(${resp.status})`);
    if (!resp.body) throw new Error("无响应流");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const events = buf.split("\n\n");
      buf = events.pop() || "";
      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith("data:")) continue;
        let obj;
        try { obj = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (obj.type === "sources") {
          sources = obj.data || [];
        } else if (obj.type === "delta") {
          answerText += obj.data;
          bubble.innerHTML = formatAnswer(answerText, sources);
          $("#msgList").scrollTop = $("#msgList").scrollHeight;
        } else if (obj.type === "done") {
          if (!state.conversations.some((c) => c.id === obj.data.conversation_id)) {
            loadConversations();
          }
        } else if (obj.type === "error") {
          throw new Error(obj.data);
        }
      }
    }
  } catch (e) {
    bubble.innerHTML = `<span style="color:var(--red)">回答失败：${escapeHtml(e.message)}</span>`;
  } finally {
    state.streaming = false;
    $("#sendBtn").disabled = false;
    if (answerText) loadConversations();
  }
}

function formatAnswer(text, sources) {
  let body = escapeHtml(text);
  body = body.replace(/\[(\d+)\]/g, (m, n) => {
    const i = Number(n) - 1;
    if (i >= 0 && i < (sources || []).length) return `<span class="cite" data-cite="${i}">[${n}]</span>`;
    return m;
  });
  const sourceBar = sources && sources.length
    ? `<div class="source-bar">${sources.map((s, i) =>
        `<span class="source-chip" data-cite="${i}">来源 ${i + 1}${s.heading ? " · " + escapeHtml(String(s.heading).slice(0, 12)) : ""}</span>`).join("")}</div>`
    : "";
  return body + sourceBar;
}

/* ---------- 统计 ---------- */
async function loadStats() {
  try {
    const s = await api("/api/stats");
    $("#statKb").textContent = s.kb_count;
    $("#statDoc").textContent = s.doc_count;
    $("#statChunk").textContent = s.chunk_count;
    $("#statConv").textContent = s.conversation_count;
    $("#statMsg").textContent = s.message_count;
    const bar = $("#kbBar");
    if (!s.kb_stats.length) { bar.innerHTML = `<div class="empty-tip">暂无知识库数据</div>`; return; }
    const max = Math.max(...s.kb_stats.map((k) => k.chunks), 1);
    bar.innerHTML = s.kb_stats.map((k) => `
      <div class="bar-row">
        <span class="bar-label" title="${escapeHtml(k.name)}">${escapeHtml(k.name)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max((k.chunks / max) * 100, 2)}%"></div></div>
        <span class="bar-val">${k.docs} 文档 / ${k.chunks} 块</span>
      </div>`).join("");
  } catch (e) {
    toast(e.message, true);
  }
}

/* ---------- 刷新聊天视图 ---------- */
function refreshChatView() {
  if (!state.conversations.length) renderWelcome();
}

/* ---------- 事件绑定 ---------- */
function bindEvents() {
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $("#logoutBtn").addEventListener("click", logout);

  $("#kbSelect").addEventListener("change", () => {
    state.currentKb = Number($("#kbSelect").value || 0);
  });

  $("#newConvBtn").addEventListener("click", () => newConversation().catch((e) => toast(e.message, true)));

  $("#sendBtn").addEventListener("click", sendQuery);
  $("#queryInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  });

  $("#newKbBtn").addEventListener("click", () => openModal("新建知识库", "", ""));
  $("#modalCancel").addEventListener("click", () => $("#modalMask").classList.add("hidden"));
  $("#modalOk").addEventListener("click", async () => {
    const name = $("#modalName").value.trim();
    if (!name) { toast("请输入名称", true); return; }
    try {
      await api("/api/kb", { method: "POST", body: JSON.stringify({ name, description: $("#modalDesc").value.trim() }) });
      toast("创建成功");
      $("#modalMask").classList.add("hidden");
      $("#modalName").value = ""; $("#modalDesc").value = "";
      loadKbs();
    } catch (e) { toast(e.message, true); }
  });
  $("#sourceClose").addEventListener("click", () => $("#sourceDrawer").classList.add("hidden"));
}

function openModal(title, name, desc) {
  $("#modalTitle").textContent = title;
  $("#modalName").value = name;
  $("#modalDesc").value = desc;
  $("#modalMask").classList.remove("hidden");
}

function sendQuery() {
  if (state.streaming) return;
  const input = $("#queryInput");
  const query = input.value.trim();
  if (!query) return;
  input.value = "";
  ask(query).catch((e) => toast(e.message, true));
}

/* ---------- 初始化 ---------- */
function init() {
  initAuth();
  bindEvents();
  if (state.token) {
    api("/api/auth/me").then(() => enterApp()).catch(() => showAuth());
  } else {
    showAuth();
  }
}

document.addEventListener("DOMContentLoaded", init);
