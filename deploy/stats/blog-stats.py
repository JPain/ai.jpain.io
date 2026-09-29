#!/usr/bin/env python3
"""
blog-stats -- private view counts for ai.jpain.io and jpain.io, from nginx's own logs.

Modelled on ops/filehost/stats/filehost-stats.py and using its definitions, so the
numbers mean the same on both pages. No database: the log archive is the record
(kept 400 days by /etc/logrotate.d/blogs). Every five minutes this reads it end to
end and writes stats.json, which the Tailscale-only page /blogs/ shows. Readers see
none of it; only the kudos count is public (on the button).

  * a VIEW is a GET of a page (HTML, answered 200/304); one visitor's views of one
    page within 30 minutes count once, so refreshes and back-and-forth don't inflate;
  * VISITORS are distinct addresses (approximate: shared mobile addresses, rotating
    IPv6 privacy addresses);
  * YOU are views from James's own networks, counted apart;
  * BOTS are crawlers, link previews and scripts, by user agent, counted apart.
    Many scrapers pose as Chrome, so a view also needs proof of a browser: the same
    address fetched the stylesheet within 30 minutes either side (a browser always
    does, or revalidates it: 304). HTML-only fetches count as bots;
  * FEED READERS: services that report subscribers in their user agent (Feedly,
    Inoreader, NewsBlur...) count as that many; any other reader counts once per
    address and agent over the last 7 days.
nginx logs the path AFTER its internal rewrites: "/" is "/index.html", a post is
"/<slug>/index.html", Bear's "/feed/" is "/feed/atom.xml".
"""
from __future__ import annotations

import gzip
import html
import ipaddress
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

LOGDIR = Path(os.environ.get("STATS_LOGDIR", "/var/log/nginx/blogs"))
WWW = Path(os.environ.get("STATS_WWW", "/var/www"))
OUT = Path(os.environ.get("STATS_OUT", "/var/www/blog-stats/stats.json"))
SITES = os.environ.get("STATS_SITES", "jpain.io ai.jpain.io").split()
VIEW_WINDOW = 30 * 60
DAYS = 90

LOADED = {200, 304}
FEEDS = {"/feed/atom.xml", "/feed/rss.xml", "/feed.xml", "/feed.json"}
# Same lists as filehost-stats.py; keep them in step.
BOT_RE = re.compile(r"bot|crawl|spider|slurp|facebookexternalhit|meta-external|meta-webindexer|preview|"
                    r"discord|slack|telegram|whatsapp|skype|embedly|curl|wget|python|go-http|okhttp|java/|"
                    r"libwww|httpclient|headless|playwright|blackbox|monitor|uptime|scan|check|zgrab", re.I)
OWN = [ipaddress.ip_network(n) for n in (
    "81.2.117.78/32", "2001:8b0:b1f3::/48", "2001:8b0:dc1d::/48",     # home: A&A IPv4 + both /48s
    "85.17.65.153/32", "2001:1af8:4700:a089::/64",                     # Arctic itself (tests, checks)
    "95.211.45.90/32", "2001:1af8:5301:109::/64",                      # Fern itself (tests, checks)
    "100.64.0.0/10", "fd7a:115c:a1e0::/48")]                           # the tailnet
SUBSCRIBERS_RE = re.compile(r"(\d+)\s+(?:subscribers|readers)", re.I)


def own(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for n in OWN if a.version == n.version)


