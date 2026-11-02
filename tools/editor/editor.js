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
// ask(title, body, buttons, log, opts): body is text or a node; buttons are [label, value, class].
// opts.validate(value) returns an error to show instead of closing; opts.wide widens the dialog.
function ask(title, body, buttons, log, opts = {}) {
  const d = $("dialog");
  d.className = opts.wide ? "wide" : "";
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
  const err = document.createElement("p");
  err.className = "dlg-error";
  err.hidden = true;
  b.append(err);
  const primary = $("dlg-buttons").querySelector(".primary");
  if (primary && opts.validate) primary.addEventListener("click", (e) => {
    const msg = opts.validate(primary.value);
    if (msg) { e.preventDefault(); err.textContent = msg; err.hidden = false; }
  });
  b.addEventListener("input", () => { err.hidden = true; });
  // Enter in a one-line field means the main button, not the first one (Cancel).
  b.querySelectorAll("input").forEach((i) => i.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing && primary) { e.preventDefault(); primary.click(); }
  }));
  // Chrome can drop the text's cursor to the start when a dialog closes; put it back.
  const keep = [text.selectionStart, text.selectionEnd, text.scrollTop];
  return new Promise((resolve) => {
    d.addEventListener("close", () => {
      if (text.value.length >= keep[1]) { text.setSelectionRange(keep[0], keep[1]); text.scrollTop = keep[2]; }
      resolve(d.returnValue);
    }, { once: true });
    d.returnValue = "";
    d.showModal();
    const input = b.querySelector("input, textarea");
    (input || primary || d.querySelector("button")).focus();
  });
}

// A labelled form field for a dialog: field("Alt text", "input", {value, hint, required}).
function field(label, kind, o = {}) {
  const wrap = document.createElement("label");
  wrap.className = "field";
  const l = document.createElement("span");
  l.textContent = label;
  const i = document.createElement(kind);
  if (kind === "input") i.type = o.type || "text";
  i.value = o.value || "";
  if (o.placeholder) i.placeholder = o.placeholder;
  if (o.rows) i.rows = o.rows;
  wrap.append(l, i);
  if (o.hint) { const h = document.createElement("small"); h.textContent = o.hint; wrap.append(h); }
  wrap.input = i;
  return wrap;
}
const group = (...nodes) => { const f = document.createDocumentFragment(); f.append(...nodes); return f; };

