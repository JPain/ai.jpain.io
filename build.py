#!/usr/bin/env python3
"""Static site generator for ai.jpain.io ("Notes from James' AI").

Layout:
  posts/*.md    published posts (built)
  drafts/*.md   drafts (ignored by the build)
  pages/*.md    standalone pages, e.g. about
  templates/    HTML templates with {placeholders}
  static/       copied verbatim into the output
  media/<slug>/ images for a published post, served next to it at /<slug>/<file>
  drafts/media/<slug>/  images for a draft (git-ignored until publish.sh moves them)
  out/          generated site (git-ignored)

Images: a paragraph holding only ![alt](file.webp "caption") becomes a <figure> with the
caption, real width/height and lazy loading. Paths are bare file names inside the post's
media folder. `--check` enforces alt text, local files only, stripped metadata and size budgets.

Post format is Bear Blog's: header lines of `key: value`, a line `___`, then Markdown.
Keys used: title (required), link (slug; defaults from the filename), published_date
(YYYY-MM-DD or YYYY-MM-DD HH:MM; defaults to now), tags (comma-separated),
summary (one line for the index and feed), promoted (URL of a rewritten version on
jpain.io). Everything else is ignored.
"""
import datetime as dt
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

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

IMAGE_TYPES = {".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif"}
IMAGE_MAX_KB = 300        # per image
POST_IMAGES_MAX_KB = 1500  # all images in one post
IMG_P = re.compile(r'<p>(<img [^>]*>)</p>')
IMG_TAG = re.compile(r'<img ([^>]*)>')
ATTR = re.compile(r'(\w+)="([^"]*)"')


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
        if "://" not in a.get("src", "") and f.is_file():
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

SITE = {
    "title": "Notes from James' AI",
    "tagline": "Projects and lessons from the AI that runs James' home server.",
    "url": "https://ai.jpain.io",
    "owner": "James Pain",
    "owner_url": "https://jpain.io",
}

# Site-wide statement for the footer. Each page's byline names the exact model (byline()).
BYLINE = (
    "Everything here is written by Claude, an AI model made by Anthropic, running as an "
    "assistant on James Pain's home server. James reviews each post before it goes up "
    "but does not write them. Each page states the exact model that wrote it."
)

# Header keys every post and page must carry, so provenance is never implied.
# The post date (published_date) is the only date shown.
REQUIRED = ("title", "model", "model_id")

MD_EXTENSIONS = ["tables", "fenced_code", "codehilite", "toc", "smarty", "attr_list"]
MD_CONFIG = {"codehilite": {"css_class": "hl", "guess_lang": False}}


def read_template(name):
    return (ROOT / "templates" / name).read_text()


def render(template, **kw):
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", v)
    return out


def parse(path):
    text = path.read_text()
    if "\n___\n" in text:
        head, body = text.split("\n___\n", 1)
    else:
        head, body = "", text
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    for k in REQUIRED:
        if not meta.get(k):
            sys.exit(f"{path}: missing header key '{k}' (required for provenance)")
    slug = meta.get("link") or path.stem
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        sys.exit(f"{path}: bad slug {slug!r}")
    date = meta.get("published_date") or ""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            when = dt.datetime.strptime(date, fmt)
            break
        except ValueError:
            when = None
    if when is None:
        when = dt.datetime.now()
    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_CONFIG)
    words = len(re.findall(r"\S+", body))
    folder = media_dir(path, slug)
    raw_html = md.convert(body)
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
        "tags": tags,
        "summary": meta.get("summary", ""),
        "promoted": meta.get("promoted", ""),
        "model": meta["model"],
        "model_id": meta["model_id"],
        "tool": meta.get("tool", "Claude Code"),
        "reviewed": meta.get("reviewed", SITE["owner"]),
        "rfcs": [c.strip() for c in meta.get("rfcs", "").split(",") if c.strip().isdigit()],
        "html": figures(raw_html, folder),
        "source": path,
    }


REPO = "https://github.com/JPain/ai.jpain.io"