def lines(site: str):
    files = sorted(LOGDIR.glob(f"{site}.access.log*"), key=lambda p: p.stat().st_mtime)
    for f in files:
        opener = gzip.open if f.suffix == ".gz" else open
        try:
            with opener(f, "rt", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("{"):
                        yield line
        except OSError as e:
            print(f"skipping {f}: {e}", file=sys.stderr)


def title_of(site: str, page: str) -> str:
    f = WWW / site / page.lstrip("/") / "index.html"
    try:
        m = re.search(r"<title>(.*?)</title>", f.read_text(errors="replace"), re.S)
    except OSError:
        return ""
    t = html.unescape(m.group(1)).strip() if m else ""
    return re.sub(r"\s+·\s+[^·]+$", "", t)          # drop " · Site name"


def css_times(site: str) -> dict:
    """ip -> sorted epochs of stylesheet loads: the proof that a browser rendered a page."""
    seen = defaultdict(list)
    for line in lines(site):
        if '"/style.css"' not in line:
            continue
        try:
            r = json.loads(line)
            if r.get("status") in LOADED:
                seen[r["ip"]].append(datetime.fromisoformat(r["time"]).timestamp())
        except (KeyError, ValueError):
            continue
    return seen


def rendered(css: dict, ip: str, epoch: float) -> bool:
    return any(abs(c - epoch) <= VIEW_WINDOW for c in css.get(ip, ()))


def site_stats(site: str, now: datetime) -> dict:
    css = css_times(site)
    pages = defaultdict(lambda: {"views": 0, "visitors": set(), "you": 0, "bots": 0, "last": None,
                                 "referrers": Counter(), "daily": Counter()})
    last_seen = {}                                   # (ip, page) -> epoch of last counted view
    daily = Counter()
    feed_readers, feed_services = set(), {}
    week_ago = now - timedelta(days=7)
    for line in lines(site):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("method") not in ("GET", "HEAD") or r.get("status") not in LOADED:
            continue
        path, ip, agent = r.get("path", ""), r.get("ip", ""), r.get("agent", "")
        try:
            t = datetime.fromisoformat(r["time"])
        except (KeyError, ValueError):
            continue
        if path in FEEDS:
            if t >= week_ago:
                m = SUBSCRIBERS_RE.search(agent)
                if m:
                    service = agent.split("/")[0].split("(")[0].strip() or agent[:30]
                    feed_services[service] = max(feed_services.get(service, 0), int(m.group(1)))
                elif not own(ip) and agent and not re.search(r"blackbox|curl|wget|python", agent, re.I):
                    feed_readers.add((ip, agent))
            continue
        if not path.endswith("/index.html") or not str(r.get("ctype", "")).startswith("text/html"):
            continue
        page = path[: -len("index.html")]
        if page.startswith(("/tags/", "/404")):
            continue
        p = pages[page]
        if own(ip):
            p["you"] += 1
            continue
        epoch = t.timestamp()
        if not agent or BOT_RE.search(agent) or not rendered(css, ip, epoch):
            p["bots"] += 1
            continue
        if epoch - last_seen.get((ip, page), -1e12) < VIEW_WINDOW:
            continue
        last_seen[(ip, page)] = epoch
        p["views"] += 1
        p["visitors"].add(ip)
        p["last"] = r["time"]
        day = t.astimezone(timezone.utc).date().isoformat()
        p["daily"][day] += 1
        daily[day] += 1
        ref = urlsplit(r.get("referer", "")).hostname or ""
        if ref and ref.removeprefix("www.") != site:
            p["referrers"][ref.removeprefix("www.")] += 1
    start = (now - timedelta(days=DAYS - 1)).date()
    days = [(start + timedelta(days=i)).isoformat() for i in range(DAYS)]
    out_pages = []
    for page, p in pages.items():
        if not (WWW / site / page.lstrip("/") / "index.html").is_file():
            continue                                  # a removed or mistyped page
        out_pages.append({
            "path": page, "title": title_of(site, page) if page != "/" else "Home page",
            "views": p["views"], "visitors": len(p["visitors"]), "you": p["you"], "bots": p["bots"],
            "last": p["last"], "referrers": p["referrers"].most_common(5),
            "daily": [p["daily"].get(d, 0) for d in days[-30:]],
        })
    out_pages.sort(key=lambda x: -x["views"])
    return {
        "pages": out_pages,
        "days": days, "daily": [daily.get(d, 0) for d in days],
        "feed_readers": len(feed_readers) + sum(feed_services.values()),
        "feed_services": sorted(feed_services.items(), key=lambda kv: -kv[1]),
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    data = {"generated": now.isoformat(timespec="seconds"),
            "sites": {s: site_stats(s, now) for s in SITES}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=OUT.parent, prefix=".stats-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
