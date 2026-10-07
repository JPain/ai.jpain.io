// jpain.io editor. The server (server.py) owns the files; this page holds one open file,
// keeps an unsaved copy in localStorage, previews as you type and publishes on request.
"use strict";
const $ = (id) => document.getElementById(id);
const text = $("text"), frame = $("frame"), main = $("main");
let cur = null;          // {path, hash, slug, saved}: the open file and its text as last saved
let list = [];
let previewTimer = 0, previewSeq = 0, previewSlug = "";

const api = async (method, url, body, raw) => {
  const opts = { method, headers: { "X-Editor": "1" } };
  if (raw) { opts.body = raw; }
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok && r.status !== 409) throw new Error(data.error || `HTTP ${r.status}`);
  return { status: r.status, data };
};

const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* private mode */ } },
};
const backupKey = (p) => "jpain-editor:" + p;

const dirty = () => cur && text.value !== cur.saved;

// ---------------------------------------------------------------- dialog
function ask(title, body, buttons, log) {
  const d = $("dialog");
  $("dlg-title").textContent = title;
  const b = $("dlg-body");
  b.replaceChildren();
  if (typeof body === "string") { const p = document.createElement("p"); p.textContent = body; b.append(p); }
  else if (body) b.append(body);
  $("dlg-log").hidden = !log;
  $("dlg-log").textContent = log || "";
  $("dlg-buttons").replaceChildren(...buttons.map(([label, value, cls]) => {
    const btn = document.createElement("button");
    btn.className = "btn " + (cls || "");
    btn.value = value;
    btn.textContent = label;
    return btn;
  }));
  return new Promise((resolve) => {
    d.addEventListener("close", () => resolve(d.returnValue), { once: true });
    d.returnValue = "";
    d.showModal();
    const input = b.querySelector("input");
    (input || d.querySelector(".primary") || d.querySelector("button")).focus();
  });
}

// ---------------------------------------------------------------- state line
function showState(msg, cls) {
  const s = $("state");
  s.textContent = msg;
  s.className = "state " + (cls || "");
}
function refreshState() {
  if (!cur) { showState(""); return; }
  $("save").disabled = !dirty();
  $("publish").disabled = false;
  const entry = list.find((p) => p.path === cur.path);
  if (dirty()) showState("Unsaved changes", "dirty");
  else if (cur.path.startsWith("drafts/")) showState("Draft, saved");
  else if (entry && entry.unpublished) showState("Saved, not yet live", "dirty");
  else showState("Live");
}

// ---------------------------------------------------------------- list
async function loadList() {
  list = (await api("GET", "/_api/list")).data;
  const make = (p) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.path = p.path;
    if (cur && cur.path === p.path) b.setAttribute("aria-current", "true");
    b.textContent = p.title;
    const small = document.createElement("small");
    small.textContent = [p.date || (p.kind === "drafts" ? "draft" : ""), p.hidden ? "hidden" : ""].filter(Boolean).join(" · ");
    if (p.unpublished) { const m = document.createElement("span"); m.className = "mark"; m.textContent = " · not yet live"; small.append(m); }
    b.append(small);
    b.addEventListener("click", () => openFile(p.path));
    li.append(b);
    return li;
  };
  $("drafts").replaceChildren(...list.filter((p) => p.kind === "drafts").map(make));
  $("posts").replaceChildren(...list.filter((p) => p.kind === "posts").map(make));
  refreshState();
}

// ---------------------------------------------------------------- open / save
async function openFile(path) {
  if (dirty()) {
    const v = await ask("Unsaved changes", `Save your changes to ${cur.path} first?`,
      [["Cancel", "cancel"], ["Discard", "discard"], ["Save", "save", "primary"]]);
    if (v === "cancel" || v === "") return;
    if (v === "save" && !(await save())) return;
    if (v === "discard") store.del(backupKey(cur.path));
  }
  let data;
  try { data = (await api("GET", "/_api/file?path=" + encodeURIComponent(path))).data; }
  catch (e) { ask("Couldn't open it", e.message, [["OK", "ok", "primary"]]); return; }
  cur = { path: data.path, hash: data.hash, slug: data.slug, saved: data.text };
  text.value = data.text;
  text.disabled = false;
  const backup = store.get(backupKey(path));
  if (backup && backup.text !== data.text) {
    const same = backup.hash === data.hash;
    const v = await ask("Unsaved edits found",
      same ? "This browser kept edits to this post that were never saved. Restore them?"
           : "This browser kept unsaved edits, but the file has changed on disk since. Restoring puts your old edits over the newer file.",
      [["Discard them", "no"], ["Restore", "yes", "primary"]]);
    if (v === "yes") text.value = backup.text;
    else store.del(backupKey(path));
  }
  location.hash = path;
  $("doc").textContent = titleOf(text.value) || path;
  document.title = (titleOf(text.value) || path) + " · jpain.io editor";
  const live = $("live");
  live.hidden = !path.startsWith("posts/");
  live.href = "https://jpain.io/" + slugOf(text.value, path) + "/";
  previewSlug = "";
  frame.removeAttribute("src");
  document.querySelectorAll(".files button").forEach((btn) => {
    if (btn.dataset.path === path) btn.setAttribute("aria-current", "true"); else btn.removeAttribute("aria-current");
  });
  setView(innerWidth <= 700 ? "write" : main.dataset.view === "list" ? "write" : main.dataset.view);
  refreshState();
  loadMedia();
  schedulePreview(0);
}

