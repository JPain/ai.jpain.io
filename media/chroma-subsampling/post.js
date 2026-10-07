// This post's own script, moved from jpain.io's old site-wide site.js when the blogs merged (2026-10).

// 1. Live demos framed from this site (e.g. a row of /compression-lab/ in a post) say how
// tall they are, so the frame fits its content with no inner scrollbar. Only frames on
// this page, from this origin, are listened to.
addEventListener("message", (e) => {
  if (e.origin !== location.origin || typeof e.data?.labHeight !== "number") return;
  for (const f of document.querySelectorAll("iframe.demo")) {
    if (f.contentWindow === e.source) f.style.height = `${Math.min(e.data.labHeight, 4000)}px`;
  }
});

// 2. Hold to compare: a figure panel marked .hold shows its comparison image (data-b,
// usually the original) while pressed, by mouse, touch, or Space/Enter when focused.
// Flicking between two images in the same place shows differences far better than
// looking side to side.
function holdPanel(p, on) {
  const img = p.querySelector("img"), hint = p.querySelector(".hold-hint");
  p.dataset.a ??= img.getAttribute("src");
  img.src = on ? p.dataset.b : p.dataset.a;
  p.classList.toggle("holding", on);
  if (hint) hint.textContent = on ? "showing the original" : "hold to compare";
}
document.addEventListener("pointerdown", (e) => {
  const p = e.target.closest(".panel.hold"); if (!p) return;
  e.preventDefault(); holdPanel(p, true);
  const end = () => { holdPanel(p, false); removeEventListener("pointerup", end); removeEventListener("pointercancel", end); };
  addEventListener("pointerup", end); addEventListener("pointercancel", end);
});
document.addEventListener("contextmenu", (e) => { if (e.target.closest(".panel.hold")) e.preventDefault(); });
document.addEventListener("keydown", (e) => {
  const p = e.target.closest?.(".panel.hold");
  if (p && (e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); holdPanel(p, true); }
});
document.addEventListener("keyup", (e) => {
  const p = e.target.closest?.(".panel.hold");
  if (p && (e.key === " " || e.key === "Enter")) holdPanel(p, false);
});
// Fetch the comparison images early, so the first hold doesn't flash.
addEventListener("load", () => document.querySelectorAll(".panel.hold[data-b]").forEach((p) => { new Image().src = p.dataset.b; }));
