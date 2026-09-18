#!/usr/bin/env python3
"""
Lay the FacetUI icon theme out as a sheet, for looking at.

    desktop/tools/render-icon-sheet.py --out desktop/docs/preview/icons.png

The icons are the shipped PNGs, pasted at their own size -- nothing here
resamples or re-renders them, so what the sheet shows is what a desktop loads.

The size row matters more than the grid: an icon theme is judged at 22px in a
toolbar far more often than at 256px in a settings dialog, and glass that reads
well large can turn to mush small.

Requires Pillow.
"""

import argparse
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
THEME = HERE.parent / "icons" / "FacetUI"

#: One name per glyph, in a reading order rather than alphabetical.
GRID = [
    "utilities-terminal", "system-file-manager", "web-browser", "internet-mail",
    "preferences-system", "office-calendar", "accessories-calculator",
    "accessories-text-editor",
    "multimedia-audio-player", "multimedia-video-player",
    "multimedia-photo-viewer", "camera-photo",
    "system-search", "drive-harddisk", "system-software-install",
    "system-software-update",
    "preferences-desktop-security", "weather-clear", "clock",
    "audio-input-microphone",
    "internet-chat", "call-start", "x-office-address-book",
    "application-x-executable",
]
#: Shown at 1:1, so the strip's height is the largest of them. 128 and 256 are
#: left out deliberately: at 1:1 a 256px icon is taller than the rest of the
#: sheet and says nothing the 64 does not. The sizes here are the ones a
#: toolbar, a menu and a file manager actually ask for.
SIZE_ROW = [64, 48, 32, 24, 22, 16]
COLS = 8
BG = (18, 20, 27)


def font(px, bold=False):
    p = f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf"
    return ImageFont.truetype(p, px) if pathlib.Path(p).exists() else ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser(description="Lay out the FacetUI icon theme.")
    ap.add_argument("--out", default="desktop/docs/preview/icons.png")
    ap.add_argument("--theme", default=str(THEME))
    args = ap.parse_args()

    theme = pathlib.Path(args.theme)
    cell, pad = 96, 20
    rows = (len(GRID) + COLS - 1) // COLS
    grid_h = rows * cell + pad
    # Sized from the strip's own contents. Hardcoding it is how the first
    # version drew a 256px icon through the caption.
    strip_h = max(SIZE_ROW) + 62

    w = COLS * cell + pad * 2
    sheet = Image.new("RGB", (w, pad + grid_h + strip_h + 56), BG)
    d = ImageDraw.Draw(sheet)

    for i, name in enumerate(GRID):
        png = theme / "apps" / "64" / f"{name}.png"
        if not png.exists():
            print(f"[!] missing {png}", file=sys.stderr)
            continue
        icon = Image.open(png).convert("RGBA")
        x = pad + (i % COLS) * cell + (cell - 64) // 2
        y = pad + (i // COLS) * cell
        sheet.paste(icon, (x, y), icon)

    # The size row: every size the theme ships, at its own scale, baselined so
    # they sit on one line the way a toolbar would show them.
    y0 = pad + grid_h + 34
    d.text((pad, y0 - 28),
           f"at 1:1 -- the theme also ships "
           f"{', '.join(str(s) for s in (128, 256))}",
           font=font(14, True), fill=(200, 212, 232))
    x = pad
    base = y0 + max(SIZE_ROW)
    for size in SIZE_ROW:
        png = theme / "apps" / str(size) / "utilities-terminal.png"
        if not png.exists():
            continue
        icon = Image.open(png).convert("RGBA")
        sheet.paste(icon, (x, base - size), icon)
        d.text((x, base + 6), str(size), font=font(11), fill=(130, 146, 176))
        x += size + 18

    d.text((pad, sheet.height - 42), "FacetUI icon theme",
           font=font(17, True), fill=(238, 243, 252))
    d.text((pad, sheet.height - 20),
           "the glass comes from shared/facetui/tile.py, the same code the "
           "Android icon pack renders",
           font=font(13), fill=(135, 152, 180))

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"[*] wrote {out} ({sheet.size[0]}x{sheet.size[1]})")


if __name__ == "__main__":
    main()
