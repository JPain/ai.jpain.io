#!/usr/bin/env bash
# Publish a draft: move it from drafts/ to posts/, stamp the date if blank, build to
# check it, commit, push the source to GitHub, and deploy the built site to jpain.io on Fern
# (deploy/deploy.sh). GitHub keeps the source and history; Fern serves the site.
#   ./publish.sh drafts/some-post.md
# With no argument, just commits and pushes whatever is already changed.
# Commits carry a Co-Authored-By trailer for the model that wrote the post (its `model:`
# header). For no-argument runs, set MODEL="Claude Opus 5" to add one. The browser editor
# (tools/editor) publishes as James with PUBLISH_TRAILER="" (no trailer) and its own PUBLISH_MSG.
set -euo pipefail
cd "$(dirname "$0")"
# The pinned build venv (requirements.txt); plain python3 renders code blocks
# slightly differently.
PY=/mnt/work/venvs/blog/bin/python; [ -x "$PY" ] || PY=python3
if [ $# -ge 1 ]; then
  src="$1"; dst="posts/$(basename "$src")"
  [ -f "$src" ] || { echo "no such draft: $src" >&2; exit 1; }
  if grep -qE '^published_date:\s*$' "$src"; then
    sed -i "s/^published_date:\s*$/published_date: $(date -u '+%Y-%m-%d %H:%M')/" "$src"
  fi
  git mv "$src" "$dst" 2>/dev/null || mv "$src" "$dst"
  slug="$(grep -m1 -E '^(link|slug):' "$dst" | cut -d: -f2- | tr -d ' ')"; slug="${slug:-$(basename "$src" .md)}"
  if [ -d "drafts/media/$slug" ]; then
    mkdir -p media && rm -rf "media/$slug" && mv "drafts/media/$slug" "media/$slug"
  fi
  "$PY" build.py --check "$dst"
  msg="Publish: $(grep -m1 '^title:' "$dst" | cut -d: -f2- | sed 's/^ *//')"
  MODEL="$(grep -m1 '^model:' "$dst" | cut -d: -f2- | sed 's/^ *//')"
else
  msg="Update site"
fi
msg="${PUBLISH_MSG:-$msg}"
trailer="${PUBLISH_TRAILER-${MODEL:+Co-Authored-By: $MODEL <noreply@anthropic.com>}}"
if [ -n "$trailer" ]; then
  msg="$(printf '%s\n\n%s' "$msg" "$trailer")"
fi
"$PY" build.py
git add -A
git commit -m "$msg" || true
git push origin main
deploy/deploy.sh jpain.io
