// Dashboard for cast-notebooklm's REST API. Plain vanilla JS, no build
// step, no framework -- just fetch() against the same API this page is
// served from. The API key is only ever stored in this browser's
// localStorage; it's sent as the X-API-Key header on every call, same as
// any other client of the REST API (see rest_api/deps.py).

const API_KEY_STORAGE_KEY = "cast_notebooklm_api_key";

let notebooks = [];
let activeNotebookId = null;

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE_KEY) || "";
}

function setApiKey(key) {
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

async function apiFetch(path, options = {}) {
  const headers = Object.assign({}, options.headers, { "X-API-Key": getApiKey() });
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, Object.assign({}, options, { headers }));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.error || `Error ${response.status}`);
  }
  return data;
}

// Every dynamic string in this file (notebook titles, error messages,
// chat answers) is rendered via textContent / a single <li>/<div> element,
// never innerHTML -- none of it should be parsed as HTML, since some of
// it (error messages, chat answers) ultimately comes from the notebook
// content a user uploaded, which this project treats as untrusted (see
// notebooklm_tools/services/provenance.py).
function _setSingleListItem(list, text, className) {
  const li = document.createElement("li");
  li.textContent = text;
  if (className) li.className = className;
  list.replaceChildren(li);
}

async function loadNotebooks() {
  const list = document.getElementById("notebook-list");
  _setSingleListItem(list, "Cargando...");
  try {
    const res = await apiFetch("/notebooks");
    notebooks = res.data.notebooks;
    renderNotebookList();
  } catch (e) {
    _setSingleListItem(list, e.message, "error");
  }
}

function renderNotebookList() {
  const list = document.getElementById("notebook-list");
  if (notebooks.length === 0) {
    _setSingleListItem(list, "No tenés notebooks todavía.");
    return;
  }
  const items = notebooks.map((nb) => {
    const li = document.createElement("li");
    li.textContent = `${nb.title} (${nb.source_count} fuentes)`;
    li.className = nb.id === activeNotebookId ? "active" : "";
    li.addEventListener("click", () => selectNotebook(nb.id, nb.title));
    return li;
  });
  list.replaceChildren(...items);
}

function selectNotebook(id, title) {
  activeNotebookId = id;
  document.getElementById("active-notebook-title").textContent = title;
  document.getElementById("chat-panel").classList.remove("hidden");
  document.getElementById("chat-log").replaceChildren();
  document.getElementById("studio-status").textContent = "";
  renderNotebookList();
}

function appendChat(role, text) {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

async function sendQuestion() {
  const input = document.getElementById("question-input");
  const question = input.value.trim();
  if (!question || !activeNotebookId) return;

  appendChat("user", question);
  input.value = "";
  const pending = appendChat("assistant", "...pensando...");

  try {
    const res = await apiFetch("/chat/ask", {
      method: "POST",
      body: JSON.stringify({ notebook_id: activeNotebookId, question }),
    });
    pending.textContent = res.data.answer;
  } catch (e) {
    pending.textContent = `Error: ${e.message}`;
  }
}

function setStudioStatus(text) {
  document.getElementById("studio-status").textContent = text;
}

async function generateContentPack() {
  if (!activeNotebookId) return;
  setStudioStatus("Generando audio + quiz + resumen...");
  try {
    const res = await apiFetch("/studio/content-pack", {
      method: "POST",
      body: JSON.stringify({ notebook_id: activeNotebookId }),
    });
    const lines = res.data.results.map(
      (r) => `${r.artifact_type}: ${r.success ? "iniciado ✓" : "error - " + r.error}`
    );
    lines.push("", 'Usá "Ver estado" en unos minutos para ver si ya terminaron.');
    setStudioStatus(lines.join("\n"));
  } catch (e) {
    setStudioStatus(`Error: ${e.message}`);
  }
}

async function checkStudioStatus() {
  if (!activeNotebookId) return;
  setStudioStatus("Consultando...");
  try {
    const res = await apiFetch(`/studio/status/${activeNotebookId}`);
    const artifacts = res.data.artifacts;
    if (artifacts.length === 0) {
      setStudioStatus("Todavía no generaste nada en Studio para este notebook.");
      return;
    }
    const lines = artifacts.map(
      (a) => `${a.type}: ${a.status}${a.title ? " - " + a.title : ""}`
    );
    setStudioStatus(lines.join("\n"));
  } catch (e) {
    setStudioStatus(`Error: ${e.message}`);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const keyInput = document.getElementById("api-key-input");
  keyInput.value = getApiKey();

  document.getElementById("save-key-btn").addEventListener("click", () => {
    setApiKey(keyInput.value.trim());
    loadNotebooks();
  });
  document.getElementById("send-question-btn").addEventListener("click", sendQuestion);
  document.getElementById("question-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendQuestion();
  });
  document.getElementById("content-pack-btn").addEventListener("click", generateContentPack);
  document.getElementById("check-status-btn").addEventListener("click", checkStudioStatus);

  if (getApiKey()) loadNotebooks();
});
