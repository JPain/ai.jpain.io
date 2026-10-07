// Replays an invented delivery on a mock Nest Hub. The cards are real output of the
// card renderer, fed made-up inputs; the timing follows the service's own rules.
(function () {
  var root = document.getElementById('hub-demo');
  if (!root) return;
  var css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = 'hub-demo.css';
  document.head.appendChild(css);

  var img = root.querySelector('.hub-screen img');
  var overlay = root.querySelector('.hub-overlay');
  var log = root.querySelector('.hub-log');
  var count = root.querySelector('.hub-count');
  var playBtn = root.querySelector('[data-act=play]');
  var stepBtn = root.querySelector('[data-act=step]');
  var resetBtn = root.querySelector('[data-act=reset]');

  // kind: open (first cast: the one chime), card (silent swap), say (speech, then the card comes back), off
  var EVENTS = [
    { t: '0:00', kind: 'open', img: 'seq-0.webp', alt: '34 min, Ordered', text: 'first image cast: cast session opens, connect chime' },
    { t: '0:00', kind: 'say', text: 'speech: "Order placed"' },
    { t: '0:30', kind: 'card', img: 'seq-1.webp', alt: '29 min, Preparing', text: 'new image: stage changed' },
    { t: '0:30', kind: 'say', text: 'speech: "Order being prepared. About 29 minutes"' },
    { t: '5:00', kind: 'card', img: 'seq-2.webp', alt: '24 min, Preparing', text: 'new image: ETA crossed a 5-minute step' },
    { t: '10:00', kind: 'card', img: 'seq-3.webp', alt: '19 min, Preparing', text: 'new image: ETA crossed a 5-minute step' },
    { t: '15:00', kind: 'card', img: 'seq-4.webp', alt: '14 min, Preparing', text: 'new image: ETA crossed a 5-minute step' },
    { t: '19:10', kind: 'card', img: 'seq-5.webp', alt: 'map, 602 metres away, On its way', text: 'new image: rider on the move, map card' },
    { t: '19:10', kind: 'say', text: 'speech: "On its way. About 6 minutes"' },
    { t: '21:40', kind: 'card', img: 'seq-6.webp', alt: 'map, 350 metres away', text: 'new image: rider closer' },
    { t: '21:40', kind: 'say', text: 'speech: "About 350 metres away"' },
    { t: '22:30', kind: 'card', img: 'seq-7.webp', alt: 'map, 198 metres away', text: 'new image: rider closer' },
    { t: '23:20', kind: 'card', img: 'seq-8.webp', alt: 'map, 60 metres away, Nearby', text: 'new image: rider at the end of the road' },
    { t: '23:20', kind: 'say', text: 'speech: "Your order is arriving now"' },
    { t: '24:30', kind: 'off', text: 'order delivered: turn_off, the Hub goes back to its own screen' }
  ];

  var i = 0, timer = null, casts = 0, chimes = 0, current = 'seq-0.webp';

  function show(src, alt) {
    img.src = src;
    img.alt = 'Mock Nest Hub showing a status card: ' + alt;
    current = src;
  }
  function setOverlay(html) {
    if (html === null) { overlay.hidden = true; img.hidden = false; return; }
    overlay.innerHTML = html;
    overlay.hidden = false;
    img.hidden = true;
  }
  function updateCount() {
    count.textContent = 'new images: ' + casts + ' · connect chimes: ' + chimes;
  }
  function addLog(e) {
    var prev = log.querySelector('li.now');
    if (prev) prev.classList.remove('now');
    var li = document.createElement('li');
    li.className = 'now';
    var t = document.createElement('span');
    t.className = 't';
    t.textContent = e.t;
    li.appendChild(t);
    li.appendChild(document.createTextNode(e.text));
    log.appendChild(li);
    log.scrollTop = log.scrollHeight;
  }

  function step() {
    if (i >= EVENTS.length) { stop(); return false; }
    var e = EVENTS[i++];
    addLog(e);
    if (e.kind === 'open' || e.kind === 'card') {
      setOverlay(null);
      show(e.img, e.alt);
      casts++;
      if (e.kind === 'open') chimes++;
    } else if (e.kind === 'say') {
      var back = current;
      setOverlay('<div class="big">♪</div><div>' + e.text.replace(/^speech: /, '') + '</div>' +
                 '<div>(the speech plays in the same session; the card is cast again afterwards)</div>');
      // In the real thing the automation re-casts the card after the speech ends.
      window.setTimeout(function () { if (!overlay.hidden && current === back) setOverlay(null); }, 1100);
    } else if (e.kind === 'off') {
      setOverlay('<div class="big">The Hub’s own screen</div><div>cast session closed</div>');
    }
    updateCount();
    if (i >= EVENTS.length) stop();
    return true;
  }

  function stop() {
    if (timer) window.clearInterval(timer);
    timer = null;
    playBtn.textContent = 'Play';
    if (i >= EVENTS.length) { playBtn.disabled = true; stepBtn.disabled = true; }
  }
  function play() {
    if (timer) { stop(); return; }
    playBtn.textContent = 'Pause';
    step();
    timer = window.setInterval(step, 1800);
  }
  function reset() {
    stop();
    i = 0; casts = 0; chimes = 0;
    log.textContent = '';
    playBtn.disabled = false; stepBtn.disabled = false;
    setOverlay('<div class="big">Waiting for an order</div><div>press Play or Step</div>');
    updateCount();
  }

  playBtn.addEventListener('click', play);
  stepBtn.addEventListener('click', function () { stop(); step(); });
  resetBtn.addEventListener('click', reset);
  root.querySelector('.hub-bar').hidden = false;
  reset();
})();
