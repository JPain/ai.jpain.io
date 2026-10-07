// Live chroma subsampling: the post's 4:4:4 / 4:2:2 / 4:2:0 figure, computed in the browser.
// The reader picks one of four 64 x 32 areas (the health gauge is the default, James' choice
// 2026-09-28; the areas are buttons rather than a clickable overview, to save space) and a
// 4 x 2 block inside it: the most colourful block is picked automatically, and clicking the
// enlarged area moves it. Each area is cut from the comparison page's lossless 960 x 540
// overview (lab/frame.png), so nothing new is published and no lossy step has halved the colour.
// Each pixel keeps its own brightness (Y); the colour (Cb, Cr) is averaged over 1, 2 or 4
// pixels, then everything goes back to RGB, as a decoder would show it. Full-range BT.601,
// the conversion JPEG uses. Without JavaScript the static figure stays.
(() => {
  const fig = document.querySelector("figure.demo-sub");
  if (!fig) return;
  const SCHEMES = {
    "4:4:4": { w: 1, h: 1, note: "every pixel keeps its own colour" },
    "4:2:2": { w: 2, h: 1, note: "each side-by-side pair shares a colour" },
    "4:2:0": { w: 2, h: 2, note: "each 2 × 2 square shares a colour" },
  };
  // Areas where a search found blocks whose 8 pixels, 4 pairs and two 2 x 2 squares all differ
  // in colour, so every scheme looks different. Files are 64 x 32 crops of lab/frame.png at
  // even coordinates: gauge (22, 460), van (726, 450), branches (370, 198), trees (74, 96).
  const PRESETS = [
    { id: "gauge", label: "Health gauge", file: "sub-gauge.png", desc: "the red health-gauge ring on grey" },
    { id: "van", label: "Van window", file: "sub-van.png", desc: "the van's window, trim and interior" },
    { id: "branches", label: "Pine branches", file: "sub-branches.png", desc: "pine branches against the sky" },
    { id: "trees", label: "Tree line", file: "sub-trees.png", desc: "a tree line against the sky" },
  ];
  const CW = 64, CH = 32, ZOOM = 8;

  const toYcc = (r, g, b) => [
    0.299 * r + 0.587 * g + 0.114 * b,
    128 - 0.168736 * r - 0.331264 * g + 0.5 * b,
    128 + 0.5 * r - 0.418688 * g - 0.081312 * b,
  ];
  const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
  const toRgb = (y, cb, cr) => [
    clamp(y + 1.402 * (cr - 128)),
    clamp(y - 0.344136 * (cb - 128) - 0.714136 * (cr - 128)),
    clamp(y + 1.772 * (cb - 128)),
  ];
  const even = (v) => v - (v % 2);
  const within = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // Apply a scheme to RGBA pixels of width w, height h. Returns the recombined pixels and,
  // per pixel, the colour it was given (Cb, Cr) for drawing the colour layer alone.
  function subsample(src, w, h, s) {
    const out = new Uint8ClampedArray(src.length), chroma = [], ycc = [];
    for (let i = 0; i < w * h; i++) ycc.push(toYcc(src[i * 4], src[i * 4 + 1], src[i * 4 + 2]));
    for (let by = 0; by < h; by += s.h) for (let bx = 0; bx < w; bx += s.w) {
      let cb = 0, cr = 0, n = 0;
      for (let y = by; y < by + s.h && y < h; y++) for (let x = bx; x < bx + s.w && x < w; x++) {
        const p = ycc[y * w + x]; cb += p[1]; cr += p[2]; n++;
      }
      cb /= n; cr /= n;
      for (let y = by; y < by + s.h && y < h; y++) for (let x = bx; x < bx + s.w && x < w; x++) {
        const i = y * w + x;
        out.set([...toRgb(ycc[i][0], cb, cr), 255], i * 4);
        chroma[i] = [cb, cr];
      }
    }
    return { px: out, chroma };
  }

  // The most colourful 4 x 2 block in a crop: the one whose closest pair of pixels, closest
  // pair of side-by-side pairs, and two 2 x 2 squares are all as far apart in colour as possible.
  function bestBlock(src) {
    const C = (x, y) => { const i = (y * CW + x) * 4; const [, cb, cr] = toYcc(src[i], src[i + 1], src[i + 2]); return [cb, cr]; };
    const d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
    const mean = (ps) => [ps.reduce((s, p) => s + p[0], 0) / ps.length, ps.reduce((s, p) => s + p[1], 0) / ps.length];
    let best = { x: even(CW / 2 - 2), y: even(CH / 2 - 1), score: -1 };
    for (let y = 2; y <= CH - 4; y += 2) for (let x = 2; x <= CW - 6; x += 2) {
      const px = [], pairs = [];
      for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) px.push(C(x + c, y + r));
      for (let r = 0; r < 2; r++) for (let k = 0; k < 2; k++) pairs.push(mean([px[r * 4 + 2 * k], px[r * 4 + 2 * k + 1]]));
      const sq = [mean([px[0], px[1], px[4], px[5]]), mean([px[2], px[3], px[6], px[7]])];
      let d444 = Infinity, d422 = Infinity;
      for (let i = 0; i < 8; i++) for (let j = i + 1; j < 8; j++) d444 = Math.min(d444, d(px[i], px[j]));
      for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) d422 = Math.min(d422, d(pairs[i], pairs[j]));
      const score = Math.min(d(sq[0], sq[1]) / 40, d422 / 15, d444 / 6);
      if (score > best.score) best = { x, y, score };
    }
    return best;
  }

  let block = { x: 0, y: 0 }, scheme = "4:2:0", preset = PRESETS[0];
  let src = null;                                     // the current 64 x 32 crop's pixels

  // Each crop is decoded once into RGBA pixels and kept.
  const base = document.baseURI.replace(/[^/]*$/, ""), cache = {};
  const load = (p) => cache[p.id] ??= (async () => {
    const img = new Image(); img.src = new URL(p.file, base).href; await img.decode();
    const c = document.createElement("canvas"); c.width = CW; c.height = CH;
    const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(img, 0, 0);
    return x.getImageData(0, 0, CW, CH).data;
  })();

  function build() {
    fig.classList.add("live");
    fig.innerHTML = `
      <div class="sub-controls">
        <div class="sub-group" role="group" aria-label="Picture area"><span class="sub-glab">Area</span>
          ${PRESETS.map((p) => `<button type="button" data-a="${p.id}">${p.label}</button>`).join("")}</div>
        <div class="sub-group" role="group" aria-label="Chroma subsampling scheme"><span class="sub-glab">Colour</span>
          ${Object.keys(SCHEMES).map((k) => `<button type="button" data-s="${k}">${k}</button>`).join("")}</div>
      </div>
      <div class="sub-eq" aria-hidden="true">
        <div class="sub-block" data-k="y"></div><span class="sub-op">+</span><div class="sub-block" data-k="c"></div><span class="sub-op">=</span><div class="sub-block" data-k="p"></div>
        <span class="sub-lab">Brightness<br><small>0–255, one per pixel</small></span><span></span><span class="sub-lab">Colour<br><small data-n></small></span><span></span><span class="sub-lab">Pixels you see<br><small>the outlined block</small></span>
      </div>
      <div class="sub-swatches" aria-hidden="true"></div>
      <div class="sub-crop"><canvas width="${CW * ZOOM}" height="${CH * ZOOM}" tabindex="0"></canvas>
        <p class="sub-hint">Click anywhere in the enlarged area to move the 4 × 2 block.</p></div>
      <figcaption></figcaption>`;
    const grid = (k) => fig.querySelector(`.sub-block[data-k="${k}"]`);
    const cap = fig.querySelector("figcaption"), count = fig.querySelector("small[data-n]");
    const swatches = fig.querySelector(".sub-swatches");
    const canvas = fig.querySelector(".sub-crop canvas"), ctx = canvas.getContext("2d");
    canvas.setAttribute("role", "img");

    function show() {
      const s = SCHEMES[scheme], { px, chroma } = subsample(src, CW, CH, s);
      // the enlarged crop, one square per pixel, and the 4 x 2 block outlined
      for (let y = 0; y < CH; y++) for (let x = 0; x < CW; x++) {
        const i = (y * CW + x) * 4;
        ctx.fillStyle = `rgb(${px[i]},${px[i + 1]},${px[i + 2]})`;
        ctx.fillRect(x * ZOOM, y * ZOOM, ZOOM, ZOOM);
      }
      for (const [lw, colour] of [[4, "rgba(0,0,0,.7)"], [2, "#fff"]]) {   // dark then light, visible on any colour
        ctx.lineWidth = lw; ctx.strokeStyle = colour;
        ctx.strokeRect(block.x * ZOOM - 2, block.y * ZOOM - 2, 4 * ZOOM + 4, 2 * ZOOM + 4);
      }
      // The 4 x 2 block taken apart: brightness (Y, kept for every pixel, the same under every
      // scheme) + colour (Cb/Cr, one value per group, drawn at an even brightness so only the
      // colour shows) = the decoded pixels outlined in the crop. Heavy outlines mark the groups.
      const at = (k) => (block.y + Math.floor(k / 4)) * CW + block.x + (k % 4);
      const cells = (fill) => Array.from({ length: 8 }, (_, k) => {
        const c = document.createElement("span"); c.style.backgroundColor = `rgb(${fill(at(k)).join(",")})`; return c;
      });
      const outlines = () => {
        const out = [];
        for (let gy = 0; gy < 2; gy += s.h) for (let gx = 0; gx < 4; gx += s.w) {
          const g = document.createElement("b");
          Object.assign(g.style, { left: `${gx * 25}%`, top: `${gy * 50}%`, width: `${s.w * 25}%`, height: `${s.h * 50}%` });
          out.push(g);
        }
        return out;
      };
      const yOf = (i) => toYcc(src[i * 4], src[i * 4 + 1], src[i * 4 + 2])[0];
      grid("y").replaceChildren(...cells((i) => { const v = clamp(yOf(i)); return [v, v, v]; }));
      // each brightness value (0-255) in its square: the differences are why pixels that
      // share one colour look almost, but not quite, the same
      grid("y").querySelectorAll("span").forEach((c, k) => {
        const v = clamp(yOf(at(k))); c.textContent = v; c.style.color = v > 140 ? "#000" : "#fff";
      });
      grid("c").replaceChildren(...cells((i) => toRgb(128, ...chroma[i])), ...outlines());
      grid("p").replaceChildren(...cells((i) => [px[i * 4], px[i * 4 + 1], px[i * 4 + 2]]), ...outlines());
      const n = (4 / s.w) * (2 / s.h);
      count.textContent = `${n} value${n === 1 ? "" : "s"} for 8 pixels`;
      // the palette: each stored colour sample, lit at its pixels' average brightness so it
      // looks like the pixels it paints
      const chips = [];
      for (let gy = 0; gy < 2; gy += s.h) for (let gx = 0; gx < 4; gx += s.w) {
        let yy = 0;
        for (let dy = 0; dy < s.h; dy++) for (let dx = 0; dx < s.w; dx++) yy += yOf(at((gy + dy) * 4 + gx + dx));
        const chip = document.createElement("i");
        chip.style.backgroundColor = `rgb(${toRgb(yy / (s.w * s.h), ...chroma[at(gy * 4 + gx)]).join(",")})`;
        chips.push(chip);
      }
      const lab = document.createElement("span");
      lab.textContent = `${n} colour sample${n === 1 ? "" : "s"} stored`;
      swatches.replaceChildren(lab, ...chips);
      const where = preset.desc;
      const kept = (CW / s.w) * (CH / s.h);
      cap.textContent = `${scheme}: ${s.note}. Top, the 4 × 2 block outlined in the enlarged area, taken apart: every pixel ` +
        `keeps its own brightness, the colour is stored ${n} time${n === 1 ? "" : "s"} for its 8 pixels (drawn at an even ` +
        `brightness, heavy lines grouping the pixels that share one), and together they make the pixels you see. ` +
        `That is why pixels sharing one colour still look slightly different. Below, ${where}, enlarged 8 times, as a ` +
        `decoder shows it: ${kept.toLocaleString("en-GB")} colour values for 2,048 pixels.`;
      canvas.setAttribute("aria-label", `${where[0].toUpperCase() + where.slice(1)}, enlarged eight times, with colour stored as ${scheme}. Click to move the 4 by 2 block.`);
      fig.querySelectorAll("button[data-s]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.s === scheme)));
      fig.querySelectorAll("button[data-a]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.a === preset.id)));
    }

    fig.querySelector(".sub-controls").addEventListener("click", async (e) => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.s) { scheme = b.dataset.s; return show(); }
      const p = PRESETS.find((q) => q.id === b.dataset.a); if (!p || p === preset) return;
      try { src = await load(p); preset = p; block = bestBlock(src); show(); } catch { /* keep the current area */ }
    });
    // move the block: click inside the enlarged area; arrow keys move it two pixels
    const placeBlock = (x, y) => { block = { x: within(even(x), 0, CW - 4), y: within(even(y), 0, CH - 2) }; show(); };
    canvas.addEventListener("click", (e) => {
      const r = canvas.getBoundingClientRect();
      placeBlock(Math.floor(((e.clientX - r.left) / r.width) * CW) - 1, Math.floor(((e.clientY - r.top) / r.height) * CH));
    });
    canvas.addEventListener("keydown", (e) => {
      const step = { ArrowLeft: [-2, 0], ArrowRight: [2, 0], ArrowUp: [0, -2], ArrowDown: [0, 2] }[e.key];
      if (!step) return;
      e.preventDefault(); placeBlock(block.x + step[0], block.y + step[1]);
    });
    block = bestBlock(src);
    show();
  }

  load(preset).then((d) => {
    src = d;
    build();
    PRESETS.slice(1).forEach((p) => load(p).catch(() => {}));   // fetch the others early, so switching is instant
  }).catch(() => { /* keep the static figure */ });
})();
