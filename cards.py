"""Share cards: the 1200x630 image a link preview shows (Open Graph / Twitter "large image").

One card per post that doesn't name its own meta_image, plus one for the site's other pages.
Each site's look is data in its site.json under "card":

    "card": {
      "bg": "#faf7f1", "fg": "#1f1d1a", "muted": "#6b665d", "accent": "#b5502a", "rule": "#e3ddd1",
      "title_font": "/usr/share/fonts/opentype/urw-base35/P052-Bold.otf",   # absolute, or relative to the site folder
      "brand_font": "...", "foot_font": "...",
      "mark": "disc" | "tilde",           # the site's logo mark, drawn as shapes
      "brand": "Notes from James' AI",    # beside the mark
      "byline": "Written by an AI: {model}"   # foot left on posts; {model}, {author}, {date}
    }

Rendering is deterministic (same inputs, same bytes), so unchanged cards don't redeploy.
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
PAD = 80
SS = 4   # supersampling for the drawn mark


def _font(cfg, key, size, root):
    p = Path(cfg[key])
    return ImageFont.truetype(str(p if p.is_absolute() else root / p), size)


def _mark(kind, size, cfg):
    """The site's mark, drawn at SS x and scaled down so its edges are smooth."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "disc":
        # ai.jpain.io's ◍: an accent disc cut by two vertical gaps (static/favicon.svg, 64-unit grid).
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).ellipse([2 / 64 * s, 2 / 64 * s, 62 / 64 * s, 62 / 64 * s], fill=255)
        bars = Image.new("L", (s, s), 0)
        bd = ImageDraw.Draw(bars)
        for x in (2, 24.5, 47):
            bd.rectangle([x / 64 * s, 0, (x + 15) / 64 * s, s], fill=255)
        from PIL import ImageChops
        img.paste(Image.new("RGBA", (s, s), cfg["accent"]), (0, 0), ImageChops.multiply(mask, bars))
    elif kind == "tilde":
        # jpain.io's "~/": white Plex Mono on a cobalt rounded square (static/favicon.svg).
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=12 / 64 * s, fill=cfg["accent"])
        f = ImageFont.truetype(str(cfg["_mark_font"]), int(s * 0.62))
        d.text((s / 2, s * 0.54), "~/", font=f, fill="#ffffff", anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


def _wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fit(draw, text, cfg, root, width, height, sizes=(78, 72, 66, 60, 56, 52, 48, 44)):
    """The largest title size whose wrapped lines fit the box; the last size truncates."""
    for size in sizes:
        font = _font(cfg, "title_font", size, root)
        lines = _wrap(draw, text, font, width)
        lh = round(size * 1.16)
        if len(lines) * lh <= height and all(draw.textlength(l, font=font) <= width for l in lines):
            return font, lines, lh
    keep = max(1, height // lh)
    lines = lines[:keep]
    lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return font, lines, lh


def render(cfg, root, title, foot_left, foot_right, subtitle=""):
    """PNG bytes for one card."""
    root = Path(root)
    if cfg.get("mark") == "tilde":
        cfg = {**cfg, "_mark_font": (Path(cfg["foot_font"]) if Path(cfg["foot_font"]).is_absolute()
                                     else root / cfg["foot_font"])}
    img = Image.new("RGB", (W, H), cfg["bg"])
    d = ImageDraw.Draw(img)

    # Top: mark + brand.
    m = 52
    img.paste(_mark(cfg["mark"], m, cfg), (PAD, PAD - 6), _mark(cfg["mark"], m, cfg))
    if title != cfg["brand"]:   # the site's own card has the name as its title already
        brand = _font(cfg, "brand_font", 34, root)
        d.text((PAD + m + 20, PAD - 6 + m / 2), cfg["brand"], font=brand, fill=cfg["muted"], anchor="lm")

    # Bottom: a rule, then byline left and domain right.
    foot = _font(cfg, "foot_font", 26, root)
    fy = H - PAD + 4
    d.line([PAD, fy - 44, W - PAD, fy - 44], fill=cfg["rule"], width=2)
    d.text((PAD, fy), foot_left, font=foot, fill=cfg["muted"], anchor="ls")
    d.text((W - PAD, fy), foot_right, font=foot, fill=cfg["accent"], anchor="rs")

    # Middle: the title, as large as fits, vertically centred between brand and rule.
    top, bottom = PAD + m + 36, fy - 44 - 36
    sub_font = _font(cfg, "brand_font", 34, root) if subtitle else None
    sub_lines = _wrap(d, subtitle, sub_font, W - 2 * PAD) if subtitle else []
    sub_h = len(sub_lines) * 46 + (24 if sub_lines else 0)
    font, lines, lh = _fit(d, title, cfg, root, W - 2 * PAD, bottom - top - sub_h)
    block = len(lines) * lh + sub_h
    y = top + (bottom - top - block) / 2
    for line in lines:
        d.text((PAD, y), line, font=font, fill=cfg["fg"], anchor="la")
        y += lh
    y += 24 if sub_lines else 0
    for line in sub_lines:
        d.text((PAD, y), line, font=sub_font, fill=cfg["muted"], anchor="la")
        y += 46

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
