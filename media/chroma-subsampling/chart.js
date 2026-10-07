// The formats chart: file size against SSIMULACRA 2 score for the four copies the image
// host makes, drawn as SVG from the comparison lab's measurements (lab/curve.json, written
// by the lab's tools/curve.py). Hover or tap a point for its values; the numbered rings
// are the copies the host serves, by rank. "Show the numbers" gives the same data as a table.
(() => {
  const fig = document.querySelector("figure.demo-chart");
  if (!fig) return;
  const SVG = "http://www.w3.org/2000/svg";
  const SERIES = [   // colour follows the format; order fixed
    { k: "avif", name: "AVIF", long: "AVIF, full-resolution colour", q: (v) => `quality ${v}` },
    { k: "jxl", name: "JPEG XL", long: "JPEG XL", q: (v) => `distance ${v.toFixed(1)}` },
    { k: "webp", name: "WebP", long: "WebP, sharp YUV", q: (v) => `quality ${v}` },
    { k: "jpg", name: "JPEG", long: "JPEG, full-resolution colour", q: (v) => `quality ${v}` },
  ];
  // Laid out for the space it has: on a phone the drawing is narrower (not shrunk), so
  // text stays readable. Redrawn if the width crosses the line (e.g. rotating a phone).
  let W, H, M, sx, sy;
  const X = { min: 0, max: 320 }, Y = { min: 50, max: 92 };
  const layout = () => {
    const narrow = fig.clientWidth < 560;
    W = narrow ? 460 : 720; H = narrow ? 400 : 420;
    M = narrow ? { l: 44, r: 92, t: 14, b: 44 } : { l: 52, r: 118, t: 16, b: 46 };
    sx = (kb) => M.l + ((kb - X.min) / (X.max - X.min)) * (W - M.l - M.r);
    sy = (s) => H - M.b - ((s - Y.min) / (Y.max - Y.min)) * (H - M.t - M.b);
    return narrow;
  };
  const el = (tag, attrs = {}, text) => {
    const e = document.createElementNS(SVG, tag);
    for (const [a, v] of Object.entries(attrs)) e.setAttribute(a, v);
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const kb = (b) => b / 1024;

  fetch("lab/curve.json").then((r) => r.json()).then((data) => {
    let narrow = layout();
    const draw = () => {
    fig.querySelectorAll(".chart-legend, .chart-box, .chart-table").forEach((n) => n.remove());
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
      "aria-label": "File size against SSIMULACRA 2 score for AVIF, JPEG XL, WebP and JPEG on the test image, with the 79.9 half-resolution colour ceiling and the four copies the host serves marked 1 to 4." });
    // grid and axes: recessive
    for (let s = 50; s <= 90; s += 10) {
      svg.append(el("line", { x1: M.l, x2: W - M.r, y1: sy(s), y2: sy(s), class: "grid" }));
      svg.append(el("text", { x: M.l - 8, y: sy(s) + 4, class: "tick", "text-anchor": "end" }, s));
    }
    for (let v = 0; v <= 300; v += narrow ? 100 : 50) {
      svg.append(el("line", { x1: sx(v), x2: sx(v), y1: H - M.b, y2: H - M.b + 5, class: "axis" }));
      svg.append(el("text", { x: sx(v), y: H - M.b + 20, class: "tick", "text-anchor": "middle" }, `${v}`));
    }
    svg.append(el("line", { x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, class: "axis" }));
    svg.append(el("text", { x: M.l + (W - M.l - M.r) / 2, y: H - 6, class: "axis-title", "text-anchor": "middle" }, "File size, KB"));
    svg.append(el("text", { x: 14, y: M.t + (H - M.t - M.b) / 2, class: "axis-title", "text-anchor": "middle",
      transform: `rotate(-90 14 ${M.t + (H - M.t - M.b) / 2})` }, "SSIMULACRA 2 score"));
    // the ceiling for half-resolution colour
    svg.append(el("line", { x1: M.l, x2: W - M.r, y1: sy(data.ceiling), y2: sy(data.ceiling), class: "ceiling" }));
    // labelled in the right margin, where no line runs
    svg.append(el("text", { x: W - M.r + 8, y: sy(data.ceiling) + 4, class: "ceiling-label" }, `${data.ceiling} ceiling`));
    svg.append(el("text", { x: W - M.r + 8, y: sy(data.ceiling) + 19, class: "ceiling-label" }, narrow ? "half-res" : "half-res colour"));

    const points = [];
    const ends = [];
    SERIES.forEach((s, i) => {
      const pts = data.points[s.k].map((p) => ({ ...p, s, x: sx(kb(p.bytes)), y: sy(p.score) }))
        .sort((a, b) => a.x - b.x);
      svg.append(el("polyline", { points: pts.map((p) => `${p.x},${p.y}`).join(" "), class: `line s${i + 1}` }));
      pts.forEach((p) => { svg.append(el("circle", { cx: p.x, cy: p.y, r: 4, class: `dot s${i + 1}` })); points.push(p); });
      ends.push({ s, i, p: pts[pts.length - 1] });
    });
    // the four served copies: a badge on the line, numbered by rank, ringed in its colour
    SERIES.forEach((s, i) => {
      const p = points.find((q) => q.s === s && q.q === data.served[s.k]);
      p.served = true;
      svg.append(el("circle", { cx: p.x, cy: p.y, r: 10, class: `served s${i + 1}` }));
      svg.append(el("text", { x: p.x, y: p.y + 4.5, class: "served-num", "text-anchor": "middle" }, i + 1));
    });
    // direct labels at each line's end, in text ink, spaced apart vertically
    ends.sort((a, b) => a.p.y - b.p.y);
    let last = -Infinity;
    for (const e of ends) {
      const y = Math.max(e.p.y + 4, last + 16); last = y;
      svg.append(el("text", { x: e.p.x + (e.p.served ? 16 : 10), y, class: "end-label" }, e.s.name));
    }
    // hover: nearest point within reach, crosshair + tooltip
    const cross = el("g", { class: "cross", visibility: "hidden" });
    const vline = el("line", { y1: M.t, y2: H - M.b }), ring = el("circle", { r: 7 });
    cross.append(vline, ring); svg.append(cross);
    const tip = document.createElement("div"); tip.className = "chart-tip"; tip.hidden = true;
    const box = document.createElement("div"); box.className = "chart-box"; box.append(svg, tip);
    const show = (evt) => {
      const r = svg.getBoundingClientRect(), f = W / r.width;
      const mx = (evt.clientX - r.left) * f, my = (evt.clientY - r.top) * f;
      let best = null, bd = 40 * 40;
      for (const p of points) { const d = (p.x - mx) ** 2 + (p.y - my) ** 2; if (d < bd) { bd = d; best = p; } }
      if (!best) { cross.setAttribute("visibility", "hidden"); tip.hidden = true; return; }
      vline.setAttribute("x1", best.x); vline.setAttribute("x2", best.x);
      ring.setAttribute("cx", best.x); ring.setAttribute("cy", best.y);
      cross.setAttribute("visibility", "visible");
      const rank = data.served[best.s.k] === best.q ? ` · served, rank ${SERIES.indexOf(best.s) + 1}` : "";
      tip.textContent = `${best.s.long}, ${best.s.q(best.q)}: ${kb(best.bytes).toFixed(1)} KB, score ${best.score}${rank}`;
      tip.hidden = false;
      const left = best.x / f, top = best.y / f;
      tip.style.left = `${Math.min(Math.max(left, 90), r.width - 90)}px`;
      tip.style.top = `${top}px`;
    };
    svg.addEventListener("pointermove", show);
    svg.addEventListener("pointerdown", show);
    svg.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; });

    // legend (identity is never colour alone: legend + direct labels) and the table view
    const legend = document.createElement("p"); legend.className = "chart-legend";
    SERIES.forEach((s, i) => {
      const item = document.createElement("span");
      const sw = document.createElement("i"); sw.className = `sw s${i + 1}`;
      item.append(sw, s.long); legend.append(item);
    });
    const details = document.createElement("details"); details.className = "chart-table";
    const sum = document.createElement("summary"); sum.textContent = "Show the numbers";
    const rows = SERIES.flatMap((s) => data.points[s.k].map((p) =>
      `<tr><td>${s.long}</td><td>${s.q(p.q)}</td><td>${kb(p.bytes).toFixed(1)}</td><td>${p.score}</td></tr>`)).join("");
    details.append(sum);
    details.insertAdjacentHTML("beforeend", `<table><thead><tr><th>Format</th><th>Setting</th><th>KB</th><th>Score</th></tr></thead><tbody>${rows}</tbody></table>`);
    fig.querySelector(".chart-fallback")?.remove();
    fig.prepend(legend, box);
    fig.append(details);
    };
    draw();
    addEventListener("resize", () => { const n = fig.clientWidth < 560; if (n !== narrow) { narrow = layout(); draw(); } });
  }).catch(() => { /* the fallback text stays */ });
})();
