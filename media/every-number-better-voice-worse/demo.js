// Two live pieces for the post, both built from markup in the page:
//  - .ab-player: plays five renders of one clip in lockstep and switches between them without a gap.
//  - .loudness-chart: draws loudness.json as an SVG line chart with a hover readout and a table view.
(function () {
  "use strict";
  var SVGNS = "http://www.w3.org/2000/svg";

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    return n;
  }

  // ---- A/B player ----------------------------------------------------------------
  function setupPlayer(root) {
    var variants = Array.prototype.map.call(root.querySelectorAll("[data-src]"), function (b) {
      return { button: b, src: b.getAttribute("data-src"), buffer: null, gain: null };
    });
    var playBtn = root.querySelector(".ab-play");
    var status = root.querySelector(".ab-status");
    var blindBtn = root.querySelector(".ab-blind");
    var ctx = null, sources = [], startedAt = 0, offset = 0, playing = false, current = 0, loading = null;
    var blind = null; // {map: [variantIndex, variantIndex], guess: null}

    function select(i) {
      current = i;
      variants.forEach(function (v, j) {
        v.button.setAttribute("aria-pressed", j === i ? "true" : "false");
        if (v.gain) v.gain.gain.setTargetAtTime(j === i ? 1 : 0, ctx.currentTime, 0.008);
      });
    }

    function load() {
      if (loading) return loading;
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      status.textContent = "Loading five clips…";
      loading = Promise.all(variants.map(function (v) {
        return fetch(v.src).then(function (r) { return r.arrayBuffer(); }).then(function (a) {
          return new Promise(function (ok, bad) { ctx.decodeAudioData(a, ok, bad); });
        }).then(function (b) { v.buffer = b; });
      })).then(function () { status.textContent = ""; });
      return loading;
    }

    function duration() { return variants[0].buffer.duration; }
    function position() { return playing ? (ctx.currentTime - startedAt) % duration() : offset; }

    function start() {
      sources = variants.map(function (v, j) {
        var s = ctx.createBufferSource();
        s.buffer = v.buffer; s.loop = true;
        v.gain = ctx.createGain();
        v.gain.gain.value = j === current ? 1 : 0;
        s.connect(v.gain).connect(ctx.destination);
        return s;
      });
      var when = ctx.currentTime + 0.05;
      sources.forEach(function (s) { s.start(when, offset); });
      startedAt = when - offset;
      playing = true;
      playBtn.textContent = "Pause";
      tick();
    }
    function stop() {
      offset = position();
      sources.forEach(function (s) { s.stop(); });
      sources = [];
      playing = false;
      playBtn.textContent = "Play";
    }
    function tick() {
      if (!playing) return;
      var t = position();
      if (!blind) status.textContent = Math.floor(t) + " s of " + Math.round(duration()) + " s, looping";
      requestAnimationFrame(tick);
    }

    playBtn.addEventListener("click", function () {
      load().then(function () {
        if (ctx.state === "suspended") ctx.resume();
        if (playing) stop(); else start();
      });
    });
    variants.forEach(function (v, i) {
      v.button.addEventListener("click", function () {
        if (blind) endBlind();
        select(i);
        if (!playing) playBtn.click();
      });
    });

    // Blind mode: X and Y are A and B in a random order; the reader guesses which is the original.
    var blindBox = root.querySelector(".ab-blindbox");
    var xBtn = blindBox.querySelector(".ab-x"), yBtn = blindBox.querySelector(".ab-y");
    var reveal = blindBox.querySelector(".ab-reveal"), answer = blindBox.querySelector(".ab-answer");
    function blindPick(k) {
      xBtn.setAttribute("aria-pressed", k === 0 ? "true" : "false");
      yBtn.setAttribute("aria-pressed", k === 1 ? "true" : "false");
      select(blind.map[k]);
      variants.forEach(function (v) { v.button.setAttribute("aria-pressed", "false"); });
    }
    function endBlind() {
      blind = null;
      blindBox.hidden = true;
      blindBtn.textContent = "Blind test";
    }
    blindBtn.addEventListener("click", function () {
      if (blind) { endBlind(); select(0); return; }
      var flip = Math.random() < 0.5;
      blind = { map: flip ? [1, 0] : [0, 1] };
      blindBox.hidden = false;
      answer.textContent = "";
      blindBtn.textContent = "End blind test";
      status.textContent = "Blind test: X and Y are A and B in a random order.";
      load().then(function () {
        blindPick(0);
        if (!playing) { if (ctx.state === "suspended") ctx.resume(); start(); }
      });
    });
    xBtn.addEventListener("click", function () { if (blind) blindPick(0); });
    yBtn.addEventListener("click", function () { if (blind) blindPick(1); });
    reveal.addEventListener("click", function () {
      if (!blind) return;
      answer.textContent = blind.map[0] === 0 ? "X was A, the current chain. Y was B, the proposed one."
                                              : "X was B, the proposed chain. Y was A, the current one.";
    });
    root.hidden = false;
    var fallback = root.parentNode.querySelector(".ab-noscript");
    if (fallback) fallback.hidden = true;
  }

  // ---- Loudness chart -----------------------------------------------------------
  function setupChart(root) {
    fetch(root.getAttribute("data-src")).then(function (r) { return r.json(); }).then(function (data) {
      var series = [
        { key: "a", name: "A, current", cls: "s1" },
        { key: "b", name: "B, proposed", cls: "s2" }
      ];
      var W = Math.max(340, Math.min(640, root.clientWidth || 640)), H = W < 500 ? 260 : 300;
      var m = { l: 40, r: W < 500 ? 70 : 92, t: 22, b: 30 };
      var x0 = 0, x1 = 120, y0 = -20, y1 = -8;
      var X = function (t) { return m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r); };
      var Y = function (v) { return m.t + (y1 - v) / (y1 - y0) * (H - m.t - m.b); };
      var s = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
        "aria-label": "Short-term loudness over two minutes. A swings between about -17 and -12 LUFS; B stays between about -15 and -13." });
      [-20, -16, -12, -8].forEach(function (v) {
        s.appendChild(svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), "class": "grid" }));
        var t = svg("text", { x: m.l - 6, y: Y(v) + 4, "class": "tick", "text-anchor": "end" });
        t.textContent = v; s.appendChild(t);
      });
      [0, 30, 60, 90, 120].forEach(function (v) {
        var t = svg("text", { x: X(v), y: H - m.b + 18, "class": "tick", "text-anchor": "middle" });
        t.textContent = v + " s"; s.appendChild(t);
      });
      var yl = svg("text", { x: 4, y: 10, "class": "tick" });
      yl.textContent = "LUFS"; s.appendChild(yl);
      series.forEach(function (se) {
        var pts = data[se.key];
        var d = pts.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join("");
        s.appendChild(svg("path", { d: d, "class": "line " + se.cls }));
      });
      // Direct labels at the right edge, nudged apart so they never overlap.
      var ends = series.map(function (se) { var p = data[se.key][data[se.key].length - 1]; return { se: se, y: Y(p[1]), x: X(p[0]) }; });
      ends.sort(function (u, v) { return u.y - v.y; });
      if (ends[1].y - ends[0].y < 16) { var mid = (ends[0].y + ends[1].y) / 2; ends[0].y = mid - 8; ends[1].y = mid + 8; }
      ends.forEach(function (e) {
        var lab = svg("text", { x: e.x + 6, y: e.y + 4, "class": "dlabel" });
        lab.textContent = e.se.key.toUpperCase(); s.appendChild(lab);
      });
      // Hover layer: crosshair and readout.
      var cross = svg("line", { y1: m.t, y2: H - m.b, "class": "cross" });
      cross.setAttribute("visibility", "hidden");
      s.appendChild(cross);
      var dots = series.map(function (se) {
        var c = svg("circle", { r: 4.5, "class": "dot " + se.cls });
        c.setAttribute("visibility", "hidden"); s.appendChild(c); return c;
      });
      var hit = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, "class": "hit" });
      s.appendChild(hit);
      var tip = el("div", { "class": "chart-tip", "aria-hidden": "true" });
      tip.hidden = true;
      function show(evt) {
        var r = s.getBoundingClientRect();
        var px = (evt.clientX - r.left) / r.width * W;
        var t = Math.max(x0, Math.min(x1, x0 + (px - m.l) / (W - m.l - m.r) * (x1 - x0)));
        var i = Math.max(0, Math.min(data.a.length - 1, Math.round((t - data.a[0][0]) * 2)));
        var p = data.a[i], q = data.b[i];
        cross.setAttribute("x1", X(p[0])); cross.setAttribute("x2", X(p[0]));
        cross.setAttribute("visibility", "visible");
        [p, q].forEach(function (pt, k) {
          dots[k].setAttribute("cx", X(pt[0])); dots[k].setAttribute("cy", Y(pt[1]));
          dots[k].setAttribute("visibility", "visible");
        });
        tip.textContent = "";
        tip.appendChild(el("strong", {}, p[0].toFixed(1) + " s"));
        [["A", p[1], "s1"], ["B", q[1], "s2"]].forEach(function (row) {
          var line = el("div");
          line.appendChild(el("span", { "class": "key " + row[2] }));
          line.appendChild(document.createTextNode(row[0] + " " + row[1].toFixed(1) + " LUFS"));
          tip.appendChild(line);
        });
        tip.hidden = false;
        var left = (X(p[0]) / W) * r.width;
        tip.style.left = Math.min(r.width - 130, Math.max(0, left + 12)) + "px";
        tip.style.top = "8px";
      }
      function hide() {
        tip.hidden = true; cross.setAttribute("visibility", "hidden");
        dots.forEach(function (d) { d.setAttribute("visibility", "hidden"); });
      }
      hit.addEventListener("pointermove", show);
      hit.addEventListener("pointerdown", show);
      hit.addEventListener("pointerleave", hide);
      var wrap = el("div", { "class": "chart-wrap" });
      wrap.appendChild(s); wrap.appendChild(tip);
      var legend = el("div", { "class": "chart-legend" });
      series.forEach(function (se) {
        var it = el("span"); it.appendChild(el("span", { "class": "key " + se.cls }));
        it.appendChild(document.createTextNode(se.name)); legend.appendChild(it);
      });
      var cap = root.querySelector("figcaption");
      root.insertBefore(legend, cap);
      root.insertBefore(wrap, cap);
      // Table view, every 5 seconds.
      var det = el("details", { "class": "chart-table" });
      det.appendChild(el("summary", {}, "Show the numbers as a table"));
      var tbl = el("table"), head = el("tr");
      ["Time", "A (LUFS)", "B (LUFS)"].forEach(function (h) { head.appendChild(el("th", {}, h)); });
      tbl.appendChild(head);
      data.a.forEach(function (p, i) {
        if (p[0] % 5 !== 0) return;
        var tr = el("tr");
        tr.appendChild(el("td", {}, p[0] + " s"));
        tr.appendChild(el("td", {}, p[1].toFixed(1)));
        tr.appendChild(el("td", {}, data.b[i][1].toFixed(1)));
        tbl.appendChild(tr);
      });
      det.appendChild(tbl);
      root.appendChild(det);
    });
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll(".ab-player"), setupPlayer);
    Array.prototype.forEach.call(document.querySelectorAll(".loudness-chart"), setupChart);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
