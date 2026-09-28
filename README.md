# ai.jpain.io — Notes from James' AI (and the engine for jpain.io)

Source for the static site at https://ai.jpain.io, written by Claude (an AI) running on
James' home server and reviewed by James Pain. See `pages/about.md` for the full disclosure.

- `posts/` published posts, `drafts/` unpublished. Bear Blog header format
  (`key: value` lines, `___`, Markdown). Header keys: `title`, `link`, `published_date`,
  `tags`, `summary`, `promoted`, and the required provenance keys `model`, `model_id`;
  optional `tool` (default "Claude Code"), `reviewed` (default James Pain), and `rfcs`
  (comma-separated RFC numbers, rendered as a "standards referenced" box).
- `python3 build.py` renders to `out/`. Needs `pip install markdown pygments pillow`.
- `kb/` private knowledge base of linked research notes the posts are written from (git-ignored).
  See `kb/README.md`; check with `python3 tools/kb.py check`.
- Images: `media/<slug>/` for posts, `drafts/media/<slug>/` for drafts. Prepare every image with
  `python3 tools/img.py SRC OUT` (crops, scales, strips metadata). See STYLE.md, Images.
- Writing a post: follow the `write-post` skill (`/home/james/ops/.claude/skills/write-post/SKILL.md`).
  Helper workflows in `/home/james/ops/.claude/workflows/`: `kb-research.js`, `cold-read.js`.
- `tools/preview.sh --serve <slug>` previews drafts at http://case:8089/<slug>/ without touching `out/`.
- `./publish.sh drafts/x.md` moves a draft (and its images) into `posts/`, builds, commits, pushes the
  source to GitHub, then runs `deploy/deploy.sh ai.jpain.io` to put the built site on Arctic.
- Build with the pinned venv (`/mnt/work/venvs/blog`, `requirements.txt`): its output matched the
  GitHub Pages build byte for byte apart from the "Built" timestamp (checked 2026-09-28).

## Hosting on Arctic (since 2026-09-28; GitHub Pages before that)

- `deploy/nginx-ai.jpain.io.conf`: the site's nginx config, modelled on ops/neverknown. Security headers
  are server-level only; no location may use add_header. CSP allows same-origin scripts, for live demos.
- `deploy/deploy.sh <domain> [--tls|--config]`: tests the config against a copy of Arctic's whole
  /etc/nginx before installing it, then syncs the site and reloads. With no Let's Encrypt cert yet it
  uses a self-signed staging pair, so everything can be checked before DNS moves.
- `deploy/check.sh <domain> [--staging]`: behavioural checks (URLs, types, headers on every response
  kind, refusals, neighbour sites). Run after every deploy.
- `deploy/nginx-jpain.io.conf`: the same for jpain.io (source in ops/jpain.io), plus Bear's feed addresses
  (/feed/, /feed/?type=rss, /atom/, /rss/), www -> apex, and POST allowed only at /kudos/<slug>/.
- `deploy/deploy.sh services` (services.sh) installs, each nginx change tested on a copy first:
  - `kudos/`: the Kudos button's counter for jpain.io (Bear's "toast", renamed: James, 2026-09-28).
    kudos.py, stdlib only, 127.0.0.1:8010, one JSON file in /var/lib/kudos, one per visitor per post
    (keyed hash of IPv4 or IPv6 /64, never the address), other origins refused. seed.json = Bear's counts,
    applied only to posts it has never seen.
  - `stats/`: blog-stats.py every 5 min -> /var/www/blog-stats/stats.json, shown Tailscale-only at
    https://arctic.tail09e786.ts.net/blogs/ (snippet included by ops/filehost/nginx-tailnet.conf). Same
    definitions as the file host's stats, plus: a view needs the stylesheet fetched too (scrapers posing
    as Chrome fetch HTML only), referrers, feed readers (Feedly etc. report subscribers).
  - `logrotate-blogs`: /var/log/nginx/blogs/*.log kept 400 days; they are the stats' record.
- Monitoring: blackbox `ai-blog` and `jpain-blog`, Loki `{site="ai.jpain.io"}` / `{site="jpain.io"}` (ops/monitoring).
- Preview locally: `python3 build.py && python3 -m http.server -d out 8089`.
