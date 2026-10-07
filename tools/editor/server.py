#!/usr/bin/env python3
"""jpain.io editor: edit posts and drafts in a browser, preview them with the real engine, publish.

  /mnt/work/venvs/blog/bin/python tools/editor/server.py [--port 8099]

Runs on Case as jpain-editor.service at http://case:8099/ and answers the tailnet and
localhost only. The posts stay plain files: this edits posts/*.md and drafts/*.md in place,
so a terminal, git or Claude can work on the same files. Saving never touches the live site;
Publish runs ./publish.sh exactly as from a terminal.

  GET  /                       the editor (an <iframe> asking for / gets the preview's home)
  GET  /_api/list              posts and drafts, with whether each has unpublished changes
  GET  /_api/file?path=        a file's text and hash
  PUT  /_api/file              {path, text, hash}: save, refused (409) if the file changed since
  POST /_api/new               {title}: create drafts/<slug>.md
  POST /_api/preview           {path, text}: build the site with this text in place, run the checks
  POST /_api/publish           {path}: ./publish.sh (drafts move to posts/)
  GET  /_api/media?path=       the post's media files
  POST /_api/upload?path=&name=  raw image body: stripped, scaled to 1600 px, saved as WebP
  anything else                the last preview build (so /<slug>/, /fonts/... resolve as on the site)
"""
import argparse
import hashlib
import io
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SITE = HERE.parent.parent                      # ops/blog: the engine and the jpain.io site
ENGINE = SITE / "build.py"
PY = "/mnt/work/venvs/blog/bin/python"
PREVIEW = Path(os.environ.get("EDITOR_PREVIEW", "/mnt/work/cache/jpain-editor"))
HOST_NAMES = {"case", "localhost"}

# Who a publish from the editor is by: James, with no AI trailer (publish.sh adds one by default).
AUTHOR_ENV = {"GIT_AUTHOR_NAME": "James Pain", "GIT_AUTHOR_EMAIL": "jamesepain@gmail.com",
              "GIT_COMMITTER_NAME": "James Pain", "GIT_COMMITTER_EMAIL": "jamesepain@gmail.com",
              "PUBLISH_TRAILER": ""}

TAILNET = [ipaddress.ip_network(n) for n in ("100.64.0.0/10", "fd7a:115c:a1e0::/48", "127.0.0.0/8", "::1/128")]
build_lock = threading.Lock()
publish_lock = threading.Lock()

NEW_POST = """---
title: {title}
slug: {slug}
published_date:
tags:
meta_description:
meta_image:
---

"""


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def header(text):
    """The header keys, as build.py reads them (lower-cased, first colon splits): front matter
    between --- lines (James' posts), or key: value lines before ___ (the AI's)."""
    m = re.match(r"---\n(.*?)\n---", text, re.S) or re.match(r"(.*?)\n___\n", text, re.S)
    meta = {}
    for line in (m.group(1) if m else "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta


def slug_of(path, text):
    meta = header(text)
    return meta.get("link") or meta.get("slug") or path.stem


def source(rel):
    """A post or draft path from the browser, checked: posts/x.md or drafts/x.md, nothing else."""
    if not re.fullmatch(r"(posts|drafts)/[a-z0-9][a-z0-9-]*\.md", rel or ""):
        raise ValueError(f"not a post or draft: {rel!r}")
    return SITE / rel


def media_for(path, text):
    slug = slug_of(path, text)
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError(f"bad slug {slug!r}")
    return SITE / ("drafts/media" if path.parent.name == "drafts" else "media") / slug


def unpublished(rel):
    """True when a post differs from the last commit, i.e. saved here but not yet live."""
    r = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=SITE, capture_output=True, text=True)
    return bool(r.stdout.strip())


def listing():
    out = []
    for kind in ("posts", "drafts"):
        for f in sorted((SITE / kind).glob("*.md")):
            text = f.read_text()
            meta = header(text)
            rel = f"{kind}/{f.name}"
            out.append({"path": rel, "kind": kind, "title": meta.get("title") or f.stem,
                        "slug": slug_of(f, text), "date": (meta.get("published_date") or "")[:10],
                        "hidden": meta.get("publish", "").lower() == "false",
                        "unpublished": kind == "posts" and unpublished(rel)})
    drafts = [p for p in out if p["kind"] == "drafts"]
    posts = sorted((p for p in out if p["kind"] == "posts"), key=lambda p: p["date"], reverse=True)
    return drafts + posts


def run(cmd, env=None, timeout=60):
    r = subprocess.run(cmd, cwd=SITE, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **(env or {})})
    return r.returncode, (r.stdout + r.stderr).strip()


