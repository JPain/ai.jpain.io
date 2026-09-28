#!/usr/bin/env python3
"""
kudos -- the "Kudos" button under each jpain.io post, on Arctic.

Bear Blog had an upvote button ("toast"); James kept it when the blog moved to his
own server, renamed Kudos, starting from Bear's counts (seed file). Standard library
only, one JSON file, listening on localhost behind nginx.

  GET  /kudos/<slug>/  -> {"count": n, "given": bool}   given = this visitor already did
  POST /kudos/<slug>/  -> the same, after adding one (at most once per visitor per post)

A visitor is their IPv4 address, or the /64 of an IPv6 address (phones rotate the rest
every few hours). Only a keyed hash of that is kept, 16 hex characters per kudos, so
the file never holds an address. Only slugs that exist as posts on the site count,
and a POST whose Origin is another site is refused (a page elsewhere cannot spend
its visitors' kudos here). After each change the plain counts are also written to
KUDOS_PUBLIC for the private stats page.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LISTEN = os.environ.get("KUDOS_LISTEN", "127.0.0.1:8010")
STATE = Path(os.environ.get("KUDOS_STATE", "/var/lib/kudos"))
SITE = Path(os.environ.get("KUDOS_SITE", "/var/www/jpain.io"))
SEED = Path(os.environ.get("KUDOS_SEED", "/etc/kudos/seed.json"))
PUBLIC = os.environ.get("KUDOS_PUBLIC", "")          # counts only, for the stats page
ORIGINS = set(os.environ.get("KUDOS_ORIGINS", "https://jpain.io").split())
PATH_RE = re.compile(r"^/kudos/([a-z0-9-]{1,120})/$")

lock = threading.Lock()


def save(path: Path, data) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.chmod(tmp, 0o644 if path.parent != STATE else 0o600)
    os.replace(tmp, path)


def load() -> dict:
    f = STATE / "kudos.json"
    data = json.loads(f.read_text()) if f.exists() else {"posts": {}}
    if "secret" not in data:
        data["secret"] = secrets.token_hex(32)
    if SEED.exists():                                   # Bear's counts, applied once per post
        for slug, n in json.loads(SEED.read_text()).items():
            data["posts"].setdefault(slug, {"count": int(n), "seed": int(n), "by": []})
    return data


DATA = load()


def persist() -> None:
    save(STATE / "kudos.json", DATA)
    if PUBLIC:
        try:
            save(Path(PUBLIC), {s: p["count"] for s, p in DATA["posts"].items()})
        except OSError as e:
            print(f"could not write {PUBLIC}: {e}", file=sys.stderr)


def visitor(ip: str) -> str:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        a = None
    key = str(ipaddress.ip_network(f"{a}/64", strict=False)) if a and a.version == 6 else str(a or ip)
    return hmac.new(bytes.fromhex(DATA["secret"]), key.encode(), hashlib.sha256).hexdigest()[:16]


class Handler(BaseHTTPRequestHandler):
    server_version = "kudos"
    sys_version = ""

    def reply(self, code: int, body: dict | None = None) -> None:
        raw = json.dumps(body or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def target(self):
        m = PATH_RE.match(self.path)
        if not m or not (SITE / m.group(1) / "index.html").is_file():
            self.reply(404, {"error": "no such post"})
            return None
        return m.group(1)

    def do_GET(self):
        slug = self.target()
        if slug:
            p = DATA["posts"].get(slug, {"count": 0, "by": []})
            self.reply(200, {"count": p["count"], "given": visitor(self.ip()) in p["by"]})

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in ORIGINS:
            self.reply(403, {"error": "kudos come from the post page"})
            return
        slug = self.target()
        if not slug:
            return
        who = visitor(self.ip())
        with lock:
            p = DATA["posts"].setdefault(slug, {"count": 0, "by": []})
            if who not in p["by"]:
                p["by"].append(who)
                p["count"] += 1
                persist()
                print(f"kudos {slug} -> {p['count']}", flush=True)
            self.reply(200, {"count": p["count"], "given": True})

    def ip(self) -> str:
        # nginx sets X-Real-IP; we only listen on localhost, so nobody else can.
        return self.headers.get("X-Real-IP") or self.client_address[0]

    def log_message(self, fmt, *args):   # nginx already logs every request
        pass


if __name__ == "__main__":
    with lock:
        persist()
    host, port = LISTEN.rsplit(":", 1)
    print(f"kudos on {LISTEN}, {len(DATA['posts'])} posts, site {SITE}", flush=True)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()
