#!/usr/bin/env python3
"""Static site generator for James' blogs: ai.jpain.io ("Notes from James' AI") and jpain.io.

One engine, one folder per site. The site folder holds everything that belongs to that site:
  site.json     settings: title, URL, owner, which header keys are required, feed layout
  posts/*.md    published posts (built)
  drafts/*.md   drafts (ignored by the build)
  pages/*.md    standalone pages, e.g. about
  templates/    HTML templates with {placeholders}; optional home.html, 404.html, robots.txt, llms.txt
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
publish (false = not built), promoted (URL of a rewritten version on jpain.io), model and
model_id (provenance; required on ai.jpain.io). Everything else is ignored.
"""
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
    return re.sub(r'<img (?![^>]*loading=)([^>]*)>', lambda m: tag(m), out)


def absolute_images(html_text, slug):
    """Feeds are read out of context, so image paths must be absolute there."""
    return re.sub(r'src="(?![a-z]+://|/)([^"]+)"', lambda m: f'src="{SITE["url"]}/{slug}/{m.group(1)}"', html_text)


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
    # "smart_quotes": false keeps quotes and ... exactly as typed (jpain.io, as on Bear).
    exts = [e for e in MD_EXTENSIONS if SITE.get("smart_quotes", True) or e != "smarty"]
    md = markdown.Markdown(extensions=exts, extension_configs=MD_CONFIG)
    words = len(re.findall(r"\S+", body))
    folder = media_dir(path, slug)
    raw_html = md.convert(bear_markdown(body) if SITE.get("bear_markdown") else body)
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
        "image": meta.get("meta_image", ""),
        "author": meta.get("author", ""),
        "publish": meta.get("publish", "true").lower() != "false",
        "promoted": meta.get("promoted", ""),
        "model": meta.get("model", ""),
        "model_id": meta.get("model_id", ""),
        "tool": meta.get("tool", "Claude Code"),
        "reviewed": meta.get("reviewed", SITE["owner"]),
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


def tag_links(tags):
    return ", ".join(f'<a href="/tags/{esc(tag_slug(t))}/">{esc(t)}</a>' for t in tags)


def author_name(p):
    """Who wrote it, as plain text: the model on ai.jpain.io, the post's author or the owner elsewhere."""
    if SITE["byline"] == "model":
        return p["model"]
    return p["author"] or SITE["owner"]


def byline(p):
    # "byline": "explicit" (jpain.io) shows one only when the post names an author, e.g.
    # "James Pain, with Claude"; James' other posts have none, as on Bear.
    if SITE["byline"] == "explicit" and not p["author"]:
        return ""
    return f'<span class="author p-author">By {esc(author_name(p))}</span>'


QUOTES = []


def quote_for(key):
    """A stable, sourced quote from computing history, chosen by page path."""
    if not QUOTES:
        return ""
    q = QUOTES[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(QUOTES)]
    return (f'<p class="quote">“{esc(q["q"])}” <span class="who">{esc(q["who"])}, '
            f'{esc(q["src"])}.</span></p>')


def rfc_box(codes):
    if not codes:
        return ""
    items = "".join(
        f'<li><a href="https://www.rfc-editor.org/rfc/rfc{c}">RFC {c}</a></li>' for c in codes)
    return f'<aside class="rfcs"><span class="label">Standards referenced</span><ul>{items}</ul></aside>'


def owner_ld():
    """The site's owner as a schema.org Person. Both blogs name the same one, by the same @id."""
    person = {"@type": "Person", "@id": f'{SITE["owner_url"]}/#person', "name": SITE["owner"],
              "url": SITE["owner_url"]}
    if SITE.get("same_as"):
        person["sameAs"] = SITE["same_as"]
    return person


def model_ld(p):
    """The model that wrote (or helped write) a post. It is not a Person, so it is described as software."""
    return {"@type": "SoftwareApplication", "name": p["model"], "softwareVersion": p["model_id"],
            "applicationCategory": "AI language model", "creator": {"@type": "Organization", "name": "Anthropic"}}