function titleOf(t) { const m = /^---\n[\s\S]*?^title:\s*(.*)$/m.exec(t); return m ? m[1].trim() : ""; }
function slugOf(t, path) {
  const m = /^---\n[\s\S]*?^(?:slug|link):\s*(\S+)/m.exec(t);
  return m ? m[1] : path.replace(/^.*\/|\.md$/g, "");
}

async function save(force) {
  if (!cur) return false;
  const body = { path: cur.path, text: text.value, hash: cur.hash, force: !!force };
  let r;
  try { r = await api("PUT", "/_api/file", body); }
  catch (e) { showState("Save failed: " + e.message, "bad"); return false; }
  if (r.status === 409) {
    const v = await ask("Changed on disk",
      "Someone changed this file since you opened it: a terminal, git or Claude. Keep your version, or load theirs? Your version stays in this browser's backup either way.",
      [["Cancel", "cancel"], ["Load theirs", "theirs"], ["Keep mine", "mine", "primary"]]);
    if (v === "mine") return save(true);
    if (v === "theirs") {
      cur.hash = r.data.hash; cur.saved = r.data.text; text.value = r.data.text;
      refreshState(); schedulePreview(0);
    }
    return false;
  }
  cur.hash = r.data.hash;
  cur.saved = body.text;
  store.del(backupKey(cur.path));
  const entry = list.find((p) => p.path === cur.path);
  if (entry) entry.unpublished = r.data.unpublished;
  await loadList();
  return true;
}

async function publish() {
  if (!cur) return;
  if (dirty() && !(await save())) return;
  const title = titleOf(text.value) || cur.path;
  const draft = cur.path.startsWith("drafts/");
  const v = await ask(draft ? "Publish this draft?" : "Publish your changes?",
    draft ? `"${title}" goes live on jpain.io, dated now.`
          : `Your saved changes to "${title}" go live on jpain.io. Anything else saved but unpublished in the site goes too.`,
    [["Cancel", "cancel"], ["Publish", "go", "primary"]]);
  if (v !== "go") return;
  $("publish").disabled = true;
  showState("Publishing…");
  let r;
  try { r = (await api("POST", "/_api/publish", { path: cur.path })).data; }
  catch (e) { r = { ok: false, log: e.message }; }
  if (r.ok) {
    await ask("Published", "It's live.", [["View it", "view"], ["OK", "ok", "primary"]], r.log)
      .then((x) => { if (x === "view") window.open("https://jpain.io/" + slugOf(text.value, cur.path) + "/", "_blank", "noopener"); });
    if (r.path !== cur.path) { cur.path = r.path; location.hash = r.path; $("live").hidden = false; }
  } else {
    await ask("Not published", "Nothing went live. " + (r.reason || "The reason is at the end of the log."), [["OK", "ok", "primary"]], r.log);
  }
  await loadList();
}

// ---------------------------------------------------------------- preview
function schedulePreview(delay) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, delay === undefined ? 600 : delay);
}
async function runPreview() {
  if (!cur) return;
  const seq = ++previewSeq;
  let r;
  try { r = (await api("POST", "/_api/preview", { path: cur.path, text: text.value })).data; }
  catch (e) { r = { ok: false, built: false, message: e.message }; }
  if (seq !== previewSeq) return;
  const c = $("checks");
  c.className = "checks " + (r.ok ? "ok" : "bad");
  c.textContent = r.ok ? "Checks pass" : r.message;
  if (!r.built) return;
  const url = `/${r.slug}/`;
  let y = 0;
  try { if (previewSlug === r.slug) y = frame.contentWindow.scrollY; } catch { /* not loaded yet */ }
  frame.addEventListener("load", () => { try { frame.contentWindow.scrollTo(0, y); } catch { /* ignore */ } }, { once: true });
  if (previewSlug === r.slug && frame.contentWindow) {
    try { frame.contentWindow.location.replace(url + "?v=" + seq); } catch { frame.src = url + "?v=" + seq; }
  } else {
    frame.src = url + "?v=" + seq;
  }
  previewSlug = r.slug;
}

