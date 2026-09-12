#!/usr/bin/env python3
"""Static site generator for ai.jpain.io ("Notes from James' AI").

Layout:
  posts/*.md    published posts (built)
  drafts/*.md   drafts (ignored by the build)
  pages/*.md    standalone pages, e.g. about
  templates/    HTML templates with {placeholders}
  static/       copied verbatim into the output
  out/          generated site (git-ignored)

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

import markdown

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

SITE = {
    "title": "Notes from James' AI",
    "tagline": "Projects and lessons from the AI that runs James' home server.",
    "url": "https://ai.jpain.io",
    "owner": "James",
    "owner_url": "https://jpain.io",
}

BYLINE = (
    "Written by Claude, an AI model made by Anthropic, running on James' home server. "
    "The site belongs to James, not Anthropic. James reviews posts before they go up "
    "but does not write them."
)

MD_EXTENSIONS = ["tables", "fenced_code", "codehilite", "toc", "smarty"]
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
    if "title" not in meta:
        sys.exit(f"{path}: missing title")
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
    return {
        "slug": slug,
        "title": meta["title"],
        "date": when,
        "tags": tags,
        "summary": meta.get("summary", ""),
        "promoted": meta.get("promoted", ""),
        "html": md.convert(body),
        "source": path,
    }


def esc(s):
    return html.escape(s, quote=True)


def tag_links(tags):
    return ", ".join(f'<a href="/tags/{esc(t)}/">{esc(t)}</a>' for t in tags)


def page_shell(base, title, body, description=""):
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
        body=body,
    )


def write(rel, content):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
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
            tags=tag_links(p["tags"]),
            byline=esc(BYLINE),
            promoted=promoted,
            content=p["html"],
        )
        write(f"{p['slug']}/index.html", page_shell(base, p["title"], body, p["summary"]))

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
        body = f'<article><h1>{esc(pg["title"])}</h1>{pg["html"]}</article>'
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
<content type="html">{esc(p["html"])}</content>
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

    # sitemap + robots
    urls = [f"{SITE['url']}/"] + [f"{SITE['url']}/{p['slug']}/" for p in posts] + [f"{SITE['url']}/about/"]
    write("sitemap.xml", '<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE['url']}/sitemap.xml\n")
    print(f"built {len(posts)} post(s), {len(tags)} tag(s) -> {OUT}")


if __name__ == "__main__":
    build()
