#!/usr/bin/env python3
"""
Draw the FacetUI surfaces, so they can be looked at without a device.

    tools/render-surfaces.py --out docs/preview/facetui-surfaces.png

Renders the notification shade, a dialog and a popup menu over a synthetic
wallpaper, by evaluating the same maths the shaders evaluate -- the edge
highlight and the rim darkening from `shared/facetui/facet_math.py`, at the
radii and alphas the overlays actually ship.

WHAT THIS IS, AND IS NOT

It is a way to see whether the numbers chosen across eight overlays add up to
something coherent, before committing to a build that takes hours and a device
nobody has. Blur radii, tint alphas and the hairline are spread across files
that are individually sensible and collectively unchecked; this is the first
thing that renders them together.

It is NOT a screenshot, and it is not a simulation of SystemUI. It applies a
Gaussian blur where SurfaceFlinger would apply its own, over a wallpaper that
is drawn here rather than sampled from a device. Proportions, tint and depth
ordering are meaningful. Exact pixels are not.

The same caveat titan2e-eos attaches to its shader previews applies: this
renders the maths, it does not photograph the result.

Requires Pillow and NumPy.
"""

import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from facetui.facet_math import edge_highlight, rim_darkening  # noqa: E402
from facetui.palette import ACCENT_A, ACCENT_B  # noqa: E402

#: A phone, at a size that fits three of them side by side.
W, H = 420, 900

#: The FacetUI depth model, in this render's pixels. A phone at this scale is
#: roughly 2.6 px per dp, so the tiers land near their real proportions.
PX_PER_DP = 420.0 / 160.0
L2 = 24 * PX_PER_DP
L3 = 48 * PX_PER_DP
L4 = 64 * PX_PER_DP

#: Alphas, as the overlays ship them.
DIALOG_ALPHA = 0xC4 / 255.0        # background_floating_device_default_dark
POPUP_ALPHA = 0xC2 / 255.0         # popup_background_material, night
SHADE_ALPHA = 0.78                 # the scrim, once notification_scrim_transparent is on
DIALOG_DIM = 0.32                  # backgroundDimAmount, from the overlay

HAIRLINE = 0.18                    # #2EFFFFFF, near enough
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def font(size):
    for p in FONTS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wallpaper():
    """Something with structure, because glass over a flat colour proves nothing.

    A blur only reads as glass if there is detail behind it to diffuse. A
    render over a plain gradient would look convincing and tell you nothing
    about whether these alphas work on a real homescreen.
    """
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    u, v = xs / W, ys / H

    base = (np.stack([0.10 + 0.30 * v, 0.13 + 0.16 * v, 0.28 + 0.34 * (1 - v)], -1))
    # A few bright forms, so the blur has edges to smear and the tint has
    # something to sit against.
    for cx, cy, r, tint, amp in [
        (0.24, 0.20, 0.20, ACCENT_A, 0.75), (0.78, 0.34, 0.26, ACCENT_B, 0.62),
        (0.48, 0.70, 0.30, ACCENT_A * 0.6 + ACCENT_B * 0.4, 0.50),
        (0.12, 0.86, 0.18, ACCENT_B, 0.45),
    ]:
        d = np.exp(-(((u - cx) ** 2 + ((v - cy) * H / W) ** 2) / (r * r)) * 3.0)
        base += d[..., None] * np.asarray(tint, np.float32) * amp
    # Hard diagonal banding: the detail most likely to reveal a blur that is
    # too weak to be doing anything.
    band = (np.sin((u * 14 + v * 9) * math.pi) * 0.5 + 0.5) ** 6
    base += band[..., None] * 0.14
    return np.clip(base, 0, 1)


def blur(img, radius_px):
    """Where SurfaceFlinger would blur, we blur. Not the same kernel."""
    if radius_px <= 0:
        return img
    pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    pil = pil.filter(ImageFilter.GaussianBlur(radius_px / 2.5))
    return np.asarray(pil, np.float32) / 255.0


