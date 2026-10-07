// Two live pieces for the post, both built from markup in the page:
//  - .ab-player: plays six renders of one clip in lockstep, switches between them without a gap,
//    and draws what is playing: the whole clip's waveform, a scrolling level trace and a live spectrum.
//    The current version (A) is always drawn in blue as the reference; the one you hear is orange.
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
  function cssVar(node, name) { return getComputedStyle(node).getPropertyValue(name).trim(); }
  function db(x) { return 20 * Math.log10(Math.max(x, 1e-9)); }

  // A canvas that keeps its backing store at the device's pixel density and reports its size in CSS pixels.
  function sharpCanvas(canvas) {
    var ctx = canvas.getContext("2d");
    var size = { w: 0, h: 0 };
    function fit() {
      var r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      size.w = r.width; size.h = r.height;
      canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    fit();
    return { ctx: ctx, size: size, fit: fit };
  }

  // ---- A/B player ----------------------------------------------------------------
  var COLUMNS = 900;          // resolution of the whole-clip waveform
  var HISTORY_S = 6;          // seconds shown in the scrolling level trace
  var LEVEL_MIN = -60;        // dBFS at the bottom of the level trace
  var F_LO = 40, F_HI = 16000, SPEC_MIN = -110, SPEC_MAX = -30;
  var BANDS = [               // shaded on the spectrum
    { lo: 40, hi: 80, label: "pops" },
    { lo: 5000, hi: 9000, label: "“s” sounds" }
  ];

  function envelope(buffer) {
    var d = buffer.getChannelData(0), per = Math.floor(d.length / COLUMNS), out = new Float32Array(COLUMNS);
    for (var c = 0; c < COLUMNS; c++) {
      var peak = 0;
      for (var i = c * per, end = i + per; i < end; i++) { var v = Math.abs(d[i]); if (v > peak) peak = v; }
      out[c] = peak;
    }
    return out;
  }

  // Level averaged over a centred 3-second window, every 0.1 s: the time scale loudness range works on.
  var SLOW_WIN = 3, SLOW_STEP = 0.1, SLOW_MIN = -32, SLOW_MAX = -16;
  function slowLevel(buffer) {
    var d = buffer.getChannelData(0), sr = buffer.sampleRate, n = d.length;
    var cum = new Float64Array(n + 1);
    for (var i = 0; i < n; i++) cum[i + 1] = cum[i] + d[i] * d[i];
    var half = Math.round(SLOW_WIN * sr / 2), out = [];
    for (var t = 0; t <= buffer.duration; t += SLOW_STEP) {
      var c = Math.round(t * sr), lo = Math.max(0, c - half), hi = Math.min(n, c + half);
      out.push([t, 10 * Math.log10((cum[hi] - cum[lo]) / Math.max(1, hi - lo) + 1e-15)]);
    }
    return out;
  }

  function setupPlayer(root) {
    var variants = Array.prototype.map.call(root.querySelectorAll("[data-src]"), function (b) {
      return { button: b, src: b.getAttribute("data-src"), key: b.getAttribute("data-key"),
               name: b.textContent, buffer: null, env: null, gain: null, analyser: null };
    });
    var ref = variants.filter(function (v) { return v.key === "a"; })[0];
    var playBtn = root.querySelector(".ab-play");
    var status = root.querySelector(".ab-status");
    var blindBtn = root.querySelector(".ab-blind");
    var blindBox = root.querySelector(".ab-blindbox");
    var xBtn = blindBox.querySelector(".ab-x"), yBtn = blindBox.querySelector(".ab-y");
    var reveal = blindBox.querySelector(".ab-reveal"), answer = blindBox.querySelector(".ab-answer");
    var wave = sharpCanvas(root.querySelector(".ab-wave"));
    var level = sharpCanvas(root.querySelector(".ab-level"));
    var spec = sharpCanvas(root.querySelector(".ab-spec"));
    var legend = root.querySelector(".ab-legend");
    var panels = Array.prototype.slice.call(root.querySelectorAll(".ab-panel"));
    function showPanels(on) { panels.forEach(function (p) { p.hidden = !on; }); if (on) { wave.fit(); level.fit(); spec.fit(); drawStatic(); } }

    var ctx = null, sources = [], startedAt = 0, offset = 0, playing = false, loading = null;
    var current = variants.indexOf(ref), blind = null, history = [], frame = null;
    var timeBuf = null, freqA = null, freqS = null, bandDiff = null;

    function selected() { return variants[current]; }
    function duration() { return ref.buffer ? ref.buffer.duration : 1; }
    function position() {
      if (!playing) return offset;
      return (ctx.currentTime - startedAt) % duration();
    }
    function label(v) {
      if (blind) return v === variants[blind.map[0]] ? "X" : "Y";
      return v.name;
    }

    function select(i) {
      current = i;
      variants.forEach(function (v, j) {
        if (!blind) v.button.setAttribute("aria-pressed", j === i ? "true" : "false");
        if (v.gain) v.gain.gain.setTargetAtTime(j === i ? 1 : 0, ctx.currentTime, 0.008);
      });
      bandDiff = null;
      drawLegend();
      drawStatic();
    }

    function load() {
      if (loading) return loading;
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      status.textContent = "Loading six clips…";
      loading = Promise.all(variants.map(function (v) {
        return fetch(v.src).then(function (r) { return r.arrayBuffer(); }).then(function (a) {
          return new Promise(function (ok, bad) { ctx.decodeAudioData(a, ok, bad); });
        }).then(function (b) {
          v.buffer = b; v.env = envelope(b); v.slow = slowLevel(b);
          v.analyser = ctx.createAnalyser();
          v.analyser.fftSize = 8192;
          v.analyser.smoothingTimeConstant = 0.8;
        });
      })).then(function () {
        timeBuf = new Float32Array(4096);
        freqA = new Float32Array(ref.analyser.frequencyBinCount);
        freqS = new Float32Array(ref.analyser.frequencyBinCount);
        status.textContent = "";
        drawStatic();
      });
      return loading;
    }

    function start() {
      sources = variants.map(function (v, j) {
        var s = ctx.createBufferSource();
        s.buffer = v.buffer; s.loop = true;
        v.gain = ctx.createGain();
        v.gain.gain.value = j === current ? 1 : 0;
        s.connect(v.gain).connect(ctx.destination);
        s.connect(v.analyser);          // every version is measured, heard or not
        return s;
      });
      var when = ctx.currentTime + 0.05;
      sources.forEach(function (s) { s.start(when, offset); });
      startedAt = when - offset;
      playing = true;
      playBtn.textContent = "Pause";
      if (!frame) frame = requestAnimationFrame(tick);
    }
    function stop() {
      offset = position();
      sources.forEach(function (s) { s.stop(); s.disconnect(); });
      sources = [];
      playing = false;
      playBtn.textContent = "Play";
    }
    function seek(t) {
      var was = playing;
      if (was) stop();
      offset = Math.max(0, Math.min(duration() - 0.01, t));
      history = [];
      if (was) start(); else drawStatic();
    }

    // ---- drawing ----
    function colours() {
      return { a: cssVar(root, "--s1"), s: cssVar(root, "--s2"), fg: cssVar(root, "--fg"),
               muted: cssVar(root, "--muted"), rule: cssVar(root, "--rule"), bg: cssVar(root, "--bg") };
    }
    function showRef() { return !blind && selected() !== ref; }

    function drawLegend() {
      legend.textContent = "";
      function item(cls, text) {
        var s = el("span"); s.appendChild(el("span", { "class": "key " + cls }));
        s.appendChild(document.createTextNode(text)); legend.appendChild(s);
      }
      item("s2", "Playing: " + label(selected()));
      if (showRef()) item("s1", "Reference: " + ref.name);
    }

    function drawWave(c) {
      var g = wave.ctx, w = wave.size.w, h = wave.size.h, mid = h / 2, padL = 34;
      g.clearRect(0, 0, w, h);
      if (!ref.env) {
        g.fillStyle = c.muted; g.font = "13px system-ui, sans-serif"; g.textAlign = "center";
        g.fillText("Press Play to load the clips", w / 2, mid + 4);
        return;
      }
      var X = function (t) { return padL + t / duration() * (w - padL); };
      var Y = function (v) { return 6 + (SLOW_MAX - Math.max(SLOW_MIN, Math.min(SLOW_MAX, v))) / (SLOW_MAX - SLOW_MIN) * (h - 12); };
      // The waveform of the version playing, faint, for finding your way around.
      var env = selected().env;
      g.fillStyle = c.rule; g.beginPath();
      for (var x = padL; x <= w; x++) { var v = env[Math.min(COLUMNS - 1, Math.floor((x - padL) / (w - padL) * COLUMNS))]; g.lineTo(x, mid - v * (mid - 4)); }
      for (x = w; x >= padL; x--) { v = env[Math.min(COLUMNS - 1, Math.floor((x - padL) / (w - padL) * COLUMNS))]; g.lineTo(x, mid + v * (mid - 4)); }
      g.closePath(); g.fill();
      g.font = "11px system-ui, sans-serif"; g.textAlign = "right"; g.fillStyle = c.muted;
      [-20, -28].forEach(function (v) {
        g.strokeStyle = c.rule; g.lineWidth = 1; g.setLineDash([3, 3]);
        g.beginPath(); g.moveTo(padL, Y(v)); g.lineTo(w, Y(v)); g.stroke(); g.setLineDash([]);
        g.fillText(v + "", padL - 4, Y(v) + 4);
      });
      function line(pts, colour) {
        g.strokeStyle = colour; g.lineWidth = 2.5; g.beginPath();
        pts.forEach(function (p, i) { if (i) g.lineTo(X(p[0]), Y(p[1])); else g.moveTo(X(p[0]), Y(p[1])); });
        g.stroke();
      }
      if (showRef()) line(ref.slow, c.a);
      line(selected().slow, c.s);
      var px = X(position());
      g.strokeStyle = c.fg; g.lineWidth = 2;
      g.beginPath(); g.moveTo(px, 0); g.lineTo(px, h); g.stroke();
    }

    function drawLevel(c) {
      var g = level.ctx, w = level.size.w, h = level.size.h, padL = 34;
      g.clearRect(0, 0, w, h);
      var Y = function (v) { return 4 + (Math.max(LEVEL_MIN, Math.min(0, v)) / LEVEL_MIN) * (h - 18); };
      g.font = "11px system-ui, sans-serif"; g.textAlign = "right"; g.fillStyle = c.muted; g.strokeStyle = c.rule; g.lineWidth = 1;
      [0, -20, -40, -60].forEach(function (v) {
        g.beginPath(); g.moveTo(padL, Y(v)); g.lineTo(w, Y(v)); g.stroke();
        g.fillText(v + "", padL - 4, Y(v) + 4);
      });
      g.textAlign = "left"; g.fillText("dB, last " + HISTORY_S + " s", padL + 4, h - 3);
      if (!history.length) return;
      var now = history[history.length - 1].t;
      var X = function (t) { return padL + (1 - (now - t) / HISTORY_S) * (w - padL); };
      function line(key, colour) {
        g.strokeStyle = colour; g.lineWidth = 2; g.beginPath();
        history.forEach(function (p, i) { if (i) g.lineTo(X(p.t), Y(p[key])); else g.moveTo(X(p.t), Y(p[key])); });
        g.stroke();
      }
      if (showRef()) line("a", c.a);
      line("s", c.s);
    }

    function drawSpec(c) {
      var g = spec.ctx, w = spec.size.w, h = spec.size.h, padL = 34, padB = 18;
      g.clearRect(0, 0, w, h);
      var lx = Math.log10(F_LO), hx = Math.log10(F_HI);
      var X = function (f) { return padL + (Math.log10(f) - lx) / (hx - lx) * (w - padL); };
      var Y = function (v) { return 4 + (SPEC_MAX - Math.max(SPEC_MIN, Math.min(SPEC_MAX, v))) / (SPEC_MAX - SPEC_MIN) * (h - padB - 4); };
      g.font = "11px system-ui, sans-serif";
      BANDS.forEach(function (b) {
        g.fillStyle = c.rule; g.globalAlpha = 0.6;
        g.fillRect(X(b.lo), 4, X(b.hi) - X(b.lo), h - padB - 4);
        g.globalAlpha = 1; g.fillStyle = c.muted; g.textAlign = "center";
        g.fillText(b.label, (X(b.lo) + X(b.hi)) / 2, 16);
      });
      g.strokeStyle = c.rule; g.lineWidth = 1; g.fillStyle = c.muted; g.textAlign = "center";
      [100, 300, 1000, 3000, 10000].forEach(function (f) {
        g.beginPath(); g.moveTo(X(f), 4); g.lineTo(X(f), h - padB); g.stroke();
        g.fillText(f >= 1000 ? f / 1000 + "k" : f + "", X(f), h - 4);
      });
      g.textAlign = "right"; g.fillText("Hz", padL - 4, h - 4);
      if (!playing || !freqA) return;
      var sr = ctx.sampleRate, n = freqA.length;
      ref.analyser.getFloatFrequencyData(freqA);
      selected().analyser.getFloatFrequencyData(freqS);
      function line(data, colour) {
        g.strokeStyle = colour; g.lineWidth = 2; g.beginPath();
        var started = false;
        for (var x = padL; x <= w; x += 2) {
          var f = Math.pow(10, lx + (x - padL) / (w - padL) * (hx - lx));
          var i = Math.round(f / (sr / 2) * n);
          var v = data[Math.min(n - 1, i)];
          if (started) g.lineTo(x, Y(v)); else { g.moveTo(x, Y(v)); started = true; }
        }
        g.stroke();
      }
      if (showRef()) line(freqA, c.a);
      line(freqS, c.s);
      // How far the playing version sits from A in the "s" band right now, smoothed.
      if (showRef()) {
        var lo = Math.round(5000 / (sr / 2) * n), hi = Math.round(9000 / (sr / 2) * n), pa = 0, ps = 0;
        for (var i = lo; i < hi; i++) { pa += Math.pow(10, freqA[i] / 10); ps += Math.pow(10, freqS[i] / 10); }
        var d = 10 * Math.log10(ps / pa);
        if (isFinite(d)) bandDiff = bandDiff == null ? d : bandDiff * 0.92 + d * 0.08;
        if (bandDiff != null) {
          g.fillStyle = c.fg; g.textAlign = "right";
          g.fillText("“s” band vs A: " + (bandDiff >= 0 ? "+" : "−") + Math.abs(bandDiff).toFixed(1) + " dB", w - 4, 30);
        }
      }
    }

    function drawStatic() {
      var c = colours();
      drawWave(c); drawLevel(c); drawSpec(c);
    }

    function tick() {
      frame = null;
      if (playing) {
        var t = position();
        if (history.length && t < history[history.length - 1].t - 1) history = [];   // looped
        var rms = function (an) {
          an.getFloatTimeDomainData(timeBuf);
          var s = 0; for (var i = 0; i < timeBuf.length; i++) s += timeBuf[i] * timeBuf[i];
          return db(Math.sqrt(s / timeBuf.length));
        };
        history.push({ t: t, a: rms(ref.analyser), s: rms(selected().analyser) });
        while (history.length && history[0].t < t - HISTORY_S) history.shift();
        if (!blind) status.textContent = Math.floor(t) + " s of " + Math.round(duration()) + " s, looping";
        drawStatic();
        frame = requestAnimationFrame(tick);
      }
    }

    playBtn.addEventListener("click", function () {
      load().then(function () {
        if (ctx.state === "suspended") ctx.resume();
        if (playing) stop(); else start();
        drawStatic();
      });
    });
    variants.forEach(function (v, i) {
      v.button.addEventListener("click", function () {
        if (blind) endBlind();
        load().then(function () {
          select(i);
          if (!playing) { if (ctx.state === "suspended") ctx.resume(); start(); }
        });
      });
    });

    // Click or drag on the waveform to move through the clip.
    var waveCanvas = root.querySelector(".ab-wave"), dragging = false;
    function seekFromEvent(e) {
      if (!ref.buffer) return;
      var r = waveCanvas.getBoundingClientRect();
      seek(Math.max(0, (e.clientX - r.left - 34) / (r.width - 34)) * duration());
    }
    waveCanvas.addEventListener("pointerdown", function (e) { dragging = true; waveCanvas.setPointerCapture(e.pointerId); seekFromEvent(e); });
    waveCanvas.addEventListener("pointerup", function () { dragging = false; });
    waveCanvas.addEventListener("pointermove", function (e) { if (dragging && !playing) seekFromEvent(e); });
    waveCanvas.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { seek(position() - 2); e.preventDefault(); }
      if (e.key === "ArrowRight") { seek(position() + 2); e.preventDefault(); }
    });

    // Blind mode: X and Y are A and B in a random order; the reader guesses which is the current chain.
    var bIndex = variants.map(function (v) { return v.key; }).indexOf("b");
    function blindPick(k) {
      xBtn.setAttribute("aria-pressed", k === 0 ? "true" : "false");
      yBtn.setAttribute("aria-pressed", k === 1 ? "true" : "false");
      select(blind.map[k]);
    }
    function endBlind() {
      blind = null;
      showPanels(true);
      blindBox.hidden = true;
      blindBtn.textContent = "Blind test";
    }
    blindBtn.addEventListener("click", function () {
      if (blind) { endBlind(); select(variants.indexOf(ref)); return; }
      var a = variants.indexOf(ref);
      blind = { map: Math.random() < 0.5 ? [bIndex, a] : [a, bIndex] };
      variants.forEach(function (v) { v.button.setAttribute("aria-pressed", "false"); });
      blindBox.hidden = false;
      showPanels(false);
      answer.textContent = "";
      blindBtn.textContent = "End blind test";
      status.textContent = "Blind test: X and Y are A and B in a random order. The visuals are hidden until you reveal the answer.";
      load().then(function () {
        blindPick(0);
        if (!playing) { if (ctx.state === "suspended") ctx.resume(); start(); }
      });
    });
    xBtn.addEventListener("click", function () { if (blind) blindPick(0); });
    yBtn.addEventListener("click", function () { if (blind) blindPick(1); });
    reveal.addEventListener("click", function () {
      if (!blind) return;
      answer.textContent = variants[blind.map[0]] === ref
        ? "X was A, the current chain. Y was B, the proposed one."
        : "X was B, the proposed chain. Y was A, the current one.";
      showPanels(true);
    });

    window.addEventListener("resize", function () { wave.fit(); level.fit(); spec.fit(); drawStatic(); });
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      if (mq.addEventListener) mq.addEventListener("change", drawStatic);
    }
    root.hidden = false;
    wave.fit(); level.fit(); spec.fit();
    drawLegend();
    drawStatic();
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
