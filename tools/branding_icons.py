#!/usr/bin/env python3
"""Writes oganesson's branding into resources/ from the Og glyph, tools/og.svg.

The glyph is element 118's outer electron shell, one flat shape on a 512 grid
(tennessine's tools/app_icon.py --og draws it). The colour icons put it in white
on an orange rounded square; the mono and white ones are the glyph alone.

The file names match Helium's resources/, so oganesson.py can lay them over
Helium's and reuse its resource lists. Run it in a container, then commit the output:

    podman run --rm -v "$PWD:/w:Z" -w /w docker.io/library/debian:stable-slim sh -c \\
        'apt-get update -qq && apt-get install -y -qq --no-install-recommends \\
         python3 librsvg2-bin fonts-noto-extra >/dev/null && python3 tools/branding_icons.py'
"""

import re
import subprocess
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
RESOURCES = TOOLS.parent / 'resources'
OUT = RESOURCES / 'branding'
GLYPH = re.search(r' d="([^"]+)"', (TOOLS / 'og.svg').read_text())[1]
PLATE = '#C2410C'
RADIUS = 112  # the plate's corners, on the glyph's 512 grid


def mark(glyph_colour, plate=True):
    """The mark on a 512 grid, as SVG elements."""
    body = f'<path fill="{glyph_colour}" d="{GLYPH}"/>'
    if plate:
        body = f'<rect width="512" height="512" rx="{RADIUS}" fill="{PLATE}"/>' + body
    return body


def svg(width, height, body, view=None):
    view = view or f'0 0 {width} {height}'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="{view}">{body}</svg>\n')


def render(text, out):
    subprocess.run(['rsvg-convert', '-o', str(out)], input=text.encode(), check=True)


def wordmark(text_colour, glyph_colour, plate):
    """Mark plus "oganesson", 280x64 like Helium's product_logo_200.png."""
    return svg(280, 64,
               f'<svg x="0" y="4" width="56" height="56" viewBox="0 0 512 512">'
               f'{mark(glyph_colour, plate)}</svg>'
               f'<text x="66" y="45" fill="{text_colour}" font-family="Noto Sans" '
               f'font-weight="600" font-size="40">oganesson</text>')


def vector_icon(colour):
    """The mark as a Chromium .icon on a 256 canvas. Its paths fill even-odd by default,
    which draws the glyph as the SVG does: its outlines don't overlap."""
    lines = ['CANVAS_DIMENSIONS, 256,']
    if colour:
        argb = ', '.join('0x' + PLATE[i:i + 2] for i in (1, 3, 5))
        lines += ['NEW_PATH,', f'PATH_COLOR_ARGB, 0xFF, {argb},',
                  f'ROUND_RECT, 0, 0, 256, 256, {RADIUS // 2},',
                  'NEW_PATH,', 'PATH_COLOR_ARGB, 0xFF, 0xFF, 0xFF, 0xFF,']
    else:
        lines += ['NEW_PATH,']
    commands = {'M': 'MOVE_TO', 'L': 'LINE_TO', 'C': 'CUBIC_TO'}
    for op, args in re.findall(r'([MLCZ])([^MLCZ]*)', GLYPH):
        if op == 'Z':
            lines.append('CLOSE,')
            continue
        numbers = [float(n) / 2 for n in re.findall(r'-?[\d.]+', args)]
        lines.append(commands[op] + ', ' + ', '.join(f'{n:g}' for n in numbers) + ',')
    return '\n'.join(lines) + '\n'


def main():
    render(svg(1024, 1024, mark('#FFF'), '0 0 512 512'), OUT / 'app_icon/raw.png')
    render(svg(22, 22, mark('#000', plate=False), '0 0 512 512'), OUT / 'product_logo_22_mono.png')
    for suffix, text, glyph, plate in (('', '#202124', '#FFF', True), ('_white', '#FFF', '#FFF', False)):
        logo = wordmark(text, glyph, plate)
        render(logo, OUT / f'product_logo{suffix}_200.png')
        render(logo.replace('width="280" height="64"', 'width="140" height="32"', 1),
               OUT / f'product_logo{suffix}.png')
    for size in (16, 32):  # The new tab page's favicon; the others aren't Helium's logo.
        render(svg(size, size, mark('#3C4043', plate=False), '0 0 512 512'),
               RESOURCES / f'favicons/favicon_ntp_{size}.png')
    (OUT / 'product_logo.icon').write_text(vector_icon(colour=False))
    (OUT / 'product_logo_color.icon').write_text(vector_icon(colour=True))
    (OUT / 'product_logo.svg').write_text(svg(256, 256, mark('#FFF'), '0 0 512 512'))


if __name__ == '__main__':
    main()