// ---------------------------------------------------------------- images
async function loadMedia() {
  const box = $("media-box");
  box.hidden = !cur;
  if (!cur) return;
  const files = (await api("GET", "/_api/media?path=" + encodeURIComponent(cur.path))).data.files;
  $("media").replaceChildren(...files.filter((f) => /\.(webp|png|jpe?g|gif|svg|avif)$/i.test(f)).map((f) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = f;
    btn.title = "Insert " + f;
    btn.addEventListener("click", () => insertImage(f));
    li.append(btn);
    return li;
  }));
}
function insert(snippet) {
  const s = text.selectionStart, e = text.selectionEnd, v = text.value;
  const before = v.slice(0, s), after = v.slice(e);
  const pre = before && !before.endsWith("\n\n") ? (before.endsWith("\n") ? "\n" : "\n\n") : "";
  const post = after.startsWith("\n\n") ? "" : after.startsWith("\n") ? "\n" : "\n\n";
  text.focus();
  text.setRangeText(pre + snippet + post, s, e, "end");
  text.dispatchEvent(new Event("input"));
}
// Alt text is left empty on purpose: the checks fail until it's written.
function insertImage(name) { insert(`![](${name} "Caption")`); }

async function uploadFiles(files) {
  if (!cur) return;
  if (dirty() && !(await save())) return;   // the upload lands in the folder of the saved slug
  for (const f of files) {
    if (!f.type.startsWith("image/")) continue;
    showState("Adding " + (f.name || "image") + "…");
    try {
      const q = `?path=${encodeURIComponent(cur.path)}&name=${encodeURIComponent(f.name || "image")}`;
      const r = (await api("POST", "/_api/upload" + q, undefined, f)).data;
      insertImage(r.name);
      showState(`Added ${r.name}, ${r.width}×${r.height}, ${r.kb} KB`);
    } catch (e) {
      showState("Image failed: " + e.message, "bad");
    }
  }
  loadMedia();
}

// ---------------------------------------------------------------- views
function setView(v) {
  main.dataset.view = v;
  document.querySelectorAll(".views button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === v)));
  if (v === "preview") schedulePreview(0);
}

// ---------------------------------------------------------------- wiring
text.addEventListener("input", () => {
  if (!cur) return;
  store.set(backupKey(cur.path), { text: text.value, hash: cur.hash });
  $("doc").textContent = titleOf(text.value) || cur.path;
  refreshState();
  schedulePreview();
});
text.addEventListener("keydown", (e) => {
  if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey && text.selectionStart === text.selectionEnd) {
    e.preventDefault();
    text.setRangeText("  ", text.selectionStart, text.selectionEnd, "end");
    text.dispatchEvent(new Event("input"));
  }
});
text.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); text.classList.add("drop"); } });
text.addEventListener("dragleave", () => text.classList.remove("drop"));
text.addEventListener("drop", (e) => {
  text.classList.remove("drop");
  if (!e.dataTransfer.files.length) return;
  e.preventDefault();
  uploadFiles([...e.dataTransfer.files]);
});
text.addEventListener("paste", (e) => {
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
  if (files.length) { e.preventDefault(); uploadFiles(files); }
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (dirty()) save(); }
});
window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
$("save").addEventListener("click", () => save());
$("publish").addEventListener("click", publish);
$("upload").addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
document.querySelectorAll(".views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("new").addEventListener("click", async () => {
  const input = document.createElement("input");
  input.placeholder = "Post title";
  input.required = true;
  const v = await ask("New post", input, [["Cancel", "cancel"], ["Create draft", "create", "primary"]]);
  if (v !== "create" || !input.value.trim()) return;
  try {
    const r = (await api("POST", "/_api/new", { title: input.value })).data;
    await loadList();
    await openFile(r.path);
    text.focus();
    text.setSelectionRange(text.value.length, text.value.length);
  } catch (e) { ask("Couldn't create it", e.message, [["OK", "ok", "primary"]]); }
});

(async () => {
  setView(innerWidth <= 700 ? "list" : "write");
  await loadList();
  const want = decodeURIComponent(location.hash.slice(1));
  if (want && list.some((p) => p.path === want)) openFile(want);
})();