def preview(rel, text):
    """Build the whole site into PREVIEW with this one file's text in place, then check it.

    Every other post is a symlink to the real file, so the preview is the site as it would
    be after publishing this text. A draft is built as a post, dated now if undated."""
    path = source(rel)
    slug = slug_of(path, text)
    with build_lock:
        PREVIEW.mkdir(parents=True, exist_ok=True)
        for name in ("templates", "static", "pages", "quotes.json"):
            link = PREVIEW / name
            if not link.is_symlink():
                shutil.rmtree(link, ignore_errors=True) if link.is_dir() else link.unlink(missing_ok=True)
                link.symlink_to(SITE / name)
        site = json.loads((SITE / "site.json").read_text())
        site["mounts"] = {k: str((SITE / v).resolve()) for k, v in site.get("mounts", {}).items()}
        (PREVIEW / "site.json").write_text(json.dumps(site))
        for name in ("posts", "media"):
            shutil.rmtree(PREVIEW / name, ignore_errors=True)
            (PREVIEW / name).mkdir()
        for f in (SITE / "posts").glob("*.md"):
            if f != path:
                (PREVIEW / "posts" / f.name).symlink_to(f)
        for d in (SITE / "media").iterdir():
            (PREVIEW / "media" / d.name).symlink_to(d)
        media = media_for(path, text)
        target = PREVIEW / "media" / slug
        if target.is_symlink():
            target.unlink()
        if media.is_dir():
            target.symlink_to(media)
        mine = PREVIEW / "posts" / path.name
        if mine.is_symlink():
            mine.unlink()
        mine.write_text(text)
        code, log = run([PY, str(ENGINE), "--site", str(PREVIEW)])
        if code:
            return {"ok": False, "built": False, "message": plain(log.splitlines()[-1]) if log else "build failed"}
        code, log = run([PY, str(ENGINE), "--site", str(PREVIEW), "--check", str(mine)])
        return {"ok": code == 0, "built": True, "slug": slug, "message": plain(log)}


FRIENDLY = {"missing header key 'summary'": "Add a meta_description: line, the one-line summary for lists, feeds and search.",
            "missing header key 'tags'": "Add a tags: line, e.g. tags: linux, windows"}


def plain(log):
    """The checker's message without file paths, and in words for the common ones."""
    msg = re.sub(r"^\S+\.md:\s*", "", log.strip(), flags=re.M)
    for k, v in FRIENDLY.items():
        msg = msg.replace(k, v)
    return re.sub(r"^ok .*$", "Checks pass", msg, flags=re.M)


def publish(rel):
    path = source(rel)
    if not path.exists():
        raise ValueError(f"{rel} does not exist")
    title = header(path.read_text()).get("title") or path.stem
    with publish_lock:
        if path.parent.name == "drafts":
            code, log = run(["./publish.sh", f"drafts/{path.name}"], AUTHOR_ENV, timeout=300)
            return {"ok": code == 0, "path": f"posts/{path.name}" if code == 0 else rel, "log": log,
                    "reason": "" if code == 0 else plain(log.splitlines()[-1] if log else "")}
        code, log = run(["./publish.sh"], {**AUTHOR_ENV, "PUBLISH_MSG": f"Edit: {title}"}, timeout=300)
        return {"ok": code == 0, "path": rel, "log": log,
                "reason": "" if code == 0 else plain(log.splitlines()[-1] if log else "")}


def upload(rel, name, data):
    path = source(rel)
    text = path.read_text() if path.exists() else ""
    folder = media_for(path, text)
    stem = re.sub(r"[^a-z0-9-]+", "-", Path(name).stem.lower()).strip("-") or "image"
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") and ("transparency" in im.info or im.mode != "P") else "RGB")
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
    clean = Image.new(im.mode, im.size)          # a fresh image carries no EXIF, GPS or profile
    clean.paste(im)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{stem}.webp"
    n = 2
    while out.exists():
        out = folder / f"{stem}-{n}.webp"
        n += 1
    for q in (80, 72, 64, 56):                   # the build allows 300 KB per image
        buf = io.BytesIO()
        clean.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() <= 290 * 1024:
            break
    out.write_bytes(buf.getvalue())
    return {"name": out.name, "kb": round(buf.tell() / 1024), "width": clean.width, "height": clean.height}


