#!/usr/bin/env bash
# Publish a draft: move it from drafts/ to posts/, stamp the date if blank, build to
# check it, commit, push. GitHub Actions builds and deploys from main.
#   ./publish.sh drafts/some-post.md
# With no argument, just commits and pushes whatever is already changed.
set -euo pipefail
cd "$(dirname "$0")"
if [ $# -ge 1 ]; then
  src="$1"; dst="posts/$(basename "$src")"
  [ -f "$src" ] || { echo "no such draft: $src" >&2; exit 1; }
  if grep -qE '^published_date:\s*$' "$src"; then
    sed -i "s/^published_date:\s*$/published_date: $(date '+%Y-%m-%d %H:%M')/" "$src"
  fi
  git mv "$src" "$dst" 2>/dev/null || mv "$src" "$dst"
  msg="Publish: $(grep -m1 '^title:' "$dst" | cut -d: -f2- | sed 's/^ *//')"
else
  msg="Update site"
fi
python3 build.py
git add -A
git commit -m "$msg" || true
git push origin main
