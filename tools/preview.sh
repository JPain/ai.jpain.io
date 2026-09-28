#!/usr/bin/env bash
# Preview drafts as they'd look published, without touching the real site or out/.
#   tools/preview.sh [slug ...]     build a throwaway copy with those drafts as posts
#   tools/preview.sh --serve [slug ...]   ...and serve it on port 8089 (Ctrl-C to stop)
# With no slugs, every draft in drafts/ is included. Open http://case:8089/<slug>/ from the LAN or tailnet.
set -euo pipefail
PY=/mnt/work/venvs/blog/bin/python; [ -x "$PY" ] || PY=python3
cd "$(dirname "$0")/.."
serve=0
if [ "${1:-}" = "--serve" ]; then serve=1; shift; fi
slugs=("$@")
if [ ${#slugs[@]} -eq 0 ]; then
  for f in drafts/*.md; do slugs+=("$(basename "$f" .md)"); done
fi
tmp=/tmp/blog-preview
rm -rf "$tmp"
mkdir -p "$tmp"
cp -r build.py site.json templates static pages posts quotes.json "$tmp"/
[ -d media ] && cp -r media "$tmp"/ || mkdir -p "$tmp/media"
[ -f CNAME ] && cp CNAME "$tmp"/
for s in "${slugs[@]}"; do
  [ -f "drafts/$s.md" ] || { echo "no draft drafts/$s.md" >&2; exit 1; }
  "$PY" build.py --check "drafts/$s.md"
  cp "drafts/$s.md" "$tmp/posts/"
  if [ -d "drafts/media/$s" ]; then rm -rf "$tmp/media/$s"; cp -r "drafts/media/$s" "$tmp/media/$s"; fi
done
(cd "$tmp" && "$PY" build.py)
for s in "${slugs[@]}"; do echo "preview: http://case:8089/$s/"; done
if [ $serve -eq 1 ]; then
  cd "$tmp/out" && exec python3 -m http.server 8089 --bind 0.0.0.0
fi