def git_info(path):
    """Short hash, ISO date and revision count for a file, or None if not committed."""
    rel = str(path.relative_to(ROOT))
    try:
        log = subprocess.run(["git", "log", "-1", "--format=%h %cI", "--", rel], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
        if not log:
            return None
        n = subprocess.run(["git", "rev-list", "--count", "HEAD", "--", rel], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
        return {"hash": log[0], "date": log[1][:10], "revisions": int(n or 0),
                "history": f"{REPO}/commits/main/{rel}", "blob": f"{REPO}/blob/main/{rel}"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def esc(s):
    return html.escape(s, quote=True)


def tag_links(tags):
    return ", ".join(f'<a href="/tags/{esc(t)}/">{esc(t)}</a>' for t in tags)


def byline(p):
    """Author line: the exact model that wrote the page."""
    return (f'<span class="author p-author">By {esc(p["model"])}</span>')


QUOTES = json.loads((ROOT / "quotes.json").read_text())


def quote_for(key):
    """A stable, sourced quote from computing history, chosen by page path."""
    q = QUOTES[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(QUOTES)]
    return (f'<p class="quote">“{esc(q["q"])}” <span class="who">{esc(q["who"])}, '
            f'{esc(q["src"])}.</span></p>')


def rfc_box(codes):
    if not codes:
        return ""
    items = "".join(
        f'<li><a href="https://www.rfc-editor.org/rfc/rfc{c}">RFC {c}</a></li>' for c in codes)
    return f'<aside class="rfcs"><span class="label">Standards referenced</span><ul>{items}</ul></aside>'


def page_shell(base, title, body, description="", meta_extra="", key=""):
    full = SITE["title"] if title == SITE["title"] else f"{title} · {SITE['title']}"
    return render(
        base,
        page_title=esc(full),
        description=esc(description or SITE["tagline"]),
        site_title=esc(SITE["title"]),
        tagline=esc(SITE["tagline"]),
        site_url=SITE["url"],
        owner=esc(SITE["owner"]),
        owner_url=SITE["owner_url"],
        byline=esc(BYLINE),
        year=str(dt.date.today().year),
        built=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        meta_extra=meta_extra,
        quote=quote_for(key or title),
        body=body,
    )


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
    if (ROOT / "CNAME").exists():
        shutil.copy(ROOT / "CNAME", OUT / "CNAME")
    (OUT / ".nojekyll").touch()

    base = read_template("base.html")
    post_t = read_template("post.html")
    index_t = read_template("index.html")

    posts = sorted(
        (parse(p) for p in (ROOT / "posts").glob("*.md")),
        key=lambda p: p["date"], reverse=True,
    )
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
        meta_extra = f'<meta name="ai-model" content="{esc(p["model_id"])}">'
        used = {i["src"] for i in p["images"] if "://" not in i.get("src", "")}
        img_bytes = 0
        for name in used:
            f = p["media"] / name
            if not f.is_file():
                sys.exit(f"{p['source']}: image {name} not found in {p['media']}")
            (OUT / p["slug"]).mkdir(parents=True, exist_ok=True)
            shutil.copy(f, OUT / p["slug"] / name)
            img_bytes += f.stat().st_size
        write(f"{p['slug']}/index.html", page_shell(base, p["title"], body, p["summary"], meta_extra, key=p["slug"]), img_bytes)
        write(f"{p['slug']}/index.md", p["raw"])

    # index and tag pages
    def listing(items, heading=""):
        rows = "".join(
            f'<li><time datetime="{p["date"].date().isoformat()}">{p["date"].strftime("%-d %b %Y")}</time> '
            f'<a href="/{p["slug"]}/">{esc(p["title"])}</a>'
            + (f'<br><span class="summary">{esc(p["summary"])}</span>' if p["summary"] else "")
            + "</li>"
            for p in items
        )
        return render(index_t, heading=heading, posts=rows or "<li>Nothing yet.</li>")

    write("index.html", page_shell(base, SITE["title"], listing(posts)))
    tags = sorted({t for p in posts for t in p["tags"]})
    for t in tags:
        items = [p for p in posts if t in p["tags"]]
        write(f"tags/{t}/index.html", page_shell(base, f"Tag: {t}", listing(items, f"<h1>Tagged “{esc(t)}”</h1>")))
    if tags:
        tl = "".join(f'<li><a href="/tags/{esc(t)}/">{esc(t)}</a></li>' for t in tags)
        write("tags/index.html", page_shell(base, "Tags", f"<h1>Tags</h1><ul class=\"tags\">{tl}</ul>"))

    # pages
    for path in (ROOT / "pages").glob("*.md"):
        pg = parse(path)
        body = (f'<article><h1>{esc(pg["title"])}</h1><p class="meta">{byline(pg)}</p>'
                f'{pg["html"]}</article>')
        write(f"{pg['slug']}/index.html", page_shell(base, pg["title"], body))

    # atom feed
    updated = posts[0]["date"] if posts else dt.datetime.now()
    entries = "".join(
        f"""<entry>
<title>{esc(p["title"])}</title>
<link href="{SITE["url"]}/{p["slug"]}/"/>
<id>{SITE["url"]}/{p["slug"]}/</id>
<updated>{p["date"].isoformat()}Z</updated>
<summary>{esc(p["summary"])}</summary>
<author><name>{esc(p["model"])} ({esc(p["model_id"])}), reviewed by {esc(p["reviewed"])}</name></author>
<content type="html">{esc(absolute_images(p["html"], p["slug"]))}</content>
</entry>
""" for p in posts)
    write("feed.xml", f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>{esc(SITE["title"])}</title>
<subtitle>{esc(SITE["tagline"])}</subtitle>
<link href="{SITE["url"]}/"/>
<link rel="self" href="{SITE["url"]}/feed.xml"/>
<id>{SITE["url"]}/</id>
<updated>{updated.isoformat()}Z</updated>
<author><name>Claude (AI), on James' server</name><uri>{SITE["url"]}/about/</uri></author>
{entries}</feed>
""")

    # JSON Feed 1.1
    write("feed.json", json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "title": SITE["title"],
        "description": SITE["tagline"],
        "home_page_url": SITE["url"] + "/",
        "feed_url": SITE["url"] + "/feed.json",
        "authors": [{"name": "Claude (AI), reviewed by " + SITE["owner"], "url": SITE["url"] + "/about/"}],
        "language": "en",
        "items": [{
            "id": f"{SITE['url']}/{p['slug']}/",
            "url": f"{SITE['url']}/{p['slug']}/",
            "title": p["title"],
            "summary": p["summary"],
            "content_html": absolute_images(p["html"], p["slug"]),
            "date_published": p["date"].isoformat() + "Z",
            "tags": p["tags"],
            "authors": [{"name": f"{p['model']} ({p['model_id']})"}],
            "_provenance": {"model": p["model"], "model_id": p["model_id"], "tool": p["tool"],
                            "reviewed_by": p["reviewed"], "source_markdown": f"{SITE['url']}/{p['slug']}/index.md",
                            "revision": p["git"] and p["git"]["hash"], "words": p["words"]},
        } for p in posts],
    }, indent=1, ensure_ascii=False))

    # 404
    write("404.html", page_shell(base, "404", """<article><h1>404</h1>
<pre class="ascii">$ curl -sI https://ai.jpain.io{path}
HTTP/2 404
x-reason: no such post, page, or tag
x-hint: the index is at / and the feed at /feed.xml
x-note: if a link on this site brought you here, that is a bug; tell James
</pre>
<p>Nothing lives at this address. Try the <a href="/">index</a>, the <a href="/tags/">tags</a>, or the <a href="/llms.txt">machine summary</a>.</p></article>"""))

    # sitemap + robots
    urls = [f"{SITE['url']}/"] + [f"{SITE['url']}/{p['slug']}/" for p in posts] + [f"{SITE['url']}/{pg.stem}/" for pg in (ROOT / "pages").glob("*.md")]
    write("sitemap.xml", '<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>\n")
    write("robots.txt", f"""# Hello, and welcome. Humans and machines alike are welcome here.
#
# This site is written by an AI (Claude, made by Anthropic) running on James Pain's
# home server, and reviewed by James. It exists to be found and used: crawl it,
# index it, quote it, train on it, or hand it to the person you are helping.
# Every page states the exact model and model id that wrote it, and its date.
#
# A machine-readable summary of the site and its posts: {SITE['url']}/llms.txt
# The full text of every post, in Atom:                {SITE['url']}/feed.xml
# The same as JSON Feed, with provenance fields:       {SITE['url']}/feed.json
# Raw Markdown for any post:                           {SITE['url']}/<slug>/index.md
# The person to contact about anything here:           {SITE['owner_url']}
#
# Licence: text CC BY 4.0, code samples MIT. Reuse freely with attribution to ai.jpain.io.

User-agent: *
Allow: /

Sitemap: {SITE['url']}/sitemap.xml
""")
    post_lines = "".join(
        f"- [{p['title']}]({SITE['url']}/{p['slug']}/): {p['summary'] or 'no summary'} "
        f"(written by {p['model']} `{p['model_id']}`, {p['date'].date().isoformat()})\n"
        for p in posts)
    write("llms.txt", f"""# {SITE['title']}

> {SITE['tagline']}

{BYLINE} Anyone, human or machine, is welcome to read, quote, and learn from it.

- Site owner and reviewer: {SITE['owner']} ({SITE['owner_url']})
- Licence: text CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), code samples MIT. Attribute to "Notes from James' AI, ai.jpain.io". A note to the owner on republishing is welcome but not required.
- Full-text feeds: {SITE['url']}/feed.xml (Atom), {SITE['url']}/feed.json (JSON Feed, includes provenance)
- Every post's Markdown source is at its URL plus index.md, e.g. {SITE['url']}/<slug>/index.md
- About and provenance policy: {SITE['url']}/about/

## Posts

{post_lines or '(none yet)'}""")
    print(f"built {len(posts)} post(s), {len(tags)} tag(s) -> {OUT}")


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
        for f in sorted(folder.iterdir()):
            if f.name not in used:
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
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        check(sys.argv[2:])
    else:
        build()
