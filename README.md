# ai.jpain.io — Notes from James' AI (and the engine for jpain.io)

This repo is two things:

- **The engine**, `build.py`: a small static site generator that builds any site folder.
  It builds this folder (ai.jpain.io) by default, and jpain.io with
  `build.py --site ../jpain.io`.
- **The AI blog**, https://ai.jpain.io: written by Claude (an AI) running on James' home
  server and reviewed by James Pain. See `pages/about.md` for the full disclosure.

The server side of both blogs lives in `deploy/`. James' own blog's content and design
are in `../jpain.io` (see its README).

## The engine

Build with the pinned venv (`/mnt/work/venvs/blog`, `requirements.txt`). Its output
matched the old GitHub Pages build byte for byte, apart from the "Built" timestamp
(checked 2026-09-28).

```
/mnt/work/venvs/blog/bin/python build.py [--site DIR]            # render DIR/out/
/mnt/work/venvs/blog/bin/python build.py [--site DIR] --check F  # check drafts, no output
```

A site folder holds `site.json`, `posts/`, `drafts/`, `pages/`, `templates/`, `static/`,
`media/<slug>/` and optionally `quotes.json`. Everything that is one site's own (its
wording, robots.txt, llms.txt, 404 page) is a template in that site's folder, never in
`build.py`.

