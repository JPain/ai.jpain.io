// "Show email address" on About. The address is not in the page as text: it is encrypted with a
// key that only exists once the browser finds the first n where SHA-256("<challenge>:<n>") starts
// with enough zero bits (build.py contact_email). That takes about half a second on a desktop and
// a couple of seconds on a phone; address harvesters read the HTML and never run it.
const enc = new TextEncoder();
const sha256 = async (s) => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)));

function zeroBits(u8) {
  let n = 0;
  for (const b of u8) {
    if (b === 0) { n += 8; continue; }
    return n + Math.clz32(b) - 24;
  }
  return n;
}

async function reveal(button) {
  const line = button.closest(".contact");
  const status = line.querySelector(".pow-status");
  const { c, bits, x } = button.dataset;
  const need = Number(bits);
  if (!window.crypto?.subtle) {
    status.textContent = "Your browser can't show it here; LinkedIn works too.";
    return;
  }
  button.hidden = true;
  status.textContent = "Checking…";
  const BATCH = 512;
  let found = -1, slice = performance.now();
  for (let base = 0; found < 0; base += BATCH) {
    const hs = await Promise.all(Array.from({ length: BATCH }, (_, i) => sha256(`${c}:${base + i}`)));
    const i = hs.findIndex((h) => zeroBits(h) >= need);
    if (i >= 0) found = base + i;
    // Digest promises resolve as microtasks, which never let the page repaint; yield every ~40 ms.
    if (performance.now() - slice > 40) {
      await new Promise((r) => setTimeout(r, 0));
      slice = performance.now();
    }
  }
  const key = await sha256(`${c}:${found}:key`);
  const cipher = Uint8Array.from(atob(x), (ch) => ch.charCodeAt(0));
  const addr = new TextDecoder().decode(cipher.map((b, i) => b ^ key[i]));
  const a = document.createElement("a");
  a.href = "mailto:" + addr;
  a.textContent = addr;
  status.replaceWith(a);
  button.remove();
  a.focus();
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button.pow-start");
  if (b) reveal(b);
});
