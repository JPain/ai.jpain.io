#!/usr/bin/env python3
"""YouTube videos in posts: fetch each video's thumbnail into the post's media folder.

  /mnt/work/venvs/blog/bin/python tools/youtube.py posts/some-post.md   # fetch any missing
  /mnt/work/venvs/blog/bin/python tools/youtube.py --info URL           # id, start, title

A post embeds a video as a link alone in its paragraph, marked {.youtube}:

  [Video title](https://youtu.be/ID "Optional caption"){.youtube}

The page shows youtube-<ID>.webp (saved here, metadata-free, 16:9) with a play button, and
loads nothing from YouTube until the reader presses play (build.py youtube_embeds). The
browser editor calls fetch() when you insert a video, so this is for posts written by hand.
"""
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
import build  # noqa: E402  (youtube_ref, media_dir, split_header)

UA = {"User-Agent": "jpain.io-editor/1 (+https://jpain.io)"}


def get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def title(vid):
    """The video's title from YouTube's oEmbed endpoint, or "" if it won't say (private, removed)."""
    try:
        q = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
        return json.loads(get(f"https://www.youtube.com/oembed?{q}")).get("title", "").strip()
    except Exception:
        return ""


def fetch(vid, folder):
    """Save youtube-<vid>.webp in folder: the largest thumbnail YouTube has, cropped to 16:9
    (the smaller ones are letterboxed 4:3), at most 1280 wide, no metadata. Returns its name."""
    im = None
    for name in ("maxresdefault", "sddefault", "hqdefault"):
        try:
            im = Image.open(io.BytesIO(get(f"https://i.ytimg.com/vi/{vid}/{name}.jpg")))
            im.load()
            break
        except Exception:
            continue
    if im is None:
        raise ValueError(f"YouTube has no thumbnail for {vid}: is the video public?")
    im = im.convert("RGB")
    h = round(im.width * 9 / 16)
    if im.height > h:
        top = (im.height - h) // 2
        im = im.crop((0, top, im.width, top + h))
    if im.width > 1280:
        im = im.resize((1280, 720), Image.LANCZOS)
    clean = Image.new("RGB", im.size)
    clean.paste(im)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"youtube-{vid}.webp"
    clean.save(out, "WEBP", quality=78, method=6)
    return out.name


def main(args):
    if args[:1] == ["--info"] and len(args) == 2:
        vid, start = build.youtube_ref(args[1])
        print(json.dumps({"id": vid, "start": start, "title": title(vid) if vid else ""}))
        return 0 if vid else 1
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    path = Path(args[0]).resolve()
    build.use_site(SITE)
    text = path.read_text()
    head, body = build.split_header(text)
    meta = dict((k.strip().lower(), v.strip()) for k, v in (l.split(":", 1) for l in head.splitlines() if ":" in l))
    folder = build.media_dir(path, meta.get("link") or meta.get("slug") or path.stem)
    found = 0
    for m in re.finditer(r"\]\(([^)\s]+)[^)]*\)\{:?\s*\.youtube\s*\}", body):
        vid, _ = build.youtube_ref(m.group(1))
        if not vid:
            continue
        found += 1
        if (folder / f"youtube-{vid}.webp").exists():
            print(f"have youtube-{vid}.webp")
        else:
            print(f"saved {fetch(vid, folder)} in {folder.relative_to(SITE)}/")
    if not found:
        print("no {.youtube} links in this post")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
