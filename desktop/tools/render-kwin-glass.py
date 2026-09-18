#!/usr/bin/env python3
"""
Draw the FacetUI desktop surfaces, using the real shader.

    desktop/tools/render-kwin-glass.py --out docs/preview/kwin-glass.png

The mobile edition has `mobile/tools/render-surfaces.py`, which evaluates the
FacetUI maths in NumPy so the numbers spread across eight overlays can be
looked at together. This is the desktop equivalent, with one difference worth
stating: IT RUNS THE ACTUAL SHADER. The panel, the dialog and the menu below
are composited by facetui-glass.frag in a real GL driver, not by a model of it.

So it is still not a screenshot -- the blur here is a Gaussian where KWin's is
its own, and the wallpaper is drawn rather than sampled from a desktop -- but
the glass itself is the shipped code.

Requires NumPy, Pillow, a C compiler and libEGL/libGLESv2.
"""

import argparse
import math
import os
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
DESKTOP = HERE.parent
ROOT = DESKTOP.parent
SHADER = DESKTOP / "kwin" / "facetui-glass" / "shaders" / "facetui-glass.frag"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "shared"))
from facetui.palette import ACCENT_A, ACCENT_B  # noqa: E402

# Imported rather than restated: the preamble and the include stand-ins have to
# be the ones the validator uses, or this renders a different shader than the
# one that was checked.
from importlib import util as _util  # noqa: E402
_spec = _util.spec_from_file_location("vks", HERE / "validate-kwin-shaders.py")
_vks = _util.module_from_spec(_spec)
_spec.loader.exec_module(_vks)

W, H = 1280, 760

#: The constants the effect ships, from facetuiglasseffect.cpp. In logical
#: pixels, which is what this render is in.
EDGE_THICKNESS = 12.0
EDGE_INTENSITY = 0.5
RIM_WIDTH = 48.0
RIM_AMOUNT = 0.35
TINT = (0.92, 0.96, 1.0)

#: The depth model, in this render's pixels.
L2, L3, L4 = 24 * 2.0, 48 * 2.0, 64 * 2.0

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size, bold=True):
    for p in FONTS if bold else reversed(FONTS):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wallpaper():
    """Something with structure, because glass over a flat colour proves nothing."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    u, v = xs / W, ys / H
    base = np.stack([0.07 + 0.16 * v, 0.09 + 0.10 * v, 0.20 + 0.22 * (1 - v)], -1)
    for cx, cy, r, tint, amp in [
        (0.22, 0.26, 0.24, ACCENT_A, 0.72), (0.74, 0.30, 0.28, ACCENT_B, 0.60),
        (0.52, 0.76, 0.32, ACCENT_A * 0.6 + ACCENT_B * 0.4, 0.46),
    ]:
        d = np.exp(-(((u - cx) ** 2 + ((v - cy) * H / W) ** 2) / (r * r)) * 3.0)
        base += d[..., None] * np.asarray(tint, np.float32) * amp
    band = (np.sin((u * 18 + v * 11) * math.pi) * 0.5 + 0.5) ** 6
    base += band[..., None] * 0.12
    return np.clip(base, 0, 1)


def blur(img, radius_px):
    """Where KWin would blur, we blur. Not the same kernel."""
    if radius_px <= 0:
        return img
    pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    return np.asarray(pil.filter(ImageFilter.GaussianBlur(radius_px / 2.5)),
                      np.float32) / 255.0


def glass(probe, scene, box, radius_px, tint, alpha, lit, workdir, tag,
          enabled=True):
    """One glass surface, composited by the real shader.

    The surface KWin would hand the effect is the blurred backdrop plus the
    window's own translucent fill; that is built here and handed to the shader
    as its texture, which then adds the rim and, on the panel, the edge.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    surface = blur(scene, radius_px)[y0:y1, x0:x1]
    surface = surface * (1.0 - alpha) + np.asarray(tint, np.float32) * alpha

    if not enabled:
        # Blur and tint, and nothing else. This is the comparison the sheet is
        # built around: it is what a translucent panel looks like without the
        # third thing FacetUI insists on.
        scene = scene.copy()
        scene[y0:y1, x0:x1] = np.clip(surface, 0, 1)
        return scene

    # The shader samples one texel per pixel, so the surface goes in as a
    # texture. glsl-probe takes a single colour, so the varying part is fed
    # through by rendering the shader once per surface with a flat texture and
    # applying its rim/edge as a transfer -- which is exact, because both
    # effects are functions of position alone.
    flat = evaluate(probe, workdir, w, h, (1.0, 1.0, 1.0, 1.0), lit, tag)
    # flat.rgb = rim(p) + edge premultiplied over white; recover the two terms.
    edge_a = flat[..., 3] - (1.0 - 0.0) * 0.0    # alpha is the edge alpha only
    # out.a = e.a + tex.a*(1-e.a), with tex.a = 1  ->  out.a = 1; use a probe
    # with a transparent texture instead to read the edge alpha directly.
    clear = evaluate(probe, workdir, w, h, (0.0, 0.0, 0.0, 0.0), lit, tag + "c")
    edge_a = clear[..., 3]
    edge_rgb = clear[..., :3]
    rim_mult = np.where(edge_a[..., None] < 0.999,
                        (flat[..., :3] - edge_rgb) / np.maximum(1.0 - edge_a[..., None], 1e-6),
                        1.0)

    out = surface * rim_mult
    out = edge_rgb + out * (1.0 - edge_a[..., None])

    scene = scene.copy()
    scene[y0:y1, x0:x1] = np.clip(out, 0, 1)
    return scene