// ---------------------------------------------------------------- state line
function showState(msg, cls) {
  const s = $("state");
  s.textContent = msg;
  s.className = "state " + (cls || "");
}
function refreshState() {
  document.querySelectorAll("#toolbar button").forEach((b) => { b.disabled = !cur && b.dataset.cmd !== "help"; });
  counts();
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

// ---------------------------------------------------------------- editing helpers
// Every change goes through edit(), which uses the browser's own text insertion where it can,
// so Ctrl+Z undoes toolbar changes like typing.
function edit(start, end, str, selStart, selEnd) {
  text.focus();
  text.setSelectionRange(start, end);
  let done = false;
  try { done = document.execCommand("insertText", false, str); } catch { /* old browser */ }
  if (!done || text.value.slice(start, start + str.length) !== str) {
    text.setRangeText(str, start, end, "end");
    text.dispatchEvent(new Event("input"));
  }
  const a = selStart === undefined ? start + str.length : selStart;
  text.setSelectionRange(a, selEnd === undefined ? a : selEnd);
}

// A block (image, video, table...) on its own, with a blank line either side.
// sel = [from, to] inside the snippet to select afterwards.
function insert(snippet, sel) {
  const s = text.selectionStart, e = text.selectionEnd, v = text.value;
  const before = v.slice(0, s), after = v.slice(e);
  const pre = before && !before.endsWith("\n\n") ? (before.endsWith("\n") ? "\n" : "\n\n") : "";
  const post = after.startsWith("\n\n") ? "" : after.startsWith("\n") ? "\n" : "\n\n";
  const at = s + pre.length;
  edit(s, e, pre + snippet + post, sel ? at + sel[0] : at + snippet.length, sel ? at + sel[1] : undefined);
}

function selection() {
  let s = text.selectionStart, e = text.selectionEnd;
  const v = text.value;
  while (e > s && /\s/.test(v[e - 1])) e--;       // a double-click takes the space after a word too
  while (s < e && /\s/.test(v[s])) s++;
  return [s, e, v.slice(s, e)];
}

// Bold, italic and code: wrap the selection, or unwrap it if it's wrapped already.
// With nothing selected, the word under the cursor is used; with no word, a placeholder.
function wrap(mark, placeholder) {
  let [s, e, sel] = selection();
  const v = text.value;
  if (s === e) {
    const word = /[\p{L}\p{N}_'-]*$/u.exec(v.slice(0, s))[0].length;
    const tail = /^[\p{L}\p{N}_'-]*/u.exec(v.slice(s))[0].length;
    if (word + tail) { s -= word; e += tail; sel = v.slice(s, e); }
  }
  const stars = mark[0] === "*";
  const run = (str, re) => (re.exec(str) || [""])[0].length;
  // How many marks sit just outside (or just inside) the selection.
  const outB = stars ? run(v.slice(0, s), /\*+$/) : v.slice(s - mark.length, s) === mark ? mark.length : 0;
  const outA = stars ? run(v.slice(e), /^\*+/) : v.slice(e, e + mark.length) === mark ? mark.length : 0;
  const has = (n) => stars ? (mark.length === 2 ? n >= 2 : n % 2 === 1) : n >= mark.length;
  if (has(Math.min(outB, outA))) {
    edit(s - mark.length, e + mark.length, sel, s - mark.length, e - mark.length);
    return;
  }
  const inB = stars ? run(sel, /^\*+/) : sel.startsWith(mark) ? mark.length : 0;
  const inA = stars ? run(sel, /\*+$/) : sel.endsWith(mark) ? mark.length : 0;
  if (sel.length > 2 * mark.length && has(Math.min(inB, inA))) {
    const inner = sel.slice(mark.length, sel.length - mark.length);
    edit(s, e, inner, s, s + inner.length);
    return;
  }
  const body = sel || placeholder;
  edit(s, e, mark + body + mark, s + mark.length, s + mark.length + body.length);
}

// Headings, quotes and lists: change the start of every line in the selection.
function lines(fn) {
  const v = text.value;
  const s = v.lastIndexOf("\n", text.selectionStart - 1) + 1;
  let endAt = text.selectionEnd;
  if (endAt > text.selectionStart && v[endAt - 1] === "\n") endAt--;
  let e = v.indexOf("\n", endAt);
  if (e < 0) e = v.length;
  const out = fn(v.slice(s, e).split("\n")).join("\n");
  const single = !v.slice(s, e).includes("\n");
  edit(s, e, out, single ? s + out.length : s, single ? undefined : s + out.length);
}
const LIST = /^(\s*)([-*+]|\d+[.)])\s+/;
function heading(level) {
  const mark = "#".repeat(level) + " ";
  lines((ls) => ls.map((l) => {
    const had = /^#{1,6}\s+/.exec(l);
    const bare = had ? l.slice(had[0].length) : l;
    return had && had[0].trim().length === level ? bare : mark + bare;
  }));
}
function prefix(kind) {
  lines((ls) => {
    const used = ls.filter((l) => l.trim());
    const is = { ul: (l) => /^\s*[-*+]\s+/.test(l), ol: (l) => /^\s*\d+[.)]\s+/.test(l), quote: (l) => /^>\s?/.test(l) }[kind];
    if (used.length && used.every(is)) return ls.map((l) => kind === "quote" ? l.replace(/^>\s?/, "") : l.replace(LIST, "$1"));
    let n = 0;
    return ls.map((l) => {
      if (!l.trim() && ls.length > 1) return l;
      if (kind === "quote") return "> " + l;
      const bare = l.replace(LIST, "$1");
      return (kind === "ul" ? "- " : `${++n}. `) + bare.trimStart();
    });
  });
}

// Enter in a list or quote starts the next item; Enter on an empty item ends the list.
function continueList(e) {
  if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  const s = text.selectionStart;
  if (s !== text.selectionEnd) return;
  const v = text.value;
  const ls = v.lastIndexOf("\n", s - 1) + 1;
  const line = v.slice(ls, s);
  if (/^\s*(```|~~~)/.test(line)) return;
  const m = /^(\s*)([-*+]|\d+[.)]|>)(\s+)(.*)$/.exec(line);
  if (!m || v.slice(s, v.indexOf("\n", s) < 0 ? v.length : v.indexOf("\n", s)).trim()) return;
  e.preventDefault();
  if (!m[4].trim()) { edit(ls, s, "\n"); return; }   // empty item: end the list, with a blank line after it
  const num = /^(\d+)([.)])$/.exec(m[2]);
  const next = num ? `${Number(num[1]) + 1}${num[2]}` : m[2];
  edit(s, s, "\n" + m[1] + next + m[3]);
}

const isUrl = (t) => /^(https?:\/\/|mailto:)\S+$/i.test(t.trim());
const mdText = (t) => t.replace(/([[\]\\])/g, "\\$1");
const mdTitle = (t) => t.includes('"') ? ` '${t.replace(/'/g, "’")}'` : ` "${t}"`;

async function link() {
  const [s, e, sel] = selection();
  const url = isUrl(sel) ? sel.trim() : "";
  const t = field("Text", "input", { value: url ? "" : sel, placeholder: "What the reader sees" });
  const u = field("Address", "input", { type: "url", value: url, placeholder: "https://…",
    hint: "To open it in a new tab, start the address with tab: (tab:https://…)" });
  const v = await ask("Link", group(t, u), [["Cancel", "cancel"], ["Add link", "ok", "primary"]], "",
    { validate: () => u.input.value.trim() ? "" : "Add the address the link goes to." });
  if (v !== "ok") { text.focus(); return; }
  const href = u.input.value.trim();
  const label = t.input.value.trim() || href.replace(/^tab:/, "");
  edit(s, e, `[${mdText(label)}](${href.replace(/[()\s]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0"))})`);
}

const TABLE = "| Column | Column |\n| --- | --- |\n| Cell | Cell |\n| Cell | Cell |";

function command(cmd) {
  if (!cur && cmd !== "help") return;
  switch (cmd) {
    case "bold": return wrap("**", "bold text");
    case "italic": return wrap("*", "italic text");
    case "code": return wrap("`", "code");
    case "link": return link();
    case "h2": return heading(2);
    case "h3": return heading(3);
    case "ul": case "ol": case "quote": return prefix(cmd);
    case "hr": return insert("---");
    case "table": return insert(TABLE, [2, 8]);
    case "pre": {
      const [s, e, sel] = selection();
      if (sel) return edit(s, e, "```\n" + sel + "\n```", s + 4, s + 4 + sel.length);
      return insert("```\n\n```", [4, 4]);
    }
    case "image": return $("upload").click();
    case "youtube": return video();
    case "help": {
      const t = $("help").content.cloneNode(true);
      return ask("Formatting", t, [["Close", "ok", "primary"]], "", { wide: true });
    }
  }
}

// ---------------------------------------------------------------- word count
function counts() {
  const st = $("status");
  if (!cur) { st.textContent = ""; return; }
  const body = text.value.replace(/^---\n[\s\S]*?\n---\n|^[\s\S]*?\n___\n/, "");
  const words = (body.match(/\S+/g) || []).length;
  st.textContent = `${words.toLocaleString("en-GB")} words · ${Math.max(1, Math.round(words / 230))} min read`;
}

// ---------------------------------------------------------------- images
let mediaFiles = [];
const mediaUrl = (name, kb) => `/_api/media/file?path=${encodeURIComponent(cur.path)}&name=${encodeURIComponent(name)}&v=${kb || 0}`;
const IMAGE = /\.(webp|png|jpe?g|gif|svg|avif)$/i;

async function loadMedia() {
  const box = $("media-box");
  box.hidden = !cur;
  if (!cur) return;
  const r = (await api("GET", "/_api/media?path=" + encodeURIComponent(cur.path))).data;
  mediaFiles = r.files.filter((f) => IMAGE.test(f)).map((f) => ({ name: f, kb: r.sizes[f] }));
  $("media").replaceChildren(...mediaFiles.map(({ name, kb }) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "thumb";
    btn.title = `Insert ${name} (${kb} KB)`;
    const img = document.createElement("img");
    img.src = mediaUrl(name, kb);
    img.alt = "";
    img.loading = "lazy";
    const label = document.createElement("span");
    label.className = "name";
    label.textContent = name;
    btn.append(img, label);
    btn.addEventListener("click", () => name.startsWith("youtube-") ? video(name.slice(8, -5)) : imageDialog(name));
    const badge = document.createElement("span");
    badge.className = "unused";
    badge.textContent = "not used";
    badge.dataset.name = name;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "del";
    del.textContent = "×";
    del.title = del.ariaLabel = "Delete " + name;
    del.addEventListener("click", () => deleteMedia(name));
    li.append(btn, badge, del);
    return li;
  }));
  markUnused();
}
function markUnused() {
  // A video's thumbnail (youtube-<id>.webp) is used when the text links that video.
  const used = (n) => text.value.includes(/^youtube-[\w-]{11}\.webp$/.test(n) ? n.slice(8, -5) : n);
  document.querySelectorAll(".media .unused").forEach((b) => { b.hidden = used(b.dataset.name); });
}

async function deleteMedia(name) {
  const badge = document.querySelector(`.media .unused[data-name="${CSS.escape(name)}"]`);
  const used = badge ? badge.hidden : text.value.includes(name);   // a hidden "not used" badge means used
  const v = await ask("Delete this image?",
    used ? `${name} is still in the post. Deleting it breaks that spot until you take it out of the text too.`
         : `${name} is deleted from this post's folder.`,
    [["Cancel", "cancel"], ["Delete", "del", "primary"]]);
  if (v !== "del") return;
  try { await api("DELETE", `/_api/media?path=${encodeURIComponent(cur.path)}&name=${encodeURIComponent(name)}`); }
  catch (e) { showState("Couldn't delete it: " + e.message, "bad"); }
  loadMedia();
  schedulePreview(0);
}

// Alt text is asked for every time: the checks fail without it.
async function imageDialog(name, info) {
  const img = document.createElement("img");
  img.className = "dlg-img";
  img.src = mediaUrl(name, info ? info.kb : (mediaFiles.find((f) => f.name === name) || {}).kb);
  img.alt = "";
  const alt = field("Alt text", "textarea", { rows: 2, placeholder: "What the image shows",
    hint: "Read out to people who can't see it, and shown if it doesn't load. Required." });
  const cap = field("Caption", "input", { placeholder: "Optional", hint: "Shown under the image." });
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = info ? `Added ${name}: ${info.width}×${info.height}, ${info.kb} KB, metadata removed.` : name;
  const v = await ask("Insert image", group(img, note, alt, cap), [["Cancel", "cancel"], ["Insert", "ok", "primary"]], "",
    { validate: () => alt.input.value.trim() ? "" : "Write the alt text first." });
  if (v !== "ok") { text.focus(); return; }
  const a = alt.input.value.trim().replace(/\s+/g, " ");
  const c = cap.input.value.trim();
  insert(`![${mdText(a)}](${name}${c ? mdTitle(c) : ""})`);
}

// The upload lands in the folder of the saved slug, so unsaved changes are saved first.
async function uploadFiles(files) {
  if (!cur) return;
  if (dirty() && !(await save())) return;
  for (const f of files) {
    if (!f.type.startsWith("image/")) continue;
    showState("Adding " + (f.name || "image") + "…");
    let r;
    try {
      const q = `?path=${encodeURIComponent(cur.path)}&name=${encodeURIComponent(f.name || "image")}`;
      r = (await api("POST", "/_api/upload" + q, undefined, f)).data;
      showState(`Added ${r.name}`);
    } catch (e) {
      showState("Image failed: " + e.message, "bad");
      continue;
    }
    await loadMedia();
    await imageDialog(r.name, r);
  }
  refreshState();
}

// ---------------------------------------------------------------- YouTube
async function video(id) {
  if (!cur) return;
  const [, , sel] = selection();
  const u = field("YouTube address", "input", { type: "url", value: id ? `https://youtu.be/${id}` : isUrl(sel) ? sel.trim() : "",
    placeholder: "https://www.youtube.com/watch?v=…", hint: "A start time in the address (?t=90) is kept." });
  const c = field("Caption", "input", { placeholder: "Optional", hint: "Shown under the video." });
  const p = document.createElement("p");
  p.className = "hint";
  p.textContent = "The post shows the video's thumbnail, saved with the post. Nothing loads from YouTube until a reader presses play.";
  const v = await ask("Embed a YouTube video", group(u, c, p), [["Cancel", "cancel"], ["Embed", "ok", "primary"]], "",
    { validate: () => /youtu\.?be/.test(u.input.value) ? "" : "Paste a YouTube video's address." });
  if (v !== "ok") { text.focus(); return; }
  if (dirty() && !(await save())) return;
  showState("Fetching the video's thumbnail…");
  let r;
  try { r = (await api("POST", "/_api/youtube", { path: cur.path, url: u.input.value.trim() })).data; }
  catch (e) { showState("Video failed: " + e.message, "bad"); return; }
  const title = r.title || "YouTube video";
  const url = `https://youtu.be/${r.id}${r.start ? "?t=" + r.start : ""}`;
  const cap = c.input.value.trim();
  const snippet = `[${mdText(title)}](${url}${cap ? mdTitle(cap) : ""}){.youtube}`;
  insert(snippet, r.title ? undefined : [1, 1 + title.length]);
  showState(r.title ? `Embedded "${r.title}"` : "YouTube didn't give the title: type it in place of the selected words", r.title ? "" : "dirty");
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
  markUnused();
  schedulePreview();
});
const KEYS = { b: "bold", i: "italic", k: "link", e: "code" };
text.addEventListener("keydown", (e) => {
  const mod = (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey;
  if (mod && KEYS[e.key.toLowerCase()]) { e.preventDefault(); command(KEYS[e.key.toLowerCase()]); return; }
  continueList(e);
  if (e.defaultPrevented) return;
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
  if (files.length) { e.preventDefault(); uploadFiles(files); return; }
  // An address pasted over selected words links them.
  const pasted = e.clipboardData?.getData("text/plain") || "";
  const [s, end, sel] = selection();
  if (sel && !sel.includes("\n") && !isUrl(sel) && isUrl(pasted)) {
    e.preventDefault();
    edit(s, end, `[${sel}](${pasted.trim()})`);
  }
});
$("toolbar").addEventListener("mousedown", (e) => { if (e.target.closest("button")) e.preventDefault(); });  // keep the text's selection
$("toolbar").addEventListener("click", (e) => { const b = e.target.closest("button[data-cmd]"); if (b) command(b.dataset.cmd); });
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (dirty()) save(); }
});
window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
$("save").addEventListener("click", () => save());
$("publish").addEventListener("click", publish);
$("upload").addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
document.querySelectorAll(".views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("new").addEventListener("click", async () => {
  const f = field("Title", "input", { placeholder: "Post title", hint: "You can change it later. The address comes from it." });
  const input = f.input;
  const v = await ask("New post", f, [["Cancel", "cancel"], ["Create draft", "create", "primary"]], "",
    { validate: () => input.value.trim() ? "" : "Give the post a title." });
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
