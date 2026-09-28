// Private blog stats page (Tailscale only). Reads stats.json (blog-stats.timer) and
// kudos/kudos.json (the kudos service). One number per post, the rest on hover.
const SVG = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, text) => {
  const e = tag.startsWith("svg:") ? document.createElementNS(SVG, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
};
function bars(values, cls, w, h) {
  const svg = el("svg:svg", { class: cls, viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none", role: "img" });
  const max = Math.max(1, ...values), bw = w / values.length;
  values.forEach((v, i) => {
    const bh = v ? Math.max(1.5, (v / max) * h) : 1;
    const r = el("svg:rect", { x: i * bw + bw * 0.1, y: h - bh, width: bw * 0.8, height: bh, class: v ? "" : "zero" });
    r.append(el("svg:title", {}, `${v} view${v === 1 ? "" : "s"}`));
    svg.append(r);
  });
  return svg;
}
const ago = (iso) => {
  if (!iso) return "never";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 60 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`;
};
(async () => {
  const [stats, kudos] = await Promise.all([
    fetch("stats.json", { cache: "no-store" }).then((r) => r.json()),
    fetch("kudos/kudos.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ]);
  document.getElementById("generated").textContent = `Updated ${ago(stats.generated)} (${new Date(stats.generated).toLocaleString("en-GB")})`;
  const main = document.getElementById("sites");
  for (const [site, s] of Object.entries(stats.sites)) {
    const d30 = s.daily.slice(-30).reduce((a, b) => a + b, 0);
    const d7 = s.daily.slice(-7).reduce((a, b) => a + b, 0);
    main.append(el("h2", {}, site));
    const services = s.feed_services.map(([n, c]) => `${n} ${c}`).join(", ");
    main.append(el("p", { class: "summary" },
      `${d7} views in 7 days, ${d30} in 30 · ${s.feed_readers} feed reader${s.feed_readers === 1 ? "" : "s"}${services ? ` (${services})` : ""} · daily views, last 90 days:`));
    main.append(bars(s.daily, "chart", 900, 70));
    const hasKudos = site === "jpain.io";
    const t = el("table"), head = el("tr");
    head.append(el("th", {}, "Page"), el("th", { class: "num" }, "Views"));
    if (hasKudos) head.append(el("th", { class: "num" }, "Kudos"));
    head.append(el("th", { class: "hide-narrow" }, "Last 30 days"), el("th", { class: "hide-narrow" }, "From"));
    t.append(head);
    for (const p of s.pages) {
      const tr = el("tr"), name = el("td");
      name.append(el("a", { href: `https://${site}${p.path}` }, p.title || p.path));
      const v = el("td", { class: "num", title: `visitors: ${p.visitors}\nyou: ${p.you}\nbots: ${p.bots}\nlast view: ${ago(p.last)}` }, p.views.toLocaleString("en-GB"));
      tr.append(name, v);
      if (hasKudos) {
        const slug = p.path.replaceAll("/", "");
        tr.append(el("td", { class: "num", title: "public count on the post" }, slug && kudos[slug] !== undefined ? kudos[slug].toLocaleString("en-GB") : ""));
      }
      const sp = el("td", { class: "hide-narrow" }); sp.append(bars(p.daily, "spark", 120, 24));
      tr.append(sp, el("td", { class: "ref hide-narrow" }, p.referrers.map(([h, n]) => `${h} ${n}`).join(", ")));
      t.append(tr);
    }
    main.append(t);
  }
})();
