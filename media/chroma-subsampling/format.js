// "Which format did your browser get?" The image's address ends in .jpg, and the server
// (nginx, as on James' image host) sends the best of four copies that this browser's
// Accept header lists. The label is in the picture; this adds how many bytes arrived and
// why, by matching the download size against the four files. Safari hides that size, so
// there the decoded pixels are compared with the AVIF, JPEG XL and WebP copies loaded on
// their own (each format decodes to slightly different pixels); no match means the JPEG,
// since negotiated.jpg can't be fetched as a plain JPEG. Without JavaScript the label in
// the picture still answers.
(() => {
  const fig = document.querySelector("figure.demo-format");
  if (!fig) return;
  const img = fig.querySelector("img"), note = fig.querySelector(".format-result");
  const sizes = JSON.parse(fig.dataset.sizes);
  const WHY = {
    avif: "It lists AVIF and isn't one of Apple's, so it got the smallest copy.",
    jxl: "It lists JPEG XL, as Safari 17 and later do, so it got the JPEG XL copy.",
    webp: "It lists WebP but not JPEG XL, and Apple's browsers never get AVIF here.",
    jpg: "It lists none of the newer formats, so it got the JPEG that every browser can show.",
  };
  const NAME = { avif: "AVIF", jxl: "JPEG XL", webp: "WebP", jpg: "JPEG" };
  const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
  // A hash of a 128 x 128 patch from the middle, at full size (same origin, so readable).
  const print = (im) => {
    try {
      const c = document.createElement("canvas"); c.width = c.height = 128;
      const x = c.getContext("2d", { willReadFrequently: true });
      x.drawImage(im, (im.naturalWidth - 128) >> 1, (im.naturalHeight - 128) >> 1, 128, 128, 0, 0, 128, 128);
      const d = x.getImageData(0, 0, 128, 128).data; let h = 2166136261;
      for (let i = 0; i < d.length; i++) h = Math.imul(h ^ d[i], 16777619);
      return h >>> 0;
    } catch { return null; }
  };
  const decoded = (src) => new Promise((res) => {
    const im = new Image(); im.onload = () => res(im.naturalWidth ? im : null); im.onerror = () => res(null); im.src = src;
  });
  const byPixels = async () => {
    const mine = print(img); if (mine === null) return null;
    const base = (img.currentSrc || img.src).replace(/negotiated\.jpg.*$/, "negotiated.");
    for (const k of ["avif", "jxl", "webp"]) {
      const im = await decoded(base + k);
      if (im && print(im) === mine) return k;
    }
    return "jpg";
  };
  const report = async () => {
    const e = performance.getEntriesByName(img.currentSrc || img.src).pop();
    let got = e && e.encodedBodySize && Object.keys(sizes).find((k) => sizes[k] === e.encodedBodySize);
    if (!got) got = await byPixels();
    if (!got) return;
    note.textContent = `Your browser downloaded the ${NAME[got]} copy: ${kb(sizes[got])}. ${WHY[got]}`;
    fig.querySelectorAll("tr[data-f]").forEach((tr) => tr.classList.toggle("got", tr.dataset.f === got));
  };
  if (img.complete) report(); else img.addEventListener("load", report);
})();
