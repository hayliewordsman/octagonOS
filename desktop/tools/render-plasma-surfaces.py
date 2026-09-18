#!/usr/bin/env python3
"""
Draw the FacetUI Plasma surfaces over a wallpaper, for looking at.

    desktop/tools/render-plasma-surfaces.py --out desktop/docs/preview/plasma.png

The surfaces are composited by KSvg -- Plasma's own SVG engine, the same one
the desktop uses -- from the theme in desktop/plasma/FacetUI. Only the
wallpaper is drawn here, and only because a glass surface over a flat colour
proves nothing: without detail behind it, a translucent panel and an opaque one
look identical.

So this is not a screenshot of a desktop, and the panel is not doing anything a
compositor would do behind it. What it does show honestly is the theme's own
contribution: how translucent each surface is, and where the hairline falls.

Requires NumPy, Pillow, and the probe from desktop/tools/plasma-probe.
"""

import argparse
import math
import os
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "shared"))
from facetui.palette import ACCENT_A, ACCENT_B  # noqa: E402

W, H = 1180, 540


def wallpaper():
    """Something with structure, so translucency is visible at all."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    u, v = xs / W, ys / H
    base = np.stack([0.07 + 0.15 * v, 0.09 + 0.10 * v,
                     0.20 + 0.20 * (1 - v)], -1)
    for cx, cy, r, tint, amp in [
        (0.20, 0.28, 0.26, ACCENT_A, 0.70),
        (0.76, 0.32, 0.30, ACCENT_B, 0.58),
        (0.50, 0.80, 0.34, ACCENT_A * 0.6 + ACCENT_B * 0.4, 0.44),
    ]:
        d = np.exp(-(((u - cx) ** 2 + ((v - cy) * H / W) ** 2) / (r * r)) * 3.0)
        base += d[..., None] * np.asarray(tint, np.float32) * amp
    # Hard diagonal banding: the detail most likely to reveal a surface that is
    # less translucent than it claims.
    band = (np.sin((u * 20 + v * 12) * math.pi) * 0.5 + 0.5) ** 6
    base += band[..., None] * 0.13
    return Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8))


def font(size, bold=True):
    p = f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf"
    return ImageFont.truetype(p, size) if os.path.exists(p) else ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser(description="Render the FacetUI Plasma surfaces.")
    ap.add_argument("--out", default="desktop/docs/preview/plasma.png")
    ap.add_argument("--probe", default=None,
                    help="path to the built plasma-probe")
    ap.add_argument("--theme", default=str(ROOT / "desktop" / "plasma" / "FacetUI"))
    args = ap.parse_args()

    probe = args.probe
    if probe is None:
        found = list(pathlib.Path("/tmp").glob("facetui-plasma-build/**/plasma-probe"))
        if not found:
            print("[!!] no plasma-probe found. Build it first:")
            print("     desktop/tools/run-plasma-theme.sh")
            return 2
        probe = str(found[0])

    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        # The theme has to be somewhere KSvg looks, under its own name.
        dest = work / "share" / "plasma" / "desktoptheme"
        dest.mkdir(parents=True)
        subprocess.run(["cp", "-r", args.theme, str(dest / "FacetUI")], check=True)

        wall = work / "wall.png"
        wallpaper().save(wall)

        out_png = work / "composed.png"
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = str(work / "share")
        env["HOME"] = str(work)
        # KSvg caches by theme NAME, so a stale cache would serve pixmaps from
        # a different build of this same theme.
        env["XDG_CACHE_HOME"] = str(work / "cache")
        r = subprocess.run([probe, "--compose", "FacetUI", str(wall),
                            str(out_png)], capture_output=True, text=True,
                           env=env)
        if r.returncode != 0:
            print(r.stdout.strip() or r.stderr.strip())
            return 1

        img = Image.open(out_png).convert("RGB")

    cap = 56
    sheet = Image.new("RGB", (W, H + cap), (9, 11, 16))
    sheet.paste(img, (0, 0))
    d = ImageDraw.Draw(sheet)
    d.text((18, H + 14), "FacetUI on Plasma", font=font(17),
           fill=(238, 243, 252))
    d.text((18, H + 36),
           "surfaces composited by KSvg from desktop/plasma/FacetUI; only the "
           "wallpaper is drawn here",
           font=font(13, False), fill=(135, 152, 180))

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"[*] wrote {out} ({sheet.size[0]}x{sheet.size[1]})")
    print("    The surfaces are the theme's. The wallpaper is a stand-in, and")
    print("    nothing here is blurred -- that is KWin's job, not the theme's.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