def json_ld(data):
    """A <script type="application/ld+json"> block. It is data, so script-src in the CSP doesn't apply."""
    text = json.dumps({"@context": "https://schema.org", **data}, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("</", "<\\/")   # a "</script>" inside a string must not end the block
    return f'\n<script type="application/ld+json">{text}</script>'


def post_image(p):
    """The share image: meta_image if set, otherwise the first image the post shows."""
    url = f'{SITE["url"]}/{p["slug"]}/'
    src = p["image"] or next((i["src"] for i in p["images"] if i.get("src") and "://" not in i["src"]), "")
    return src if "://" in src or not src else url + src


def head_meta(path, title, description, og_type="website", image=""):
    """Canonical link on every page; Open Graph and Twitter card tags where site.json has share_cards."""
    url = SITE["url"] + path
    out = f'<link rel="canonical" href="{url}">'
    if SITE.get("share_cards"):
        tags = [("og:type", og_type), ("og:title", title), ("og:url", url), ("og:site_name", SITE["title"]),
                ("og:description", description or SITE["tagline"])]
        if image:
            tags.append(("og:image", image))
        out += "".join(f'\n<meta property="{k}" content="{esc(v)}">' for k, v in tags)
        out += f'\n<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">'
    return out


def page_shell(base, title, body, description="", meta_extra="", key="", path=None):
    full = SITE["title"] if title == SITE["title"] else f"{title} · {SITE['title']}"
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
        owner=esc(SITE["owner"]),
        owner_url=SITE["owner_url"],
        byline=esc(SITE["footer_statement"]),
        year=str(dt.date.today().year),
        built=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        meta_extra=meta_extra,
        quote=quote_for(key or title),
        body=body,
    )


def post_meta(p):
    """Extra <head> tags for a post: provenance when a model wrote it, canonical, share cards, BlogPosting."""
    url = f'{SITE["url"]}/{p["slug"]}/'
    image = post_image(p)
    out = f'<meta name="ai-model" content="{esc(p["model_id"])}">\n' if p["model_id"] else ""
    out += head_meta(f'/{p["slug"]}/', p["title"], p["summary"], "article", image)
    if SITE.get("share_cards"):
        out += f'\n<meta property="article:published_time" content="{iso(p["date"])}">'
        if p["updated"] != p["date"]:
            out += f'\n<meta property="article:modified_time" content="{iso(p["updated"])}">'
    ld = {"@type": "BlogPosting", "@id": f"{url}#post", "url": url, "mainEntityOfPage": url,
          "headline": p["title"], "datePublished": iso(p["date"]), "dateModified": iso(p["updated"]),
          "inLanguage": "en", "isPartOf": {"@id": f'{SITE["url"]}/#website'}, "publisher": owner_ld()}
    if p["summary"]:
        ld["description"] = p["summary"]
    if p["tags"]:
        ld["keywords"] = p["tags"]
    if image:
        ld["image"] = image
    if SITE["byline"] == "model":
        # ai.jpain.io: the model wrote it and James reviewed it; say exactly that.
        ld["author"] = model_ld(p)
        ld["editor"] = owner_ld()
    else:
        ld["author"] = owner_ld()
        if p["model_id"]:
            ld["contributor"] = model_ld(p)
    return out + json_ld(ld)


def home_meta():
    """JSON-LD for the home page: the site and who runs it."""
    return json_ld({"@graph": [
        {"@type": "WebSite", "@id": f'{SITE["url"]}/#website', "url": f'{SITE["url"]}/', "name": SITE["title"],
         "description": SITE["tagline"], "inLanguage": "en", "publisher": {"@id": f'{SITE["owner_url"]}/#person'}},
        owner_ld(),
    ]})


