// Click (or Enter on) an image in a post to see it larger, over the page; click, Escape or ×
// to close. Only images shown smaller than their file are offered. build.py adds this script to
// posts with images. It listens on the whole page, so the editor's in-place preview works too.
"use strict";
(() => {
  // Plain Markdown images only (a <figure> build.py made, no class): demos have their own clicks.
  const candidate = (img) => img.matches(".e-content figure:not([class]) > img") && !img.closest("a");
  const mark = (img) => {
    if (!candidate(img) || !img.naturalWidth) return;
    const bigger = img.naturalWidth > img.clientWidth * 1.15;
    img.classList.toggle("zoomable", bigger);
    if (bigger) { img.tabIndex = 0; img.setAttribute("role", "button"); img.setAttribute("aria-label", `${img.alt || "Image"} (show larger)`); }
    else { img.removeAttribute("tabindex"); img.removeAttribute("role"); img.removeAttribute("aria-label"); }
  };
  const markAll = () => document.querySelectorAll(".e-content figure:not([class]) > img").forEach(mark);
  document.addEventListener("load", (e) => { if (e.target.tagName === "IMG") mark(e.target); }, true);
  let t = 0;
  addEventListener("resize", () => { clearTimeout(t); t = setTimeout(markAll, 150); });
  markAll();

  let box;
  const open = (img) => {
    if (!box) {
      box = document.createElement("dialog");
      box.className = "lightbox";
      box.innerHTML = '<button type="button" class="close" aria-label="Close">×</button><figure><img alt=""><figcaption></figcaption></figure>';
      box.addEventListener("click", () => box.close());
      document.body.append(box);
    }
    const big = box.querySelector("img");
    big.src = img.currentSrc || img.src;
    big.alt = img.alt;
    const cap = box.querySelector("figcaption");
    const fig = img.closest("figure");
    const fc = fig && fig.querySelector("figcaption");
    cap.replaceChildren();
    if (fc && fig.closest(".gallery")) {        // a gallery item: its own caption, not a figure number
      cap.append(...[...fc.cloneNode(true).childNodes]);
    } else if (fc) {
      const n = [...document.querySelectorAll(".e-content figure")]
        .filter((f) => f.querySelector(":scope > figcaption") && !f.closest(".gallery")).indexOf(fig) + 1;
      const b = document.createElement("b");
      b.textContent = `Figure ${n}. `;
      cap.append(b, fc.textContent);
    }
    cap.hidden = !fc;
    box.showModal();
  };
  document.addEventListener("click", (e) => {
    const img = e.target.closest && e.target.closest("img.zoomable");
    if (img && candidate(img)) open(img);
  });
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches("img.zoomable")) { e.preventDefault(); open(e.target); }
  });
})();
