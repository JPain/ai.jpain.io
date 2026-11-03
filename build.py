#!/usr/bin/env python3
"""Static site generator for James' blogs: ai.jpain.io ("Notes from James' AI") and jpain.io.

One engine, one folder per site. The site folder holds everything that belongs to that site:
  site.json     settings: title, URL, owner, which header keys are required, feed layout
  posts/*.md    published posts (built)
  drafts/*.md   drafts (ignored by the build)
  pages/*.md    standalone pages, e.g. about
  templates/    HTML templates with {placeholders}; optional home.html, 404.html, robots.txt, llms.txt, humans.txt
  static/       copied verbatim into the output
  media/<slug>/ images and demo files for a published post, served next to it at /<slug>/<file>
  drafts/media/<slug>/  the same for a draft (git-ignored until publish.sh moves them)
  quotes.json   optional footer quotes
  out/          generated site (git-ignored)

This folder (ops/blog) is both the engine and the ai.jpain.io site. Build another site with
  build.py --site ../jpain.io [--check files...]

Images: a paragraph holding only ![alt](file.webp "caption") becomes a <figure> with the
caption, real width/height and lazy loading. Paths are bare file names inside the post's
media folder. `--check` enforces alt text, local files only, stripped metadata and size budgets.

Post header: either Bear Blog's dashboard format (`key: value` lines, then `___`) or YAML-style
front matter between `---` lines, as in Bear's export. Keys used: title (required), link or slug
(defaults from the filename), published_date (YYYY-MM-DD, YYYY-MM-DD HH:MM or ISO 8601 with a
zone; defaults to now), tags (comma-separated), summary or meta_description (one line for the
index, feed and description meta), meta_image (share image; defaults to the post's first image),
updated (date of a real revision: dateModified and sitemap lastmod), author (byline override),
publish (false = not built), unlisted (true = built at its address but left off
the home page, tags, feeds and sitemap, listed only on /archive/, and noindex), outdated (a note under the title of a post things have
overtaken), model and model_id (a post that names a model was written by
that AI, and says so; every other post is the owner's), cowritten (with model and model_id: the
owner and that AI wrote it together; the value is the note under the title, saying plainly who did
what and naming the model).
Everything else is ignored.
"""
import base64
import datetime as dt
import email.utils
import html
import re
import shutil
import sys
from pathlib import Path

import hashlib
import json
import subprocess
import markdown
from PIL import Image

import cards

ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE          # the site folder; set by use_site()
OUT = ROOT / "out"
SITE = {}

IMAGE_TYPES = {".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif"}
IMAGE_MAX_KB = 300        # per image
POST_IMAGES_MAX_KB = 1500  # all images in one post
IMG_P = re.compile(r'<p>(<img [^>]*>)</p>')
IMG_TAG = re.compile(r'<img ([^>]*)>')
ATTR = re.compile(r'(\w+)="([^"]*)"')


def use_site(folder):
    """Point the build at a site folder and load its site.json."""
    global ROOT, OUT, SITE, QUOTES
    ROOT = Path(folder).resolve()
    OUT = ROOT / "out"
    SITE = json.loads((ROOT / "site.json").read_text())
    SITE.setdefault("required", ["title"])
    SITE.setdefault("byline", "author")
    SITE.setdefault("footer_statement", "")
    q = ROOT / "quotes.json"
    QUOTES = json.loads(q.read_text()) if q.exists() else []


def media_dir(path, slug):
    """Where a post's images live: drafts/media/<slug>/ for drafts and work files, media/<slug>/ once published."""
    rel = path.resolve().relative_to(ROOT).parts if path.resolve().is_relative_to(ROOT) else ()
    return ROOT / ("drafts" if rel[:1] in (("drafts",), ("work",)) else "") / "media" / slug


def image_size(f):
    if f.suffix.lower() == ".svg":
        m = re.search(r'viewBox="[\d.\s-]*?([\d.]+)\s+([\d.]+)"', f.read_text())
        return (round(float(m.group(1))), round(float(m.group(2)))) if m else (None, None)
    with Image.open(f) as im:
        return im.size


def images_in(html_text):
    return [dict(ATTR.findall(m.group(1))) for m in IMG_TAG.finditer(html_text)]


def figures(html_text, folder):
    """<p><img></p> -> <figure> with caption from the title; add size and lazy loading to every img."""
    def tag(m):
        a = dict(ATTR.findall(m.group(1)))
        extra = ""
        f = folder / a.get("src", "")
        if "://" not in a.get("src", "") and f.is_file() and "width" not in a:
            w, h = image_size(f)
            if w:
                extra = f' width="{w}" height="{h}"'
        attrs = " ".join(f'{k}="{v}"' for k, v in a.items() if k != "title")
        return f'<img {attrs}{extra} loading="lazy" decoding="async">'

    def fig(m):
        a = dict(ATTR.findall(m.group(1)))
        cap = f'<figcaption>{a["title"]}</figcaption>' if a.get("title") else ""
        return f'<figure>{IMG_TAG.sub(tag, m.group(1))}{cap}</figure>'

    out = IMG_P.sub(fig, html_text)
    # Keyboard users can scroll a wide code block or table only if it can take focus (WCAG 2.1.1).
    out = out.replace("<pre>", '<pre tabindex="0">')
    out = re.sub(r"<table>(.*?)</table>", r'<div class="table-scroll" tabindex="0"><table>\1</table></div>', out, flags=re.S)
    return re.sub(r'<img (?![^>]*loading=)([^>]*)>', lambda m: tag(m), out)


# A YouTube video: a link alone in its paragraph, marked {.youtube}:
#   [Video title](https://youtu.be/ID "Optional caption"){.youtube}
# It renders as the video's thumbnail (youtube-<ID>.webp in the post's media folder, saved by the
# editor or tools/youtube.py) with a play button. Nothing loads from YouTube until a reader presses
# play; static/youtube.js then swaps in a youtube-nocookie.com player. Without JavaScript, and in
# feeds, it stays a link to the video.
YT_P = re.compile(r'<p><a ([^>]*\bclass="youtube"[^>]*)>(.*?)</a></p>', re.S)
YT_ID = re.compile(r'(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/))([\w-]{11})')


# A note: a quote whose first line is [!NOTE] (GitHub's and Obsidian's alert syntax), with an
# optional label after it on the same line:
#   > [!NOTE] Definition
#   > "Vibe coding" means ...
# It becomes <aside class="note"> with the label ("Note" if none) as its first line.
NOTE = re.compile(r"<blockquote>\s*<p>\[!NOTE\][ \t]*([^\n<]*?)[ \t]*(\n|</p>\s*)(.*?)</blockquote>", re.S | re.I)