def glass_panel(scene, box, radius_px, tint, alpha, lit_top=False, rim=True):
    """One glass surface: blur behind it, tint it, darken its rim, hairline it.

    The stack the overlays and shaders produce together, in that order --
    blurred first, then tinted, then the rim absorbs.

    `lit_top` defaults to FALSE, which is a correction. The first version of
    this render lit every panel, and the result was a white bar across the top
    of every notification. That is not what the device does: the specular edge
    is hooked into ScrimView.onDraw, so it is drawn on the shade SCRIM and
    nothing else. Notifications, dialogs and menus get blur, tint, rim and a
    hairline -- no specular.

    Worth stating plainly because the wrong version looked plausible. A render
    that overstates an effect is worse than no render, since it invites tuning
    a number that was never the problem.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    panel = blur(scene, radius_px)[y0:y1, x0:x1].copy()
    panel = panel * (1.0 - alpha) + np.asarray(tint, np.float32) * alpha

    # FacetRimShader, across the panel's width.
    lateral = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    panel *= rim_darkening(lateral, 0.42, 0.35 if rim else 0.0)[..., None]

    # FacetEdgeShader, down from the top edge -- scrim only.
    if lit_top:
        thickness = 12 * PX_PER_DP
        # ScrimView bounds the draw to 3x thickness: the falloff is already
        # transparent past that, and drawing the full height would cost fill
        # rate for nothing. Bounding it here too is what keeps the highlight a
        # band rather than a wash.
        band = min(int(thickness * 3), h)
        dist = np.arange(band, dtype=np.float32)[:, None]
        lat = np.broadcast_to(lateral, (band, w))
        panel[:band] += edge_highlight(
            np.broadcast_to(dist, (band, w)), thickness, lat, 0.5)[..., None]

    # The hairline. Without it this is translucent grey, not glass.
    panel[0, :] += HAIRLINE
    panel[-1, :] += HAIRLINE * 0.5
    panel[:, 0] += HAIRLINE * 0.7
    panel[:, -1] += HAIRLINE * 0.7

    scene[y0:y1, x0:x1] = np.clip(panel, 0, 1)
    return scene


def label(img, xy, text, size=15, fill=(238, 243, 252)):
    ImageDraw.Draw(img).text(xy, text, font=font(size), fill=fill)


def shade():
    """The notification shade: L4 window, L3 content, notifications on top."""
    s = wallpaper()
    # L4, the deepest layer, behind everything.
    # The only surface in the system that gets the specular edge: it is hooked
    # into ScrimView, which is the shade scrim.
    s = glass_panel(s, (0, 0, W, int(H * 0.62)), L4,
                    ACCENT_B * 0.22 + 0.04, SHADE_ALPHA, lit_top=True)
    img = Image.fromarray((s * 255).astype(np.uint8))
    label(img, (22, 26), "9:41", 20)
    label(img, (W - 92, 26), "FacetUI", 15, (150, 190, 245))

    # Notifications: L3, the same tier as the shade content they sit in.
    s = np.asarray(img, np.float32) / 255.0
    for i, (title, body) in enumerate([
            ("Messages", "3 new"), ("Calendar", "Stand-up in 10 min"),
            ("Updater", "octagonOS 1.0-beta")]):
        top = 86 + i * 104
        s = glass_panel(s, (18, top, W - 18, top + 88), L3,
                        ACCENT_A * 0.20 + 0.05, 0.62)   # no specular
        img = Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))
        label(img, (36, top + 18), title, 16)
        label(img, (36, top + 44), body, 14, (186, 206, 236))
        s = np.asarray(img, np.float32) / 255.0
    return Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))


def dialog():
    """A dialog: L4 behind the whole screen, L2 for the panel, dim at 0.32."""
    s = wallpaper()
    # windowBlurBehindEnabled: the entire screen behind goes to the deepest tier.
    s = blur(s, L4)
    s = s * (1.0 - DIALOG_DIM)      # backgroundDimAmount, lowered from stock 0.6

    x0, x1 = 34, W - 34
    y0, y1 = int(H * 0.34), int(H * 0.34) + 250
    s = glass_panel(s, (x0, y0, x1, y1), L2, ACCENT_B * 0.16 + 0.05, DIALOG_ALPHA)
    img = Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))
    label(img, (x0 + 26, y0 + 30), "Erase all data?", 19)
    label(img, (x0 + 26, y0 + 72), "This cannot be undone.", 15, (186, 206, 236))
    label(img, (x1 - 158, y1 - 46), "Cancel", 15, (150, 190, 245))
    label(img, (x1 - 70, y1 - 46), "Erase", 15, (150, 190, 245))
    return img


def menu():
    """A popup menu: L2, and only glass at all because of a patch."""
    s = wallpaper()
    x0, x1 = W - 232, W - 22
    y0, y1 = 70, 70 + 214
    s = glass_panel(s, (x0, y0, x1, y1), L2, ACCENT_A * 0.14 + 0.05, POPUP_ALPHA)
    img = Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))
    label(img, (22, 26), "Files", 20)
    for i, item in enumerate(["New folder", "Sort by", "Select all", "Settings"]):
        label(img, (x0 + 22, y0 + 20 + i * 46), item, 15)
    return img


PANELS = [
    ("Notification shade", "L4 window, L3 content", shade),
    ("Dialog", "L2 panel, L4 behind, dim 0.32", dialog),
    ("Popup menu", "L2, needs patches/framework/0001", menu),
]


def main():
    ap = argparse.ArgumentParser(description="Render the FacetUI surfaces.")
    ap.add_argument("--out", default="docs/preview/facetui-surfaces.png")
    args = ap.parse_args()

    pad, cap = 24, 58
    sheet = Image.new("RGB", (len(PANELS) * (W + pad) + pad, H + pad + cap),
                      (9, 11, 16))
    for i, (title, sub, fn) in enumerate(PANELS):
        x = pad + i * (W + pad)
        sheet.paste(fn(), (x, pad))
        label(sheet, (x, H + pad + 12), title, 17)
        label(sheet, (x, H + pad + 34), sub, 13, (135, 152, 180))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sheet.save(args.out)
    print(f"[*] wrote {args.out} ({sheet.size[0]}x{sheet.size[1]})")
    print("    Renders the maths, not a device. Proportions, tint and depth")
    print("    order are meaningful; exact pixels are not.")


if __name__ == "__main__":
    main()
