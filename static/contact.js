// The email address on About sits behind a proof-of-work wall, like the "checking your browser"
// pages in front of much of the web now. Your browser hashes "<challenge>:<n>" for n = 0, 1, 2...
// until a SHA-256 starts with enough zero bits. The address is encrypted with a key made from that
// n (build.py contact_email), so nothing in the page reveals it until the work is done. Address
// harvesters read the HTML and move on; they never run this.
const enc = new TextEncoder();
const sha256 = async (s) => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)));
const hex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, "0")).join("");

function zeroBits(u8) {
  let n = 0;
  for (const b of u8) {
    if (b === 0) { n += 8; continue; }
    return n + Math.clz32(b) - 24;
  }
  return n;
}

function hashHtml(u8) {
  const h = hex(u8).slice(0, 24);
  const z = h.match(/^0*/)[0].length;
  return `<span class="zeros">${h.slice(0, z)}</span><span class="hash">${h.slice(z)}…</span>`;
}

async function prove(button) {
  const box = button.closest(".contact");
  const log = box.querySelector(".pow-log");
  const { c, bits, x } = button.dataset;
  const need = Number(bits);
  button.disabled = true;
  box.querySelector(".pow").hidden = false;
  if (!window.crypto?.subtle) {
    log.textContent = "This needs Web Crypto, which browsers only offer over HTTPS. Find me on LinkedIn instead.";
    return;
  }
  const head = `$ prove-human --sha256 --zero-bits ${need}\n` +
    `Every site wants proof you're human now. This one asks your computer to find a SHA-256 hash ` +
    `that starts with ${need} zero bits. There's no shortcut: it has to try one number after another.\n\n`;
  const t0 = performance.now();
  const BATCH = 512;
  let found = -1, best = null, slice = performance.now();
  for (let base = 0; found < 0; base += BATCH) {
    const hs = await Promise.all(Array.from({ length: BATCH }, (_, i) => sha256(`${c}:${base + i}`)));
    for (let i = 0; i < BATCH; i++) {
      if (zeroBits(hs[i]) >= need) { found = base + i; best = hs[i]; break; }
    }
    // Digest promises resolve as microtasks, so the loop never lets the page repaint on its own.
    // Every ~40 ms, show the counter and hand back to the browser for a frame.
    if (found < 0 && performance.now() - slice > 40) {
      log.innerHTML = head + `try ${(base + BATCH).toLocaleString("en-GB")}   ${hashHtml(hs[BATCH - 1])}`;
      await new Promise((r) => setTimeout(r, 0));
      slice = performance.now();
    }
  }
  const secs = ((performance.now() - t0) / 1000).toFixed(1);
  const key = await sha256(`${c}:${found}:key`);
  const cipher = Uint8Array.from(atob(x), (ch) => ch.charCodeAt(0));
  const addr = new TextDecoder().decode(cipher.map((b, i) => b ^ key[i]));
  log.innerHTML = head +
    `try ${(found + 1).toLocaleString("en-GB")}   ${hashHtml(best)}   found in ${secs} s\n\n` +
    `Proof accepted. It doesn't prove you're human, only that your device did some pointless work, ` +
    `which is all most of these checks prove. Bots that harvest email addresses don't wait around for it.`;
  const p = document.createElement("p");
  const a = document.createElement("a");
  a.href = "mailto:" + addr;
  a.textContent = addr;
  p.append("Email: ", a);
  button.closest("p").replaceWith(p);
  a.focus();
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button.pow-start");
  if (b) prove(b);
});