def note_blocks(html_text):
    def note(m):
        label = m.group(1).strip() or "Note"
        rest = m.group(3)
        rest = ("<p>" + rest) if m.group(2) == "\n" else rest   # the label shared the first paragraph
        return f'<aside class="note">\n<p class="note-label">{label}</p>\n{rest.strip()}\n</aside>'
    return NOTE.sub(note, html_text)


def youtube_ref(url):
    """(video id, start second) from any YouTube address, or (None, 0)."""
    url = html.unescape(url)
    m = YT_ID.search(url)
    if not m:
        return None, 0
    t = re.search(r'[?&#](?:t|start)=(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?', url)
    start = sum(int(n or 0) * k for n, k in zip(t.groups(), (3600, 60, 1))) if t else 0
    return m.group(1), start


def youtube_embeds(html_text):
    def embed(m):
        a = dict(ATTR.findall(m.group(1)))
        vid, start = youtube_ref(a.get("href", ""))
        if not vid:
            return m.group(0)
        title = html.escape(html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip() or "YouTube video")
        cap = f'<figcaption>{a["title"]}</figcaption>' if a.get("title") else ""
        href = f"https://www.youtube.com/watch?v={vid}" + (f"&amp;t={start}s" if start else "")
        return (f'<figure class="youtube"><a class="yt" href="{href}" data-yt="{vid}" data-start="{start}" '
                f'data-title="{title}" aria-label="Play video: {title}">'
                f'<img src="youtube-{vid}.webp" alt="{title}">'
                f'<span class="yt-title" aria-hidden="true">{title}</span>'
                '<svg class="yt-play" viewBox="0 0 68 48" aria-hidden="true"><path class="yt-bg" d="M66.5 7.7c-.8-2.9-3-5.2-5.9-6C55.3.3 34 .3 34 .3s-21.3 0-26.6 1.4c-2.9.8-5.1 3.1-5.9 6C.1 13 .1 24 .1 24s0 11 1.4 16.3c.8 2.9 3 5.2 5.9 6C12.7 47.7 34 47.7 34 47.7s21.3 0 26.6-1.4c2.9-.8 5.1-3.1 5.9-6C67.9 35 67.9 24 67.9 24s0-11-1.4-16.3z"/><path fill="#fff" d="M45 24 27 14v20z"/></svg>'
                f'</a>{cap}</figure>')
    out = YT_P.sub(embed, html_text)
    if out != html_text and 'src="/youtube.js"' not in out:
        out += '\n<script src="/youtube.js" defer></script>'
    return out


def absolute_images(html_text, slug):
    """Feeds are read out of context, so image and link paths must be absolute there. A demo's
    <script> and <link rel=stylesheet> are dropped: feed readers strip them anyway."""
    html_text = re.sub(r'<script\b[^>]*>.*?</script>\s*|<link rel="stylesheet"[^>]*>\s*', "", html_text, flags=re.S)
    def fix(m):
        attr, path = m.group(1), m.group(2)
        return f'{attr}="{SITE["url"]}{path}"' if path.startswith("/") else f'{attr}="{SITE["url"]}/{slug}/{path}"'
    return re.sub(r'\b(src|href|poster)="(?![a-z][a-z0-9+.-]*:|#|//)([^"]+)"', fix, html_text)


