// YouTube videos in posts (build.py youtube_embeds): each shows its thumbnail, saved on this site,
// and nothing loads from YouTube until the reader presses play. Then the link becomes a
// youtube-nocookie.com player. Ctrl/Cmd/Shift-click still opens the video on YouTube.
"use strict";
document.addEventListener("click", (e) => {
  const a = e.target.closest && e.target.closest("a.yt[data-yt]");
  if (!a || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  const f = document.createElement("iframe");
  const start = Number(a.dataset.start) || 0;
  f.src = `https://www.youtube-nocookie.com/embed/${a.dataset.yt}?autoplay=1&rel=0${start ? "&start=" + start : ""}`;
  f.title = a.dataset.title || "YouTube video";
  f.className = "yt";
  f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen; web-share";
  f.allowFullscreen = true;
  f.referrerPolicy = "strict-origin-when-cross-origin";
  a.replaceWith(f);
  f.focus();
});
