"""Thumbnail for the Vedantic Psychology autopilot — Pillow only.

BookPeak style, 1280x720: the book visual on the left, a big bold Hindi
headline (yellow first line, white rest) on a dark background on the
right, and a small "ऑडियोबुक" ribbon at the bottom.
Font: Noto Sans Devanagari Bold (Devanagari glyphs; DejaVu Sans has
none). Falls back to DejaVuSans-Bold if the Noto font is missing.
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

W, H = 1280, 720
DEVA_BOLD = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
DEJA_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LEFT_W = 500  # book visual panel width


def _font(size):
    for path in (DEVA_BOLD, DEJA_BOLD):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(text, font, draw, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(bg_image, text, out_path):
    """bg_image: the thumbnail visual (AI image). text: short Hindi
    headline from the script (thumbnail_text)."""
    img = Image.new("RGB", (W, H), (10, 10, 16))
    # Left panel: book visual, cropped to fill LEFT_W x H.
    panel = Image.open(bg_image).convert("RGB")
    pw, ph = panel.size
    target_ratio = LEFT_W / H
    if pw / ph > target_ratio:
        new_w = int(ph * target_ratio)
        x0 = (pw - new_w) // 2
        panel = panel.crop((x0, 0, x0 + new_w, ph))
    else:
        new_h = int(pw / target_ratio)
        y0 = (ph - new_h) // 2
        panel = panel.crop((0, y0, pw, y0 + new_h))
    panel = panel.resize((LEFT_W, H))
    panel = ImageEnhance.Brightness(panel).enhance(0.95)
    img.paste(panel, (0, 0))
    # Thin gold divider between panel and text area.
    draw = ImageDraw.Draw(img)
    draw.rectangle([LEFT_W, 0, LEFT_W + 6, H], fill=(255, 210, 0))
    # Right side: big Hindi headline, up to 3 lines.
    font = _font(110)
    max_w = W - LEFT_W - 90
    lines = _wrap(text, font, draw, max_w)
    while len(lines) > 3 and font.size > 60:
        font = _font(font.size - 10)
        lines = _wrap(text, font, draw, max_w)
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) \
        + 24 * (len(lines) - 1)
    y = (H - total_h) // 2 - 20
    for li, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        x = LEFT_W + 6 + (W - LEFT_W - 6 - w) // 2
        fill = (255, 210, 0) if li == 0 else (255, 255, 255)
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=5, stroke_fill=(0, 0, 0))
        y += draw.textbbox((0, 0), line, font=font)[3] + 24
    # "ऑडियोबुक" ribbon, bottom-right.
    ribbon_font = _font(44)
    ribbon = "ऑडियोबुक"
    rw = draw.textlength(ribbon, font=ribbon_font)
    rx0, ry0 = W - int(rw) - 70, H - 92
    draw.rounded_rectangle([rx0, ry0, W - 30, H - 34], radius=12,
                           fill=(255, 210, 0))
    draw.text((rx0 + 20, ry0 + 4), ribbon, font=ribbon_font,
              fill=(0, 0, 0))
    img.save(out_path, "JPEG", quality=90)
    print("Wrote thumbnail %s" % out_path)
    return out_path


if __name__ == "__main__":
    import sys
    make_thumbnail(sys.argv[1], sys.argv[2], sys.argv[3])
