#!/usr/bin/env python3
"""Prepare an image for a post: crop, scale, strip all metadata, compress.

  python3 tools/img.py SRC OUT [--crop X,Y,W,H] [--width 1600] [--pixel] [--quality 80]

OUT's extension picks the format: .webp for photos and screenshots (default choice),
.png for masks, diagrams and anything with hard edges. --pixel scales with nearest
neighbour so small masks stay crisp. Prints the result size; build.py --check allows
300 KB per image and 1500 KB per post.
"""
import argparse
from pathlib import Path

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--crop", help="X,Y,W,H in source pixels")
    ap.add_argument("--width", type=int, default=1600, help="max output width (never upscales unless --pixel)")
    ap.add_argument("--pixel", action="store_true", help="nearest-neighbour scaling, allows upscaling to --width")
    ap.add_argument("--quality", type=int, default=80)
    a = ap.parse_args()

    with Image.open(a.src) as im:
        im.load()
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") and "transparency" in im.info or im.mode == "RGBA" else "RGB")
    if a.crop:
        x, y, w, h = (int(v) for v in a.crop.split(","))
        im = im.crop((x, y, x + w, y + h))
    if im.width > a.width or (a.pixel and im.width < a.width):
        h = round(im.height * a.width / im.width)
        im = im.resize((a.width, h), Image.NEAREST if a.pixel else Image.LANCZOS)

    # A fresh image carries no EXIF, XMP, ICC profile, text chunks or GPS.
    clean = Image.new(im.mode, im.size)
    clean.putdata(list(im.getdata()))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ext = out.suffix.lower()
    if ext == ".webp":
        clean.save(out, "WEBP", quality=a.quality, method=6)
    elif ext == ".png":
        clean.save(out, "PNG", optimize=True)
    elif ext in (".jpg", ".jpeg"):
        clean.convert("RGB").save(out, "JPEG", quality=a.quality, optimize=True, progressive=True)
    else:
        raise SystemExit(f"unsupported output type {ext}")
    print(f"{out}: {clean.width}x{clean.height}, {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
