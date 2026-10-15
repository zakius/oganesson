#!/usr/bin/env python3
"""Writes the placeholder "Og" branding into resources/.

The file names match Helium's resources/, so oganesson.py can lay them
over Helium's and reuse its resource lists. Run on a host with
Pillow and Noto Sans, then commit the output.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

RESOURCES = Path(__file__).resolve().parent.parent / 'resources'
OUT = RESOURCES / 'branding'
FONT = '/usr/share/fonts/truetype/noto/NotoSans-SemiBold.ttf'
BG, FG = (0xE8, 0x59, 0x0C), (0xFF, 0xFF, 0xFF)
# On a 256 canvas: rings are (cx, cy, outer r, inner r), bars (x, y, w, h).
RINGS = [(86, 113, 50, 28), (178, 125, 36, 18)]
BARS = [(196, 89, 18, 94), (146, 165, 68, 18)]
RADIUS = 56


def draw_mark(size, glyph, background=None):
    """The mark at size x size, drawn 4x and scaled down for antialiasing."""
    s = 4 * size / 256
    img = Image.new('RGBA', (4 * size, 4 * size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if background:
        draw.rounded_rectangle((0, 0, 4 * size - 1, 4 * size - 1), RADIUS * s, fill=background)
    for cx, cy, outer, inner in RINGS:
        draw.ellipse(((cx - outer) * s, (cy - outer) * s, (cx + outer) * s, (cy + outer) * s), fill=glyph)
        draw.ellipse(((cx - inner) * s, (cy - inner) * s, (cx + inner) * s, (cy + inner) * s),
                     fill=background or (0, 0, 0, 0))
    for x, y, w, h in BARS:
        draw.rectangle((x * s, y * s, (x + w) * s, (y + h) * s), fill=glyph)
    return img.resize((size, size), Image.LANCZOS)


def wordmark(text_color):
    """Mark plus "oganesson", 280x64 like Helium's product_logo_200.png."""
    img = Image.new('RGBA', (280, 64), (0, 0, 0, 0))
    img.alpha_composite(draw_mark(56, FG, BG), (0, 4))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 40)
    draw.text((66, 30), 'oganesson', font=font, fill=text_color, anchor='lm')
    return img


def vector_icon(color):
    lines = ['CANVAS_DIMENSIONS, 256,']
    if color:
        lines += ['NEW_PATH,', 'PATH_COLOR_ARGB, 0xFF, %s,' % ', '.join(f'0x{c:02X}' for c in BG),
                  f'ROUND_RECT, 0, 0, 256, 256, {RADIUS},']
    fill = ['PATH_COLOR_ARGB, 0xFF, 0xFF, 0xFF, 0xFF,'] if color else []
    for cx, cy, outer, inner in RINGS:  # Even-odd fill (the default) makes a ring.
        lines += ['NEW_PATH,', *fill, f'CIRCLE, {cx}, {cy}, {outer},', f'CIRCLE, {cx}, {cy}, {inner},']
    for x, y, w, h in BARS:
        lines += ['NEW_PATH,', *fill, f'ROUND_RECT, {x}, {y}, {w}, {h}, 0,']
    return '\n'.join(lines) + '\n'


def svg():
    hex_bg = '#%02X%02X%02X' % BG
    rings = ''.join(f'M{cx - o} {cy}a{o} {o} 0 1 0 {2 * o} 0a{o} {o} 0 1 0 {-2 * o} 0z'
                    f'M{cx - i} {cy}a{i} {i} 0 1 0 {2 * i} 0a{i} {i} 0 1 0 {-2 * i} 0z'
                    for cx, cy, o, i in RINGS)
    bars = ''.join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFF"/>' for x, y, w, h in BARS)
    return (f'<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="256" height="256" rx="{RADIUS}" fill="{hex_bg}"/>'
            f'<path fill-rule="evenodd" fill="#FFF" d="{rings}"/>{bars}</svg>\n')


def main():
    (OUT / 'app_icon').mkdir(parents=True, exist_ok=True)
    (RESOURCES / 'favicons').mkdir(exist_ok=True)
    draw_mark(1024, FG, BG).save(OUT / 'app_icon/raw.png')
    draw_mark(22, (0, 0, 0)).save(OUT / 'product_logo_22_mono.png')
    for suffix, color in (('', (0x20, 0x21, 0x24)), ('_white', FG)):
        mark = wordmark(color)
        mark.save(OUT / f'product_logo{suffix}_200.png')
        mark.resize((140, 32), Image.LANCZOS).save(OUT / f'product_logo{suffix}.png')
    for size in (16, 32):  # The new tab page's favicon; the others aren't Helium's logo.
        draw_mark(size, (0x3C, 0x40, 0x43)).save(RESOURCES / f'favicons/favicon_ntp_{size}.png')
    (OUT / 'product_logo.icon').write_text(vector_icon(color=False))
    (OUT / 'product_logo_color.icon').write_text(vector_icon(color=True))
    (OUT / 'product_logo.svg').write_text(svg())


if __name__ == '__main__':
    main()