def evaluate(probe, workdir, w, h, tex, lit, tag):
    src = _vks.preprocess(SHADER.read_text())
    path = workdir / f"r{tag}.frag"
    path.write_text(src)
    raw = workdir / f"r{tag}.raw"
    args = [str(probe), "--eval", str(path), str(w), str(h), str(raw),
            f"sampler={','.join(str(v) for v in tex)}",
            f"facet_size={w},{h}",
            f"facet_thickness={EDGE_THICKNESS}",
            f"facet_intensity={EDGE_INTENSITY if lit else 0.0}",
            f"facet_tint={','.join(str(v) for v in TINT)}",
            f"facet_rim={RIM_WIDTH}",
            f"facet_amount={RIM_AMOUNT}",
            "modulation=1,1,1,1"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"shader evaluation failed: {r.stderr or r.stdout}")
    return np.fromfile(raw, dtype=np.float32).reshape(h, w, 4)


def label(img, xy, text, size=15, fill=(238, 243, 252), bold=True):
    ImageDraw.Draw(img).text(xy, text, font=font(size, bold), fill=fill)


def main():
    ap = argparse.ArgumentParser(description="Render the FacetUI desktop surfaces.")
    ap.add_argument("--out", default="desktop/docs/preview/kwin-glass.png")
    args = ap.parse_args()

    def build(probe, workdir, enabled):
        """The same desktop, with the effect on or off."""
        tag = "on" if enabled else "off"
        s = wallpaper()
        # The panel: L4, and the only lit surface -- mirroring the Android
        # edition, where the specular edge is drawn by ScrimView and therefore
        # lands on the notification shade's scrim alone.
        s = glass(probe, s, (0, 0, W, 56), L4, ACCENT_B * 0.20 + 0.04, 0.80,
                  True, workdir, tag + "panel", enabled)
        img = Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))
        label(img, (22, 17), "octagonOS", 18)
        label(img, (W - 128, 18), "21:41", 16, (186, 206, 236))
        s = np.asarray(img, np.float32) / 255.0

        # A dialog: L2.
        s = glass(probe, s, (330, 230, 950, 520), L2, ACCENT_B * 0.15 + 0.05,
                  0.77, False, workdir, tag + "dialog", enabled)
        img = Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))
        label(img, (368, 268), "Apply these display settings?", 21)
        label(img, (368, 312), "Reverting in 15 seconds.", 16,
              (186, 206, 236), bold=False)
        label(img, (762, 470), "Revert", 16, (150, 190, 245))
        label(img, (862, 470), "Keep", 16, (150, 190, 245))
        s = np.asarray(img, np.float32) / 255.0

        # A menu: L2, the same tier as the dialog, because a user reads them as
        # the same kind of floating panel.
        s = glass(probe, s, (60, 96, 300, 330), L2, ACCENT_A * 0.13 + 0.05,
                  0.75, False, workdir, tag + "menu", enabled)
        img = Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8))
        for i, item in enumerate(["New window", "Open recent", "Preferences",
                                  "Quit"]):
            label(img, (86, 124 + i * 52), item, 16, bold=False)
        return img

    with tempfile.TemporaryDirectory() as td:
        workdir = pathlib.Path(td)
        probe = _vks.build_probe(workdir)
        off = build(probe, workdir, False)
        on = build(probe, workdir, True)

    # Side by side, because the point of FacetUI is a difference that is
    # obvious in comparison and easy to miss in isolation.
    gap, cap, pad = 20, 58, 20
    sheet = Image.new("RGB", (W * 2 + gap + pad * 2, H + cap + pad * 2),
                      (9, 11, 16))
    sheet.paste(off, (pad, pad))
    sheet.paste(on, (pad + W + gap, pad))
    y = pad + H + 16
    label(sheet, (pad, y), "Blur and tint only", 19)
    label(sheet, (pad, y + 26),
          "translucent, and flat: no boundary, no light", 15,
          (135, 152, 180), bold=False)
    label(sheet, (pad + W + gap, y), "With facetui-glass", 19)
    label(sheet, (pad + W + gap, y + 26),
          "a specular edge on the panel, a darkened rim on every surface", 15,
          (135, 152, 180), bold=False)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"[*] wrote {out} ({sheet.size[0]}x{sheet.size[1]})")
    print("    The glass is the shipped shader. The blur and the wallpaper are")
    print("    stand-ins: this renders the effect, it does not photograph KWin.")


if __name__ == "__main__":
    main()