def write(rel, content, image_bytes=0):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if "{page_kb}" in content:
        kb = len(content.replace("{page_kb}", "00.0").encode()) / 1024
        weight = f"{kb:.1f} KB of HTML"
        if image_bytes:
            weight += f" and {image_bytes / 1024:.0f} KB of images"
        content = content.replace("{page_kb} KB of HTML", weight).replace("{page_kb}", f"{kb:.1f}")
    p.write_text(content)


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

    # posts
    for p in posts:
        promoted = ""
        if p["promoted"]:
            promoted = (f'<p class="promoted">James rewrote this one for his own blog: '
                        f'<a href="{esc(p["promoted"])}">{esc(p["promoted"])}</a></p>')
        body = render(
            post_t,
            title=esc(p["title"]),
            date=p["date"].strftime("%-d %B %Y"),
            iso_date=p["date"].date().isoformat(),
            slug=p["slug"],
            tags=tag_links(p["tags"]),
            author=byline(p),
            promoted=promoted,
            content=p["html"] + rfc_box(p["rfcs"]),
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
        write(f"{p['slug']}/index.html", page_shell(base, p["title"], body, p["summary"], post_meta(p), key=p["slug"]), img_bytes)
        if SITE.get("markdown_source"):
            write(f"{p['slug']}/index.md", p["raw"])

    # "mounts": {"image-compression-colour-ceiling/lab": "../compression-lab/docs"} publishes another
    # project's built pages inside this site, straight from its own repo. A mount inside a post's
    # folder appears only once that post is published, never as an orphan beside a draft.
    for dest, src in SITE.get("mounts", {}).items():
        parent = dest.split("/")[0]
        if "/" in dest and not (OUT / parent / "index.html").is_file():
            print(f"mount {dest} skipped: {parent} is not published")
            continue
        shutil.copytree((ROOT / src).resolve(), OUT / dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".*", "__pycache__"))

    # index and tag pages
    def listing(items, heading="", template=index_t):
        rows = "".join(
            ("<li>" if not SITE.get("tag_filter") else f'<li data-tags="{esc(" ".join(tag_slug(t) for t in p["tags"]))}">')
            + f'<time datetime="{p["date"].date().isoformat()}">{p["date"].strftime("%-d %b %Y")}</time> '
            f'<a href="/{p["slug"]}/">{esc(p["title"])}</a>'
            + (f'<br><span class="summary">{esc(p["summary"])}</span>' if p["summary"] else "")
            + "</li>"
            for p in items
        )
        return render(template, heading=heading, posts=rows or "<li>Nothing yet.</li>")

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
    if tags:
        tl = "".join(f'<li><a href="/tags/{esc(ts)}/">{esc(sorted(by_slug[ts])[0])}</a></li>' for ts in tags)
        write("tags/index.html", page_shell(base, "Tags", f"<h1>Tags</h1><ul class=\"tags\">{tl}</ul>",
                                            f"Every tag used on {SITE['title']}.", path="/tags/"))

    # pages
    page_dates = {}
    for path in sorted((ROOT / "pages").glob("*.md")):
        pg = parse(path)
        body = (f'<article><h1>{esc(pg["title"])}</h1><p class="meta">{byline(pg)}</p>'
                f'{pg["html"]}</article>')
        write(f"{pg['slug']}/index.html", page_shell(base, pg["title"], body, pg["summary"], path=f"/{pg['slug']}/"))
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
                "authors": [{"name": f"{p['model']} ({p['model_id']})" if p["model_id"] else author_name(p)}],
            }
            if jf.get("provenance"):
                it["_provenance"] = {"model": p["model"], "model_id": p["model_id"], "tool": p["tool"],
                                     "reviewed_by": p["reviewed"], "source_markdown": f"{SITE['url']}/{p['slug']}/index.md",
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
            problems.append(f"{src}: not found in {folder.relative_to(ROOT)}/")
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