class Handler(BaseHTTPRequestHandler):
    server_version = "jpain-editor"

    def log_message(self, fmt, *args):
        if not self.path.startswith("/_api/") or self.command != "GET":
            super().log_message(fmt, *args)

    # -- guards -------------------------------------------------------------
    def allowed(self):
        ip = ipaddress.ip_address(self.client_address[0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not any(ip in n for n in TAILNET):
            return False
        # Only our own names: stops a web page elsewhere reaching this through DNS rebinding.
        host = urllib.parse.urlsplit("//" + (self.headers.get("Host") or "")).hostname or ""
        if host in HOST_NAMES or (host.startswith("case.") and host.endswith(".ts.net")):
            return True
        try:
            return any(ipaddress.ip_address(host) in n for n in TAILNET)
        except ValueError:
            return False

    def same_origin(self):
        # Changes need our custom header, which a page on another site can't send without a
        # CORS preflight this server never approves.
        return self.headers.get("X-Editor") == "1"

    # -- responses ----------------------------------------------------------
    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 40 * 1024 * 1024:
            raise ValueError("too large")
        return self.rfile.read(n)

    def query(self):
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}

    def static(self, root, rel):
        f = (root / rel).resolve()
        base = root.resolve()
        if f.is_dir():
            f = f / "index.html"
        if not f.is_relative_to(base) or not f.is_file():
            # The preview's own 404 page, when there is one.
            nf = root / "404.html"
            return self.send(404, nf.read_bytes() if nf.is_file() else b"not found", "text/html; charset=utf-8")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send(200, f.read_bytes(), ctype)

    # -- routes -------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {"error": "tailnet only"})
        url = urllib.parse.urlsplit(self.path)
        p = urllib.parse.unquote(url.path)
        try:
            if p == "/_api/list":
                return self.send(200, listing())
            if p == "/_api/file":
                path = source(self.query().get("path"))
                text = path.read_text()
                return self.send(200, {"path": self.query()["path"], "text": text, "hash": digest(text),
                                       "slug": slug_of(path, text)})
            if p == "/_api/media":
                path = source(self.query().get("path"))
                folder = media_for(path, path.read_text())
                files = sorted(f.name for f in folder.iterdir() if f.is_file()) if folder.is_dir() else []
                return self.send(200, {"files": files})
            if p in ("/_edit/editor.js", "/_edit/editor.css"):
                return self.static(HERE, p[len("/_edit/"):])
            if p == "/" and self.headers.get("Sec-Fetch-Dest") not in ("iframe", "frame"):
                return self.static(HERE, "index.html")
            if ".." in p.split("/"):
                return self.send(400, {"error": "bad path"})
            with build_lock:
                return self.static(PREVIEW / "out", p.lstrip("/"))
        except (ValueError, FileNotFoundError, KeyError) as e:
            return self.send(400, {"error": str(e)})

    def do_PUT(self):
        if not (self.allowed() and self.same_origin()):
            return self.send(403, {"error": "forbidden"})
        try:
            if urllib.parse.urlsplit(self.path).path != "/_api/file":
                return self.send(404, {"error": "no such endpoint"})
            req = json.loads(self.body())
            path = source(req["path"])
            current = path.read_text() if path.exists() else ""
            if path.exists() and req.get("hash") != digest(current) and not req.get("force"):
                return self.send(409, {"error": "changed on disk since you opened it",
                                       "text": current, "hash": digest(current)})
            path.write_text(req["text"])
            return self.send(200, {"hash": digest(req["text"]), "unpublished": path.parent.name == "posts" and unpublished(req["path"])})
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return self.send(400, {"error": str(e)})

    def do_POST(self):
        if not (self.allowed() and self.same_origin()):
            return self.send(403, {"error": "forbidden"})
        p = urllib.parse.urlsplit(self.path).path
        try:
            if p == "/_api/upload":
                q = self.query()
                return self.send(200, upload(q.get("path"), q.get("name", "image"), self.body()))
            req = json.loads(self.body() or b"{}")
            if p == "/_api/preview":
                return self.send(200, preview(req["path"], req["text"]))
            if p == "/_api/publish":
                return self.send(200, publish(req["path"]))
            if p == "/_api/new":
                title = (req.get("title") or "").strip()
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-")
                if not slug:
                    raise ValueError("give the post a title")
                if any((SITE / d / f"{slug}.md").exists() for d in ("posts", "drafts")):
                    raise ValueError(f"a post or draft called {slug} already exists")
                (SITE / "drafts" / f"{slug}.md").write_text(NEW_POST.format(title=title, slug=slug))
                return self.send(200, {"path": f"drafts/{slug}.md"})
            return self.send(404, {"error": "no such endpoint"})
        except (ValueError, KeyError, json.JSONDecodeError, OSError) as e:
            return self.send(400, {"error": str(e)})
        except subprocess.TimeoutExpired:
            return self.send(504, {"error": "timed out"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--bind", default="::")
    a = ap.parse_args()
    ThreadingHTTPServer.address_family = __import__("socket").AF_INET6 if ":" in a.bind else __import__("socket").AF_INET
    ThreadingHTTPServer.daemon_threads = True
    srv = ThreadingHTTPServer((a.bind, a.port), Handler)
    first = next(iter(sorted((SITE / "posts").glob("*.md"))), None)
    if first:                                    # so /fonts/ and the favicon exist before any preview
        preview(f"posts/{first.name}", first.read_text())
    print(f"jpain.io editor on http://case:{a.port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