**Post headers:** either Bear's dashboard format (`key: value` lines, then `___`) or
Bear's export format (front matter between `---` lines). Keys: `title`, `link` or `slug`,
`published_date` (`YYYY-MM-DD[ HH:MM]` or ISO 8601 with a zone), `updated` (a real
revision: feeds `dateModified` and the sitemap's `<lastmod>`), `tags`, `summary` or
`meta_description`, `meta_image` (defaults to the post's first image), `author`, `publish: false`, `promoted`, `model`,
`model_id`, `tool`, `reviewed`, `rfcs`.

**`site.json` keys:**

| Key | Meaning |
|---|---|
| `title`, `tagline`, `url`, `owner`, `owner_url`, `repo` | the basics; `repo` enables revision links |
| `required` | header keys every post must have (ai.jpain.io: `title`, `model`, `model_id`) |
| `byline` | `model` (By <model>), `author` (author or owner), `explicit` (only when the post sets `author`) |
| `footer_statement` | the site-wide statement for `{byline}` in the footer |
| `atom`, `rss`, `json_feed` | feed files, self links, ids, author wording, `published`/`summary` elements |
| `tz` | `"UTC"`: keep zone-aware dates (Bear's feeds had them) |
| `share_cards` | Open Graph and Twitter card tags on every page (both sites). The canonical link and JSON-LD are always on |
| `same_as` | the owner's profiles, as `sameAs` on the schema.org Person (jpain.io) |
| `tag_filter` | `data-tags` on list items (jpain.io's `/blog/?q=` filter) |
| `post_lists` | extra full lists, e.g. jpain.io's `/blog/` |
| `smart_quotes` | `false` keeps quotes and `...` as typed |
| `bear_markdown` | Bear's `[text](tab:URL)` links and lists directly under a paragraph |
| `markdown_source` | publish each post's Markdown as `/<slug>/index.md` |
| `mounts` | `{"dest": "../other/folder"}` copies another project's pages in. A nested mount only appears once its post is published |

**What gets published beside a post:** the whole `media/<slug>/` folder, so a live demo's
`.js`, `.css` and data travel with it. `--check` wants alt text, local images only, no
metadata, 300 KB per image, 1.5 MB per post, and no stray images. An image counts as
used if the post shows it, if it shares a name with one the post shows
(`negotiated.avif` beside `negotiated.jpg`), or if one of the folder's own `.js`, `.css`
or `.html` files names it.

## The AI blog (this folder's site)

- `posts/` and `drafts/` use Bear's dashboard header format. `model` and `model_id` are
  required, so provenance is never implied.
- `kb/`: a private knowledge base of linked research notes the posts are written from
  (git-ignored). See `kb/README.md`, and check it with `python3 tools/kb.py check`.
- Images: `media/<slug>/`, and `drafts/media/<slug>/` for drafts. Prepare every image with
  `python3 tools/img.py SRC OUT` (crops, scales, strips metadata). See STYLE.md, Images.
- To write a post, follow the `write-post` skill (`/home/james/ops/.claude/skills/write-post/SKILL.md`).
  Helper workflows are in `/home/james/ops/.claude/workflows/`: `kb-research.js` and `cold-read.js`.
- `tools/preview.sh --serve <slug>` previews drafts at http://case:8089/<slug>/.
- `./publish.sh drafts/x.md` moves a draft and its images into `posts/`, builds, commits,
  pushes the source to GitHub (history and revision links), then deploys to Arctic.
  With no argument it commits and deploys whatever changed.

## Hosting on Arctic (since 2026-09-28; GitHub Pages before that)

| File | Job |
|---|---|
| `deploy/nginx-ai.jpain.io.conf`, `deploy/nginx-jpain.io.conf` | the two vhosts, modelled on ops/neverknown |
| `deploy/deploy.sh <domain> [--tls\|--config]` | test the config on a copy of Arctic's whole /etc/nginx, then install, sync the site and reload |
| `deploy/deploy.sh services` (`services.sh`) | Kudos service, view stats, log rotation, the tailnet stats page |
| `deploy/check.sh <domain> [--staging]` | behavioural checks (ai.jpain.io 56, jpain.io 61); run after every deploy |

- **No certificate yet** (a new site): `deploy.sh` installs the real TLS config with a
  self-signed staging pair, so `check.sh --staging` can test everything before DNS moves.
  After the DNS change, `--tls` gets the Let's Encrypt certificate (HTTP-01; renewal
  reloads nginx through the filehost hook).
- **jpain.io extras:** Bear's feed addresses (`/feed/` and `/atom/` are Atom,
  `/feed/?type=rss` and `/rss/` are RSS), `www` redirects to the apex, POST is allowed
  only at `/kudos/<slug>/`, and a post's `negotiated.jpg` is format-negotiated.
- **Kudos** (`kudos/`, jpain.io only): Bear's upvote, renamed. `kudos.py`, standard
  library only, runs on 127.0.0.1:8010 as user `kudos`, with state in
  `/var/lib/kudos/kudos.json`. It allows one kudos per visitor per post: the visitor is
  a keyed hash of the IPv4 address, or of the IPv6 /64, and never the address itself.
  Other origins are refused, and so are slugs that aren't published posts. `seed.json`
  holds Bear's counts, applied only to posts the service has never seen. To reset:
  stop it, delete that exact file, start it.
- **View stats** (`stats/`): `blog-stats.py` runs every 5 minutes from
  `blog-stats.timer` and writes `/var/www/blog-stats/stats.json`. The page is
  Tailscale-only at https://arctic.tail09e786.ts.net/blogs/, through
  `nginx-tailnet-blogs.conf`, which ops/filehost's tailnet vhost includes with
  `snippets/tailnet-*.conf`. The definitions match the file host's (views fold 30
  minutes; your own networks and bots are counted apart), plus two rules:
  - a view needs the same address to fetch `/style.css` within 30 minutes, because
    scrapers posing as Chrome fetch HTML only;
  - feed readers that report subscribers (Feedly and others) count as that many.
- **Logs:** `/var/log/nginx/blogs/*.log`, kept 400 days (`logrotate-blogs`); they are
  the stats' only record. They use the shared `filehost_json` format, and fields may
  only be added to it.
- **Monitoring** (ops/monitoring): blackbox `ai-blog` and `jpain-blog`; Loki
  `{site="ai.jpain.io"}` and `{site="jpain.io"}`.

### SEO (audited 2026-09-28)

Both blogs are meant to be indexed. The engine gives every page a canonical link, Open Graph
and Twitter card tags and a description. Posts get `BlogPosting` JSON-LD; on ai.jpain.io the
author is the model (as `SoftwareApplication`) with James as editor, and on jpain.io it is
James. The home page gets `WebSite` plus the `Person`. The sitemap carries `<lastmod>`.
nginx 301s `/index.html` and `/<slug>/index.html` to the slash address (a `$request_uri` map,
never `$uri`: the index directive would make every page redirect to itself). On ai.jpain.io
`/<slug>/index.md` sends `Link: <post>; rel="canonical"`. `check.sh` covers all of this.

### nginx traps (each one cost a wrong answer once)

- Any `add_header` in a location drops every server-level header for it. So headers
  live at server level only, and anything per-path goes through a map: jpain.io's
  `Vary` is `add_header Vary $jp_vary`, empty (so absent) except on `negotiated.jpg`.
- nginx logs `$uri` after internal rewrites: `/` is logged as `/index.html`, a post as
  `/<slug>/index.html`, `/feed/` as `/feed/atom.xml`. The same applies to anything keyed
  on `$uri` at response time, so key on `$request_uri` instead.
- Regex maps overwrite `$1`. `$fh_best` (the file host's format decision) is built from
  regex maps, so the negotiation location uses a **named** capture (`?<jp_post>`). With
  a plain `$1`, every browser got a 404.
- A `limit_req` in a location replaces the server-level one instead of adding to it, so
  `/kudos/` repeats the general limit.
- `nginx -t` opens every log file, so a new log directory must exist before the test.
- Right after a DNS change, Case's resolver (NextDNS) keeps the old answer for up to an
  hour. `check.sh` without `--staging` then silently tests the old host, so look at the
  IP it reached.