def terminal_fences(body):
    """A fenced block with no language whose first line starts with "$ " is a terminal session:
    label it console, so Pygments marks the prompt (.gp) and the output (.go)."""
    out, fence = [], None
    lines = body.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(\s{0,3})(`{3,}|~{3,})\s*(\S*)", line)
        if m and fence is None:
            fence = m.group(2)
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not m.group(3) and nxt.lstrip().startswith("$ "):
                line = f"{m.group(1)}{m.group(2)}console"
        elif m and fence and m.group(2).startswith(fence[0]) and len(m.group(2)) >= len(fence) and not m.group(3):
            fence = None
        out.append(line)
    return "\n".join(out)


MD_EXTENSIONS = ["tables", "fenced_code", "codehilite", "toc", "smarty", "attr_list"]
MD_CONFIG = {"codehilite": {"css_class": "hl", "guess_lang": False}}


def read_template(name):
    return (ROOT / "templates" / name).read_text()


def optional_template(name):
    f = ROOT / "templates" / name
    return f.read_text() if f.exists() else None


def render(template, **kw):
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", v)
    return out


def split_header(text):
    """(header lines, body) for either header style."""
    if text.startswith("---\n") and "\n---\n" in text[4:]:
        head, body = text[4:].split("\n---\n", 1)
        return head, body
    if "\n___\n" in text:
        return tuple(text.split("\n___\n", 1))
    return "", text


def parse_date(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def site_date(when):
    """Sites with a "tz" setting keep zone-aware UTC dates (Bear's feeds carry them); the rest stay naive."""
    if SITE.get("tz") == "UTC":
        return when.replace(tzinfo=dt.timezone.utc) if when.tzinfo is None else when.astimezone(dt.timezone.utc)
    return when.astimezone(dt.timezone.utc).replace(tzinfo=None) if when.tzinfo else when


def iso(d):
    d = d.replace(microsecond=0)
    return d.isoformat() if d.tzinfo else d.isoformat() + "Z"


LIST_ITEM = re.compile(r"^\s{0,3}([-*+]|\d+[.)])\s")


BEAR_TAB_LINK = re.compile(r"\]\(tab:([^)\s]+)\)")


def bear_markdown(body):
    """Bear-only syntax: [text](tab:URL) is a link that opens in a new tab, and a list may
    start right under a paragraph. Used by sites with "bear_markdown": true."""
    body = BEAR_TAB_LINK.sub(r'](\1){: target="_blank" rel="noopener"}', body)
    return bear_lists(body)


def bear_lists(body):
    """Bear (like GitHub) starts a list right under a paragraph; Python-Markdown needs a blank
    line first. Insert one, outside fenced code. Used by sites with "bear_markdown": true."""
    out, fence, prev = [], False, ""
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        if (not fence and LIST_ITEM.match(line) and prev.strip()
                and not LIST_ITEM.match(prev) and not prev.startswith((" ", "\t"))):
            out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def parse(path):
    text = path.read_text()
    head, body = split_header(text)
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    for k in SITE["required"]:
        if not meta.get(k):
            sys.exit(f"{path}: missing header key '{k}' (required by {ROOT.name}/site.json)")
    # Who wrote it: a post naming a model is the AI's, and it must name the exact model id too.
    # Every other post is the owner's.
    if meta.get("model") and not meta.get("model_id"):
        sys.exit(f"{path}: model: needs model_id: as well")
    # cowritten: <who did what> marks a post the owner and the AI wrote together.
    if meta.get("cowritten") and not meta.get("model"):
        sys.exit(f"{path}: cowritten: needs model: and model_id: as well")
    slug = meta.get("link") or meta.get("slug") or path.stem
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        sys.exit(f"{path}: bad slug {slug!r}")
    date = meta.get("published_date") or ""
    when = parse_date(date) if date else None
    if when is None:
        when = dt.datetime.now()
    when = site_date(when)
    # "updated:" marks a real revision of an older post; it feeds dateModified and sitemap <lastmod>.
    updated = parse_date(meta.get("updated", "")) if meta.get("updated") else None
    updated = max(when, site_date(updated)) if updated else when
    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
    # The owner's posts can be typed differently (site.json "owner_typing"): jpain.io keeps James'
    # quotes and ... exactly as typed, and reads Bear's Markdown, as on Bear.
    typing = SITE if meta.get("model") and not meta.get("cowritten") else {**SITE, **SITE.get("owner_typing", {})}
    exts = [e for e in MD_EXTENSIONS if typing.get("smart_quotes", True) or e != "smarty"]
    md = markdown.Markdown(extensions=exts, extension_configs=MD_CONFIG)
    words = len(re.findall(r"\S+", body))
    folder = media_dir(path, slug)
    raw_html = note_blocks(youtube_embeds(md.convert(terminal_fences(bear_markdown(body) if typing.get("bear_markdown") else body))))
    return {
        "media": folder,
        "images": images_in(raw_html),
        "raw": text,
        "words": words,
        "minutes": max(1, round(words / 230)),
        "git": git_info(path),
        "slug": slug,
        "title": meta["title"],
        "date": when,
        "updated": updated,
        "tags": tags,
        "summary": meta.get("summary") or meta.get("meta_description", ""),
        # The search-result line: meta_description when set (Google shows about 160 characters),
        # else the summary, which the feeds keep in full.
        "description": meta.get("meta_description") or meta.get("summary", ""),
        "image": meta.get("meta_image", ""),
        "author": meta.get("author", ""),
        # byline: none hides the "By ..." line on a page (the crawler page, James' ask).
        "byline": meta.get("byline", "").strip().lower() not in ("none", "no"),
        "publish": meta.get("publish", "true").lower() != "false",
        "unlisted": meta.get("unlisted", "").strip().lower() in ("true", "yes"),
        "outdated": meta.get("outdated", ""),
        "model": meta.get("model", ""),
        "model_id": meta.get("model_id", ""),
        "cowritten": meta.get("cowritten", ""),
        "tool": meta.get("tool", "Claude Code"),
        # reviewed: none marks a post published without the owner's review (standing permission).
        "reviewed": "" if meta.get("reviewed", SITE["owner"]).strip().lower() in ("none", "no") else meta.get("reviewed", SITE["owner"]),
        "rfcs": [c.strip() for c in meta.get("rfcs", "").split(",") if c.strip().isdigit()],
        "html": figures(raw_html, folder),
        "source": path,
    }


def git_info(path):
    """Short hash, ISO date and revision count for a file, or None if not committed."""
    repo = SITE.get("repo")
    if not repo:
        return None
    rel = str(path.relative_to(ROOT))
    try:
        log = subprocess.run(["git", "log", "-1", "--format=%h %cI", "--", rel], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
        if not log:
            return None
        n = subprocess.run(["git", "rev-list", "--count", "HEAD", "--", rel], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
        return {"hash": log[0], "date": log[1][:10], "revisions": int(n or 0),
                "history": f"{repo}/commits/main/{rel}", "blob": f"{repo}/blob/main/{rel}"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_date(path):
    """When a file was last committed, or None (not committed, or no git)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(path)], cwd=path.parent,
                             capture_output=True, text=True, check=True).stdout.strip()
        return site_date(dt.datetime.fromisoformat(out)) if out else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def esc(s):
    return html.escape(s, quote=True)


def tag_slug(t):
    """URL form of a tag: Bear tags have capitals and spaces ("Next.js", "web development")."""
    return re.sub(r"[^a-z0-9.]+", "-", t.lower()).strip("-")


def tag_links(tags, linked=None):
    """Tags as links to their pages; a tag with no page (only unlisted posts use it) stays plain text."""
    return ", ".join(f'<a href="/tags/{esc(tag_slug(t))}/">{esc(t)}</a>' if linked is None or tag_slug(t) in linked
                     else esc(t) for t in tags)


def by_ai(p):
    """A post written by an AI names its model in the header."""
    return bool(p["model"]) and not p["cowritten"]


def cowritten(p):
    """A post the owner and the AI wrote together: it names the model and says who did what."""
    return bool(p["model"]) and bool(p["cowritten"])


def author_name(p):
    """Who wrote it, as plain text: the model for the AI's posts, both for joint ones, else the
    post's author or the owner."""
    if cowritten(p):
        return f'{SITE["owner"]} and {SITE.get("ai_name", p["model"])}'
    return p["model"] if by_ai(p) else (p["author"] or SITE["owner"])


def byline(p):
    return f'<span class="author p-author">By {esc(author_name(p))}</span>'


def writer_mark(p):
    """The index's who-wrote-it, on the date line: "AI", or the owner's short name. Compact on
    purpose; the post itself names the model and says plainly that an AI wrote it."""
    if by_ai(p):
        return ' | <span class="by-ai">AI</span>'
    if cowritten(p):
        return f' | <span class="by-owner">{esc(SITE.get("owner_short", SITE["owner"]))}</span> + <span class="by-ai">AI</span>'
    return f' | <span class="by-owner">{esc(SITE.get("owner_short", SITE["owner"]))}</span>'


QUOTES = []


def quote_for(key):
    """A stable, sourced quote from computing history, chosen by page path."""
    if not QUOTES:
        return ""
    q = QUOTES[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(QUOTES)]
    return (f'<p class="quote">“{esc(q["q"])}” <span class="who">{esc(q["who"])}, '
            f'{esc(q["src"])}.</span></p>')


_POW = {}   # contact_email()'s answer per address: the search is the slow part of a build


def contact_email():
    """The contact address behind a quiet proof-of-work (static/contact.js), never plain text in the HTML.
    The browser hashes "<challenge>:<n>" for n = 0, 1, 2... until a SHA-256 starts with POW_BITS zero
    bits; the address is XORed with SHA-256 of "<challenge>:<n>:key" for that first n, so it can't be
    read without doing the work. Deterministic: the same address always builds the same page."""
    c = SITE.get("contact")
    if not c:
        return ""
    addr = f'{c["user"]}@{c["domain"]}'.encode()
    bits = c.get("pow_bits", 18)
    challenge = hashlib.sha256(f'{SITE["url"]} contact {c["user"]} {c["domain"]}'.encode()).hexdigest()[:16]
    n = _POW.get((challenge, bits), 0)
    while int.from_bytes(hashlib.sha256(f"{challenge}:{n}".encode()).digest(), "big") >> (256 - bits):
        n += 1
    _POW[(challenge, bits)] = n
    key = hashlib.sha256(f"{challenge}:{n}:key".encode()).digest()
    cipher = base64.b64encode(bytes(a ^ k for a, k in zip(addr, key))).decode()
    return (f'<p class="contact">Email: <button type="button" class="pow-start" '
            f'data-c="{challenge}" data-bits="{bits}" data-x="{cipher}">Show email address</button>'
            '<span class="pow-status" aria-live="polite"></span></p>'
            '<script src="/contact.js" defer></script>')


def rfc_box(codes):
    if not codes:
        return ""
    items = "".join(
        f'<li><a href="https://www.rfc-editor.org/rfc/rfc{c}">RFC {c}</a></li>' for c in codes)
    return f'<aside class="rfcs"><span class="label">Standards referenced</span><ul>{items}</ul></aside>'


def owner_ld():
    """The site's owner as a schema.org Person. Both blogs name the same one, by the same @id."""
    person = {"@type": "Person", "name": SITE["owner"], "url": SITE["owner_url"]}
    if SITE.get("same_as"):
        person["sameAs"] = SITE["same_as"]
    return person


def model_ld(p):
    """The model that wrote (or helped write) a post. It is not a Person, so it is described as software."""
    return {"@type": "SoftwareApplication", "name": p["model"], "softwareVersion": p["model_id"],
            "applicationCategory": "AI language model", "creator": {"@type": "Organization", "name": "Anthropic"}}


def json_ld(data):
    """A <script type="application/ld+json"> block. It is data, so script-src in the CSP doesn't apply."""
    text = json.dumps({"@context": "https://schema.org", **data}, ensure_ascii=False, indent=2)
    text = text.replace("</", "<\\/")   # a "</script>" inside a string must not end the block
    return f'\n<script type="application/ld+json">\n{text}\n</script>'


CARD = "og-card.png"   # the generated share card's file name, beside each post and at the site root


OG_SIZE = {}   # url -> (width, height) of share images this build wrote
OG_JPG = "og-image.jpg"   # a JPEG copy of a WebP/AVIF meta_image: LinkedIn and others don't show WebP


def post_image(p):
    """The share image: meta_image if set, else the generated card (site.json "card"), else the first image."""
    url = f'{SITE["url"]}/{p["slug"]}/'
    if not p["image"] and SITE.get("card"):
        return url + CARD
    if (OUT / p["slug"] / OG_JPG).is_file():
        return url + OG_JPG
    src = p["image"] or next((i["src"] for i in p["images"] if i.get("src") and "://" not in i["src"]), "")
    return src if "://" in src or not src else url + src


def card_text(s):
    """Card titles get the same curly apostrophes the pages show, unless the site keeps quotes as typed."""
    return re.sub(r"(?<=\w)'", "\u2019", s) if SITE.get("smart_quotes", True) else s


# Set by the browser editor's preview, which rebuilds as you type: share cards are slow PNG encodes
# that no preview shows, so they're skipped there.
NO_CARDS = False


def write_card(rel, title, foot_left="", subtitle=""):
    if NO_CARDS:
        return
    cfg = dict(SITE["card"])
    cfg["brand"] = card_text(cfg.get("brand", SITE["title"]))
    domain = SITE["url"].split("://", 1)[1]
    png = cards.render(cfg, ROOT, card_text(title), card_text(foot_left), domain, card_text(subtitle))
    (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
    (OUT / rel).write_bytes(png)


def post_card(p):
    """Draw a post's card unless it names its own meta_image; a WebP/AVIF meta_image gets a JPEG copy."""
    if NO_CARDS:
        return
    src = p["media"] / p["image"] if p["image"] and "://" not in p["image"] else None
    if src and src.suffix.lower() in (".webp", ".avif") and src.is_file():
        img = Image.open(src).convert("RGB")
        if img.width > cards.W:
            img = img.resize((cards.W, round(img.height * cards.W / img.width)), Image.LANCZOS)
        img.save(OUT / p["slug"] / OG_JPG, "JPEG", quality=85, optimize=True)
        OG_SIZE[f'{SITE["url"]}/{p["slug"]}/{OG_JPG}'] = img.size
    if p["image"] or not SITE.get("card"):
        return
    foot = SITE["card"].get("byline" if by_ai(p) else "owner_byline", "").format(model=p["model"] or "", author=author_name(p),
                                                  date=p["date"].strftime("%-d %B %Y"))
    write_card(f'{p["slug"]}/{CARD}', p["title"], foot)


def head_meta(path, title, description, og_type="website", image=""):
    """Canonical link on every page; Open Graph and Twitter card tags where site.json has share_cards."""
    url = SITE["url"] + path
    if not image and SITE.get("card"):
        image = f'{SITE["url"]}/{CARD}'   # the site card, for every page that isn't a post
    out = f'<link rel="canonical" href="{url}">'
    if SITE.get("share_cards"):
        tags = [("og:type", og_type), ("og:title", title), ("og:url", url), ("og:site_name", SITE["title"]),
                ("og:description", description or SITE["tagline"])]
        if image:
            tags.append(("og:image", image))
            if image.endswith("/" + CARD):   # a generated card: its size and what it says are known
                site_card = image == f'{SITE["url"]}/{CARD}'
                tags += [("og:image:width", str(cards.W)), ("og:image:height", str(cards.H)),
                         ("og:image:alt", f'{SITE["title"]}: {SITE["tagline"]}' if site_card else title)]
            elif image in OG_SIZE:
                tags += [("og:image:width", str(OG_SIZE[image][0])), ("og:image:height", str(OG_SIZE[image][1]))]
        out += "".join(f'\n<meta property="{k}" content="{esc(v)}">' for k, v in tags)
        out += f'\n<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">'
    return out


def page_shell(base, title, body, description="", meta_extra="", key="", path=None, author=""):
    # The site title is the page's top heading on the home page only; elsewhere the post or page title is.
    brand = f'<a class="site-title" href="/">{esc(SITE["title"])}</a>'
    if path == "/":
        brand = f"<h1>{brand}</h1>"
    full = SITE["title"] if title == SITE["title"] else f"{title} | {SITE['title']}"
    if path is not None:
        meta_extra = head_meta(path, SITE["title"] if title == SITE["title"] else title,
                               description) + meta_extra
    return render(
        base,
        page_title=esc(full),
        description=esc(description or SITE["tagline"]),
        site_title=esc(SITE["title"]),
        tagline=esc(SITE["tagline"]),
        site_url=SITE["url"],
        brand=brand,
        page_author=esc(author or SITE["owner"]),
        owner=esc(SITE["owner"]),
        owner_url=SITE["owner_url"],
        byline=esc(SITE["footer_statement"]),
        built=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        meta_extra=meta_extra,
        quote=quote_for(key or title),
        body=body,
    )


def page_author(p):
    """<meta name="author">: the model, with who supervises it, or the owner."""
    if cowritten(p):
        return f'{SITE["owner"]} and {p["model"]} (an AI model by Anthropic)'
    return f'{p["model"]} (an AI model by Anthropic), supervised by {SITE["owner"]}' if by_ai(p) else author_name(p)


def post_meta(p):
    """Extra <head> tags for a post: provenance when a model wrote it, canonical, share cards, BlogPosting."""
    url = f'{SITE["url"]}/{p["slug"]}/'
    image = post_image(p)
    out = f'<meta name="ai-model" content="{esc(p["model_id"])}">\n' if p["model_id"] else ""
    if p["unlisted"]:
        out += '<meta name="robots" content="noindex">\n'
    out += head_meta(f'/{p["slug"]}/', p["title"], p["description"], "article", image)
    # Kept to what search engines use: the headline, dates, author and image (2026-11-03).
    ld = {"@type": "BlogPosting", "url": url, "headline": p["title"],
          "datePublished": iso(p["date"]), "dateModified": iso(p["updated"])}
    if p["summary"]:
        ld["description"] = p["summary"]
    if image:
        ld["image"] = image
    if by_ai(p):
        # The model wrote it; James is the editor only when he reviewed it.
        ld["author"] = model_ld(p)
        if p["reviewed"]:
            ld["editor"] = owner_ld()
    elif cowritten(p):
        ld["author"] = [owner_ld(), model_ld(p)]
    else:
        ld["author"] = owner_ld()
    return out + json_ld(ld)


def home_meta():
    """JSON-LD for the home page: the site, and who runs it with their profiles (sameAs)."""
    return json_ld({"@type": "WebSite", "url": f'{SITE["url"]}/', "name": SITE["title"], "publisher": owner_ld()})


# Tags whose contents the page source indents a level (pretty()). Inline tags such as <p>, <a> and
# <span> aren't here: their lines stay as written.
BLOCKS = {"head", "body", "header", "main", "footer", "nav", "article", "section", "aside", "div",
          "ul", "ol", "li", "figure", "table", "thead", "tbody", "tfoot", "tr", "blockquote",
          "details", "dialog", "form", "fieldset"}
TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")


def pretty(html_text):
    """The page source, indented two spaces per level of nesting so it reads well in view-source.

    Only the start of a line changes, which HTML treats as the same single space, so the page
    renders exactly as before. Lines inside <pre> and <textarea> (code, ASCII art) and inside
    comments (the cat) keep every space; lines inside <script> (the JSON-LD) keep their own
    indentation, shifted to sit under the tag."""
    out, depth, raw, script = [], 0, None, False
    for line in html_text.split("\n"):
        if raw:                                   # verbatim until the closing marker
            out.append(line)
            if raw in line:
                raw = None
            continue
        body = line.strip()
        if not body:
            out.append("")
            continue
        if body.startswith("<!--") and "-->" not in body:
            out.append(line)
            raw = "-->"
            continue
        if script:                                # JSON-LD: one level in, keeping its own indentation
            if body == "</script>":
                script = False
                out.append("  " * depth + body)
            else:
                out.append("  " * (depth + 1) + line.rstrip())
            continue
        lead, rest = 0, body                      # closing tags first on the line: indent it less
        while (m := re.match(r"</([a-zA-Z][a-zA-Z0-9]*)>\s*", rest)) and m.group(1).lower() in BLOCKS:
            lead, rest = lead + 1, rest[m.end():]
        out.append("  " * max(depth - lead, 0) + body)
        script = body.startswith("<script") and "</script>" not in body
        for m in TAG.finditer(body):
            if m.group(2).lower() in BLOCKS and not m.group(3):
                depth = max(depth + (-1 if m.group(1) else 1), 0)
        for opener, closer in (("<pre", "</pre>"), ("<textarea", "</textarea>")):
            i = body.rfind(opener)
            if i >= 0 and closer not in body[i:]:
                raw = closer
    return "\n".join(out)


def write(rel, content, image_bytes=0):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if "{page_kb}" in content:
        kb = len(content.replace("{page_kb}", "00.0").encode()) / 1024
        weight = f"{kb:.1f} KB of HTML"
        if image_bytes:
            weight += f" and {image_bytes / 1024:.0f} KB of images"
        content = content.replace("{page_kb} KB of HTML", weight).replace("{page_kb}", f"{kb:.1f}")
        if "<script src=" in content:   # a post with a live demo loads the demo's own script
            content = content.replace(" with no JavaScript,", ", with JavaScript only for this post's demos,")
    if rel.endswith(".html"):
        content = pretty(content)
    p.write_text(content)


def lightbox(p):
    """Posts with images load static/lightbox.js: click an image to see it larger. A video's
    thumbnail doesn't count; it plays instead."""
    if any(not i.get("src", "").startswith("youtube-") for i in p["images"]):
        return '\n<script src="/lightbox.js" defer></script>'
    return ""


def render_post(p, base, post_t, listed_tags):
    """Write one post's page, its Markdown source, its media folder and its share card into OUT."""
    promoted = ""
    if p["unlisted"]:
        promoted += f'<p class="promoted">{esc(SITE.get("archived_note", "This post is archived."))} <a href="/archive/">Archive</a>.</p>'

    # outdated: <note> puts a note under the title of a post that things have overtaken.
    if p["outdated"]:
        promoted += f'<p class="promoted">{esc(p["outdated"])}</p>'
    # Every AI post says so under its title, and whether James reviewed it (site.json "ai_note").
    if by_ai(p) and SITE.get("ai_note"):
        note = SITE["ai_note"]["reviewed" if p["reviewed"] else "unreviewed"]
        promoted += f'<p class="promoted ai-note">{esc(note.format(model=p["model"]))} <a href="/about/#ai-attribution">AI attribution</a>.</p>'
    # A joint post says so too, and who did what (its cowritten: header).
    if cowritten(p) and SITE.get("ai_note"):
        note = SITE["ai_note"]["cowritten"].format(model=p["model"], cowritten=p["cowritten"])
        promoted += f'<p class="promoted ai-note">{esc(note)} <a href="/about/#ai-attribution">AI attribution</a>.</p>'
    body = render(
        post_t,
        title=esc(p["title"]),
        date=p["date"].strftime("%-d %B %Y"),
        iso_date=p["date"].date().isoformat(),
        slug=p["slug"],
        tags=tag_links(p["tags"], listed_tags),
        author=byline(p),
        promoted=promoted,
        content=p["html"] + rfc_box(p["rfcs"]) + lightbox(p),
    )
    # Everything in the post's media folder is published beside it: images the
    # post shows, and the files a live demo needs (.js, .css, .html, data).
    used = {i["src"] for i in p["images"] if "://" not in i.get("src", "")}
    img_bytes = 0
    for name in used:
        f = p["media"] / name
        if not f.is_file():
            sys.exit(f"{p['source']}: image {name} not found in {p['media']}")
        img_bytes += f.stat().st_size
    if p["media"].is_dir():
        shutil.copytree(p["media"], OUT / p["slug"], dirs_exist_ok=True)
    post_card(p)
    write(f"{p['slug']}/index.html", page_shell(base, p["title"], body, p["description"], post_meta(p), key=p["slug"], author=page_author(p)), img_bytes)
    if SITE.get("markdown_source"):
        write(f"{p['slug']}/index.md", p["raw"])


def build_one(path):
    """Re-render one post into the out/ of the last full build (the editor's preview while you
    type). Lists, tags, feeds and other pages stay as that build left them."""
    p = parse(Path(path))
    listed_tags = set()
    for f in (ROOT / "posts").glob("*.md"):
        head, _ = split_header(f.read_text())
        meta = {k.strip().lower(): v.strip() for k, v in (l.split(":", 1) for l in head.splitlines() if ":" in l)}
        if meta.get("publish", "true").lower() != "false" and meta.get("unlisted", "").lower() not in ("true", "yes"):
            listed_tags |= {tag_slug(t) for t in meta.get("tags", "").split(",") if t.strip()}
    render_post(p, read_template("base.html"), read_template("post.html"), listed_tags)
    return p["slug"]


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    if (ROOT / "static").exists():
        shutil.copytree(ROOT / "static", OUT, dirs_exist_ok=True)

    base = read_template("base.html")
    post_t = read_template("post.html")
    index_t = read_template("index.html")

    posts = [p for p in (parse(f) for f in (ROOT / "posts").glob("*.md")) if p["publish"]]
    posts.sort(key=lambda p: p["date"], reverse=True)
    seen = set()
    for p in posts:
        if p["slug"] in seen:
            sys.exit(f"duplicate slug {p['slug']}")
        seen.add(p["slug"])
    # unlisted: true keeps a post at its address but off the home page, tags, feeds and sitemap
    # (James, 2026-11-01: old posts he no longer likes); /archive/ lists them.
    listed = [p for p in posts if not p["unlisted"]]
    archived = [p for p in posts if p["unlisted"]]
    listed_tags = {tag_slug(t) for p in listed for t in p["tags"]}

    # posts
    for p in posts:
        render_post(p, base, post_t, listed_tags)

    # "mounts": {"chroma-subsampling/lab": "../compression-lab/docs"} publishes another
    # project's built pages inside this site, straight from its own repo. A mount inside a post's
    # folder appears only once that post is published, never as an orphan beside a draft.
    for dest, src in SITE.get("mounts", {}).items():
        parent = dest.split("/")[0]
        if "/" in dest and not (OUT / parent / "index.html").is_file():
            print(f"mount {dest} skipped: {parent} is not published")
            continue
        shutil.copytree((ROOT / src).resolve(), OUT / dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".*", "__pycache__"))

    # From here on, only listed posts: the archived ones appear on /archive/ and nowhere else.
    posts = listed

    # index and tag pages: date, writer and title only (James cut the summaries 2026-11-01:
    # they made the home page too long; they still feed the description meta and the feeds)
    def listing(items, heading="", template=index_t):
        # site.json "list_years": the first post of each year carries the year (class="new-year"
        # data-year="2026") for the stylesheet to show, and the dates drop it.
        years = SITE.get("list_years")
        rows, last = [], None
        for p in items:
            y = p["date"].year
            attrs = f' class="new-year" data-year="{y}"' if years and y != last else ""
            last = y
            if SITE.get("tag_filter"):
                attrs += f' data-tags="{esc(" ".join(tag_slug(t) for t in p["tags"]))}"'
            rows.append(f'<li{attrs}><span class="when"><time datetime="{p["date"].date().isoformat()}">'
                        f'{p["date"].strftime("%-d %b" if years else "%-d %b %Y")}</time>{writer_mark(p)}</span> '
                        f'<a href="/{p["slug"]}/">{esc(p["title"])}</a></li>')
        rows = "\n".join(rows)
        return render(template, heading=heading, posts=rows or "<li>Nothing yet.</li>")

    if SITE.get("card"):
        write_card(CARD, SITE["title"], subtitle=SITE["tagline"])
    home_t = optional_template("home.html")
    write("index.html", page_shell(base, SITE["title"], listing(posts, template=home_t or index_t),
                                   meta_extra=home_meta(), path="/"))
    for extra in SITE.get("post_lists", []):   # e.g. jpain.io's /blog/, kept from Bear
        write(f"{extra['path']}/index.html", page_shell(base, extra["title"], listing(posts, f"<h1>{esc(extra['title'])}</h1>"),
                                                        f"Every post on {SITE['title']}, newest first.", path=f"/{extra['path']}/"))
    # Tags that differ only in capitals ("AI", "ai") are one tag with one page.
    by_slug = {}
    for p in posts:
        for t in p["tags"]:
            by_slug.setdefault(tag_slug(t), set()).add(t)
    tags = sorted(by_slug)
    for ts in tags:
        name = sorted(by_slug[ts])[0]
        items = [p for p in posts if any(tag_slug(t) == ts for t in p["tags"])]
        write(f"tags/{ts}/index.html", page_shell(base, f"Tag: {name}", listing(items, f"<h1>Tagged “{esc(name)}”</h1>"),
                                                  f"Posts tagged “{name}” on {SITE['title']}.", path=f"/tags/{ts}/"))
    if archived:
        write("archive/index.html", page_shell(
            base, "Archive", listing(archived, f'<h1>Archive</h1><p>{esc(SITE.get("archive_intro", ""))}</p>'),
            f"Archived posts on {SITE['title']}.", meta_extra='<meta name="robots" content="noindex">', path="/archive/"))
    if tags:
        tl = "".join(f'<li><a href="/tags/{esc(ts)}/">{esc(sorted(by_slug[ts])[0])}</a></li>' for ts in tags)
        write("tags/index.html", page_shell(base, "Tags", f"<h1>Tags</h1><ul class=\"tags\">{tl}</ul>",
                                            f"Every tag used on {SITE['title']}.", path="/tags/"))

    # pages
    page_dates = {}
    for path in sorted((ROOT / "pages").glob("*.md")):
        pg = parse(path)
        meta = f'<p class="meta">{byline(pg)}</p>' if pg["byline"] else ""
        # <!-- contact-email --> in a page becomes a "Show email address" button (site.json "contact":
        # {"user", "domain"}, kept apart so the repo has no address either). Nothing while it is unset.
        pg["html"] = pg["html"].replace("<!-- contact-email -->", contact_email())
        body = f'<article><h1>{esc(pg["title"])}</h1>{meta}{pg["html"]}</article>'
        write(f"{pg['slug']}/index.html", page_shell(base, pg["title"], body, pg["summary"], path=f"/{pg['slug']}/", author=page_author(pg)))
        page_dates[pg["slug"]] = git_date(path)

    feeds(posts)

    # 404
    body_404 = optional_template("404.html")
    if body_404 is not None:
        write("404.html", page_shell(base, "404", body_404))

    # sitemap + robots + llms.txt
    # <lastmod>: a post's updated (or published) date, the newest post for the lists, a page's last commit.
    newest = max((p["updated"] for p in posts), default=None)
    entries = [("/", newest)] + [(f"/{p['slug']}/", p["updated"]) for p in posts] \
        + [(f"/{x['path']}/", newest) for x in SITE.get("post_lists", [])] \
        + [(f"/{slug}/", when) for slug, when in page_dates.items()]
    write("sitemap.xml", '<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{SITE['url']}{u}</loc>" + (f"<lastmod>{when.date().isoformat()}</lastmod>" if when else "")
                    + "</url>\n" for u, when in entries) + "</urlset>\n")
    fill = dict(site_url=SITE["url"], site_title=SITE["title"], tagline=SITE["tagline"], owner=SITE["owner"],
                owner_url=SITE["owner_url"], footer_statement=SITE["footer_statement"])
    robots = optional_template("robots.txt")
    write("robots.txt", render(robots, **fill) if robots is not None
          else f"User-agent: *\nAllow: /\n\nSitemap: {SITE['url']}/sitemap.xml\n")
    humans = optional_template("humans.txt")
    if humans is not None:
        models = sorted({p["model"] for p in posts if p["model"]})
        write("humans.txt", render(humans, models=", ".join(models) or "none yet",
                                   last_update=max((p["updated"] for p in posts), default=site_date(dt.datetime.now())).strftime("%Y/%m/%d"),
                                   **fill))
    llms = optional_template("llms.txt")
    if llms is not None:
        post_lines = "".join(
            f"- [{p['title']}]({SITE['url']}/{p['slug']}/): {p['summary'] or 'no summary'} "
            f"(written by {author_name(p)} `{p['model_id']}`, {p['date'].date().isoformat()})\n"
            if p["model_id"] else
            f"- [{p['title']}]({SITE['url']}/{p['slug']}/): {p['summary'] or 'no summary'} "
            f"(by {author_name(p)}, {p['date'].date().isoformat()})\n"
            for p in posts)
        write("llms.txt", render(llms.removesuffix("\n"), post_lines=post_lines or "(none yet)", **fill))
    print(f"built {len(posts)} post(s), {len(tags)} tag(s) -> {OUT}")


def feeds(posts):
    """Atom (always), plus RSS 2.0 and JSON Feed when site.json asks for them."""
    atom = SITE["atom"]
    updated = posts[0]["date"] if posts else site_date(dt.datetime.now())
    entry_author = atom.get("entry_author")

    def who(p):
        if cowritten(p):
            return f'{SITE["owner"]} and {p["model"]} ({p["model_id"]})'
        if entry_author and p["model_id"] and not p["reviewed"]:
            return f'{p["model"]} ({p["model_id"]}), not reviewed before publishing'
        return render(entry_author, model=p["model"], model_id=p["model_id"], reviewed=p["reviewed"]) \
            if entry_author and p["model_id"] else author_name(p)

    entries = "".join(
        f"""<entry>
<title>{esc(p["title"])}</title>
<link href="{SITE["url"]}/{p["slug"]}/"/>
<id>{SITE["url"]}/{p["slug"]}/</id>
<updated>{iso(p["date"])}</updated>
""" + (f"<published>{iso(p['date'])}</published>\n" if atom.get("published") else "")
        + (f"<summary>{esc(p['summary'])}</summary>\n" if atom.get("summary") else "")
        + f"""<author><name>{esc(who(p))}</name></author>
<content type="html">{esc(absolute_images(p["html"], p["slug"]))}</content>
</entry>
""" for p in posts)
    author_uri = f"<uri>{atom['author_uri']}</uri>" if atom.get("author_uri") else ""
    write(atom["file"], f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>{esc(SITE["title"])}</title>
<subtitle>{esc(SITE["tagline"])}</subtitle>
<link href="{SITE["url"]}/"/>
<link rel="self" href="{atom["self"]}"/>
<id>{atom["id"]}</id>
<updated>{iso(updated)}</updated>
<author><name>{html.escape(atom.get("author", SITE["owner"]), quote=False)}</name>{author_uri}</author>
{entries}</feed>
""")

    rss = SITE.get("rss")
    if rss:
        items = "".join(f"""<item>
<title>{esc(p["title"])}</title>
<link>{SITE["url"]}/{p["slug"]}/</link>
<guid isPermaLink="false">{SITE["url"]}/{p["slug"]}/</guid>
<pubDate>{email.utils.format_datetime(p["date"] if p["date"].tzinfo else p["date"].replace(tzinfo=dt.timezone.utc))}</pubDate>
<description>{esc(absolute_images(p["html"], p["slug"]))}</description>
</item>
""" for p in posts)
        write(rss["file"], f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{esc(SITE["title"])}</title>
<link>{SITE["url"]}/</link>
<description>{esc(SITE["tagline"])}</description>
<atom:link href="{esc(rss["self"])}" rel="self" type="application/rss+xml"/>
{items}</channel>
</rss>
""")

    jf = SITE.get("json_feed")
    if jf:
        def item(p):
            it = {
                "id": f"{SITE['url']}/{p['slug']}/",
                "url": f"{SITE['url']}/{p['slug']}/",
                "title": p["title"],
                "summary": p["summary"],
                "content_html": absolute_images(p["html"], p["slug"]),
                "date_published": iso(p["date"]),
                "tags": p["tags"],
                "authors": [{"name": SITE["owner"]}, {"name": f"{p['model']} ({p['model_id']})"}] if cowritten(p) else
                           [{"name": f"{p['model']} ({p['model_id']})" if p["model_id"] else author_name(p)}],
            }
            if jf.get("provenance") and p["model"]:
                it["_provenance"] = {"model": p["model"], "model_id": p["model_id"], "tool": p["tool"],
                                     "reviewed_by": p["reviewed"] or None, "source_markdown": f"{SITE['url']}/{p['slug']}/index.md",
                                     "revision": p["git"] and p["git"]["hash"], "words": p["words"]}
            return it
        write(jf["file"], json.dumps({
            "version": "https://jsonfeed.org/version/1.1",
            "title": SITE["title"],
            "description": SITE["tagline"],
            "home_page_url": SITE["url"] + "/",
            "feed_url": f"{SITE['url']}/{jf['file']}",
            "authors": [{"name": jf.get("author", SITE["owner"]), "url": SITE["url"] + "/about/"}],
            "language": "en",
            "items": [item(p) for p in posts],
        }, indent=1, ensure_ascii=False))


def check_images(post):
    """Problems with a post's images, as a list of strings."""
    problems, total = [], 0
    folder = post["media"]
    used = set()
    for img in post["images"]:
        src, alt = img.get("src", ""), img.get("alt", "").strip()
        if "://" in src or src.startswith("/"):
            problems.append(f"{src}: images must be local files in {folder.relative_to(ROOT)}/, not links")
            continue
        used.add(src)
        f = folder / src
        if not alt:
            problems.append(f"{src}: missing alt text")
        if not f.is_file():
            hint = " (the video's thumbnail: run tools/youtube.py, or reinsert the video in the editor)" if src.startswith("youtube-") else ""
            problems.append(f"{src}: not found in {folder.relative_to(ROOT)}/{hint}")
            continue
        if f.suffix.lower() not in IMAGE_TYPES:
            problems.append(f"{src}: unsupported type (use webp, png, jpg, svg, gif)")
            continue
        kb = f.stat().st_size / 1024
        total += kb
        if kb > IMAGE_MAX_KB:
            problems.append(f"{src}: {kb:.0f} KB, over {IMAGE_MAX_KB} KB (run tools/img.py)")
        if f.suffix.lower() != ".svg":
            with Image.open(f) as im:
                meta = {k for k in im.info if k.lower() in ("exif", "xmp", "comment", "parameters", "icc_profile") or k.startswith("XML")}
                if im.getexif():
                    meta.add("exif")
                if meta:
                    problems.append(f"{src}: carries metadata ({', '.join(sorted(meta))}); run tools/img.py")
                if im.width > 2400:
                    problems.append(f"{src}: {im.width}px wide, over 2400 (run tools/img.py)")
    if total > POST_IMAGES_MAX_KB:
        problems.append(f"images total {total:.0f} KB, over {POST_IMAGES_MAX_KB} KB for one post")
    if folder.is_dir():
        # Unused images are mistakes; other files (a demo's .js, .html, data) are served as they are.
        # Copies sharing a used image's name (negotiated.avif beside negotiated.jpg) are the
        # alternatives nginx picks between for format negotiation, not strays.
        stems = {Path(u).stem for u in used}
        # The hold-to-compare originals (data-b="x.png" on a panel) are used too.
        used |= set(re.findall(r'data-b="([^"/]+)"', post["html"]))
        # ...and a <video>'s poster frame.
        used |= set(re.findall(r'poster="([^"/]+)"', post["html"]))
        # ...and the share-card image named by meta_image.
        if post.get("image") and "/" not in post["image"]:
            used.add(post["image"])
        # ...and files a live demo loads are named in its own .js, .css or .html.
        demo_text = "".join(f.read_text(errors="ignore") for f in folder.iterdir()
                            if f.suffix.lower() in (".js", ".css", ".html"))
        for f in sorted(folder.iterdir()):
            if (f.name not in used and f.stem not in stems and f.name not in demo_text
                    and f.suffix.lower() in IMAGE_TYPES):
                problems.append(f"{f.name}: in {folder.relative_to(ROOT)}/ but not used in the post")
    return problems, total, len(used)


def check(paths):
    """Parse and render files without touching out/. Exits non-zero on problems."""
    for path in paths:
        p = Path(path).resolve()
        post = parse(p)
        for k in ("summary", "tags"):
            if not post[k]:
                sys.exit(f"{p}: missing header key '{k}'")
        problems, kb, n = check_images(post)
        if problems:
            sys.exit(f"{p}:\n  " + "\n  ".join(problems))
        print(f"ok {p}: '{post['title']}' slug={post['slug']} words={post['words']} "
              f"images={n} ({kb:.0f} KB) tags={','.join(post['tags'])} rfcs={','.join(post['rfcs']) or '-'}")


if __name__ == "__main__":
    args = sys.argv[1:]
    site = ENGINE
    if args[:1] == ["--site"]:
        site, args = Path(args[1]), args[2:]
    use_site(site)
    if len(args) > 1 and args[0] == "--check":
        check(args[1:])
    else:
        build()
