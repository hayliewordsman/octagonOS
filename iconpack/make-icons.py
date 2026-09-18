#!/usr/bin/env python3
"""
Build the FacetUIIcons adaptive icon pack.

    ./make-icons.py

Produces, under FacetUIIcons/res/:

    mipmap-anydpi-v26/facetui_<glyph>.xml   adaptive icon: background,
                                            foreground, monochrome
    drawable/facetui_glyph_<glyph>.xml      the glyph, as a vector
    drawable-<dpi>/facetui_tile.png         the glass octagon, rendered from
                                            FacetUI's own shader maths
    xml/appfilter.xml                       component -> icon mapping

The glass tile is a raster because it is glass: the edge highlight and the rim
darkening are exponential falloffs, and a vector drawable has no way to express
them. The glyphs stay vectors, because a glyph is flat and should be crisp at
any size. That split is the whole design -- one shared, generated surface, with
per-app line art on top of it.

Requires Pillow and NumPy. No Android SDK.
"""

import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "bootanimation"))

from facet_math import edge_highlight, rim_darkening  # noqa: E402
from glyphs import APPS, GLYPHS, FALLBACK_GLYPH  # noqa: E402

# --- brand ------------------------------------------------------------------
# Identical to bootanimation/make-bootanimation.py. If these drift, the boot
# screen and the app drawer stop being the same material.
ACCENT_A = np.array([0.36, 0.72, 1.00])   # cool cyan-blue
ACCENT_B = np.array([0.62, 0.50, 1.00])   # violet

FACETS = 8
FACET_HALF_ANGLE = math.pi / FACETS
FACET_TILT = math.radians(52.0)
LIGHT_ELEVATION = math.radians(58.0)

#: Where the light sits on an icon. Fixed, not animated: every icon on the
#: screen is lit from the same direction, which is what makes a grid of them
#: read as one surface rather than as a scatter of unrelated buttons.
ICON_LIGHT_ANGLE = math.radians(-118.0)

AMBIENT = 0.30
SPECULAR_POWER = 36.0
SPECULAR_STRENGTH = 0.85

RIM_WIDTH = 0.42
RIM_AMOUNT = 0.35
EDGE_INTENSITY = 0.50

#: The flat table is much larger here than on the boot animation's mark (0.46).
#: There the facets are the subject; here they are a bezel, and the subject is
#: the glyph sitting on top. Eight facets' worth of value variation running
#: under a thin glyph at 48dp makes the glyph unreadable, so the crown is
#: pushed out to a ring and the middle left calm.
#:
#: 0.84, not the 0.70 this started at. At 0.70 the table's edge sat at 25.2 and
#: fifteen of the twenty-five glyphs ran straight over it onto the facets --
#: the calm centre existed but most glyphs were not inside it. The table and
#: GLYPH_SCALE below are a pair: they are what decides whether a glyph sits on
#: calm glass or across a girdle hairline, and neither can be changed alone.
TABLE_FRAC = 0.84

#: Android's adaptive icon geometry. The drawable is 108 units square, the mask
#: covers the middle 72, and the outer 18 on each side is parallax bleed that
#: is never all visible at once.
ADAPTIVE_SIZE = 108
MASK_SIZE = 72

#: How the 100-unit glyph artwork is fitted into the 108-unit viewport.
#:
#: Not 108/100, and not the mask width either. The glyphs must clear the
#: OCTAGON, which cuts the mask's corners, and the safe zone Android documents
#: is a circle of diameter 66 in the 108 viewport -- smaller than the mask
#: square in every direction that matters.
#:
#: 0.59, arrived at twice over. First down from the mask's own 0.72 to 0.68,
#: because the widest glyph was landing at 31.7 against Android's safe radius
#: of 33 -- inside, but not by enough to survive a launcher with a tighter mask.
#: Then down again to 0.59, because fitting the MASK was never the binding
#: constraint: the glyph has to fit the TABLE, which is smaller, and measuring
#: against the mask alone had hidden that for every glyph in the pack.
#:
#: At 0.59 the widest glyph reaches 27.9 against a table edge of 30.2 and a
#: mask safe radius of 33. tools/verify-iconpack.py checks both bounds on every
#: build; the table one is the one that bites.
GLYPH_SCALE = 0.59
GLYPH_PIVOT = 50.0
GLYPH_TRANSLATE = (ADAPTIVE_SIZE - 100.0) / 2.0

#: Densities to render the tile at. The launcher picks by device density; the
#: tile is the only raster in the pack, so this is the whole of its size cost.
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
BASE_TILE_PX = 108


def table_radius():
    """Octagon-distance of the table's edge, in 108-unit viewport space.

    The boundary between the calm centre a glyph should sit on and the faceted
    crown it should not. Exported because tools/verify-iconpack.py checks every
    glyph against it, and a second copy of the arithmetic there would be free to
    drift away from this one.
    """
    apothem = ADAPTIVE_SIZE * (MASK_SIZE / ADAPTIVE_SIZE) * 0.5
    return apothem * TABLE_FRAC


def facet_lighting(psi):
    """Diffuse and specular for the eight crown facets, plus the flat table."""
    phis = np.arange(FACETS) * (2.0 * math.pi / FACETS)
    normals = np.stack([
        math.sin(FACET_TILT) * np.cos(phis),
        math.sin(FACET_TILT) * np.sin(phis),
        np.full(FACETS, math.cos(FACET_TILT)),
    ], axis=1)
    light = np.array([
        math.cos(psi) * math.sin(LIGHT_ELEVATION),
        math.sin(psi) * math.sin(LIGHT_ELEVATION),
        math.cos(LIGHT_ELEVATION),
    ])
    half = light + np.array([0.0, 0.0, 1.0])
    half /= np.linalg.norm(half)
    return (
        np.maximum(normals @ light, 0.0),
        np.maximum(normals @ half, 0.0) ** SPECULAR_POWER,
        max(float(light[2]), 0.0),
        max(float(half[2]), 0.0) ** SPECULAR_POWER,
    )


def render_tile(px):
    """The glass octagon, as an RGBA image `px` wide.

    The same construction as the boot animation's mark -- eight crown facets
    around a flat table, rim-darkened, with a specular edge -- but lit from a
    fixed angle and sized to the adaptive-icon mask rather than the screen.
    """
    # The octagon fills the mask area, not the full drawable: the corners of an
    # adaptive icon are bleed, and a tile drawn out to them would be clipped to
    # a different shape on every launcher.
    apothem = px * (MASK_SIZE / ADAPTIVE_SIZE) * 0.5
    cx = cy = px / 2.0

    ys, xs = np.mgrid[0:px, 0:px].astype(np.float32)
    dx, dy = xs - cx, ys - cy

    phis = np.arange(FACETS) * (2.0 * math.pi / FACETS)
    dists = np.stack([dx * math.cos(p) + dy * math.sin(p) for p in phis])
    order = np.argsort(dists, axis=0)
    facet = order[-1]
    d_max = np.take_along_axis(dists, order[-1][None], 0)[0]
    d_second = np.take_along_axis(dists, order[-2][None], 0)[0]

    phi = phis[facet]
    lateral_px = -dx * np.sin(phi) + dy * np.cos(phi)
    half_width = np.maximum(d_max, 1e-3) * math.tan(FACET_HALF_ANGLE)
    lateral = np.clip(lateral_px / half_width, -1.0, 1.0)

    diffuse, specular, table_diff, table_spec = facet_lighting(ICON_LIGHT_ANGLE)

    t = np.arange(FACETS) / (FACETS - 1.0)
    t = 1.0 - np.abs(t * 2.0 - 1.0)
    tints = ACCENT_A[None, :] * (1.0 - t[:, None]) + ACCENT_B[None, :] * t[:, None]

    table_r = apothem * TABLE_FRAC
    inside = d_max <= apothem
    is_table = inside & (d_max <= table_r)
    is_crown = inside & ~is_table

    shade = AMBIENT + (1.0 - AMBIENT) * diffuse
    colour = (tints * shade[:, None] + specular[:, None] * SPECULAR_STRENGTH)[facet]

    span = max(apothem - table_r, 1e-3)
    along = np.clip((apothem - d_max) / span, 0.0, 1.0)
    colour = colour * (0.74 + 0.36 * along)[:, :, None]
    colour = colour * rim_darkening(lateral, RIM_WIDTH, RIM_AMOUNT)[:, :, None]

    table_tint = ACCENT_A * 0.44 + ACCENT_B * 0.56
    table_lat = np.clip(d_max / max(table_r, 1e-3), 0.0, 1.0)
    gather = 1.0 - 0.30 * table_lat ** 2
    table_col = (table_tint[None, None, :]
                 * (AMBIENT + (1.0 - AMBIENT) * table_diff)
                 * gather[:, :, None] * 1.40
                 + table_spec * SPECULAR_STRENGTH * 0.75)
    table_col = table_col * rim_darkening(
        table_lat, RIM_WIDTH, RIM_AMOUNT * 0.8)[:, :, None]
    colour = np.where(is_table[:, :, None], table_col, colour)

    lit = EDGE_INTENSITY * (0.34 + 0.66 * np.clip(specular * 2.4, 0.0, 1.0))
    colour = colour + edge_highlight(
        apothem - d_max, apothem * 0.10, lateral, lit[facet])[:, :, None]

    w = max(px / 108.0, 0.7)
    seam = np.exp(-(( d_max - d_second) / w) ** 2) * 0.34 * is_crown
    girdle = np.exp(-((d_max - table_r) / (w * 1.3)) ** 2) * 0.30
    outline = np.exp(-((d_max - apothem) / (w * 1.4)) ** 2) * 0.60
    colour = colour + (seam + girdle + outline)[:, :, None]

    # Antialias the silhouette: a hard inside/outside test leaves stair-stepped
    # diagonals, and an octagon is mostly diagonals.
    alpha = np.clip((apothem - d_max) / max(w, 0.5) + 0.5, 0.0, 1.0)
    alpha = np.where(inside | (d_max < apothem + w), alpha, 0.0)

    rgb = np.clip(colour, 0.0, 1.0)
    out = np.dstack([rgb, alpha[:, :, None]])
    return Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), "RGBA")


# --- vector output ----------------------------------------------------------

VECTOR_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by iconpack/make-icons.py. Do not edit by hand. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="{size}dp"
    android:height="{size}dp"
    android:viewportWidth="{vp}"
    android:viewportHeight="{vp}">
    <group
        android:pivotX="{pivot}"
        android:pivotY="{pivot}"
        android:scaleX="{scale}"
        android:scaleY="{scale}"
        android:translateX="{off}"
        android:translateY="{off}">
        <path
            android:fillColor="{colour}"
            android:fillType="evenOdd"
            android:pathData="{path}" />
    </group>
</vector>
"""

ADAPTIVE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by iconpack/make-icons.py. Do not edit by hand. -->
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/facetui_tile" />
    <foreground android:drawable="@drawable/facetui_glyph_{name}" />
    <monochrome android:drawable="@drawable/facetui_mono_{name}" />
</adaptive-icon>
"""


def glyph_colour(hue):
    """Glyph fill for a hue in 0..1, as #AARRGGBB.

    Lifted well above the glass beneath it. A glyph tinted the same as its own
    surface disappears the moment the specular highlight crosses it.
    """
    c = ACCENT_A * (1.0 - hue) + ACCENT_B * hue
    c = np.clip(c * 0.45 + 0.55, 0.0, 1.0)     # pull toward white
    return "#FF%02X%02X%02X" % tuple(int(round(v * 255)) for v in c)


def write_vector(path, glyph_path, colour):
    # The glyphs are authored on 0..100; an adaptive foreground is 108 with the
    # middle 72 visible. Centre the 100-unit artwork in the 108-unit viewport
    # and let the safe-zone margin the glyphs already carry do the rest.
    xml = VECTOR_TEMPLATE.format(
        size=ADAPTIVE_SIZE, vp=ADAPTIVE_SIZE,
        off=f"{GLYPH_TRANSLATE:g}", scale=f"{GLYPH_SCALE:g}",
        pivot=f"{GLYPH_PIVOT:g}",
        colour=colour, path=re.sub(r"\s+", " ", glyph_path).strip(),
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)


APPFILTER_HEADER = """<?xml version="1.0" encoding="utf-8"?>
<!--
     Generated by iconpack/make-icons.py. Do not edit by hand.

     Component to icon mapping. A bare package matches any activity in it; a
     full ComponentInfo entry overrides its own package.

     This list is NOT the pack's coverage. Anything absent from it is themed
     procedurally by patches/iconloader/0001, which composites whatever icon
     the app ships onto the same glass. The entries here exist because a
     purpose-drawn glyph beats a wrapped one, not because the rest go untreated.
-->
<resources>
"""


def write_appfilter(path, entries):
    lines = [APPFILTER_HEADER]
    for component, name in sorted(entries):
        if "/" in component:
            comp = f"ComponentInfo{{{component}}}"
        else:
            comp = component
        lines.append(f'    <item component="{comp}" drawable="facetui_{name}" />\n')
    lines.append("</resources>\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def main():
    ap = argparse.ArgumentParser(description="Build the FacetUIIcons pack.")
    ap.add_argument("--out", default=os.path.join(HERE, "FacetUIIcons", "res"))
    ap.add_argument("--preview", help="also write a contact sheet here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    res = args.out
    for sub in ["drawable", "mipmap-anydpi-v26", "xml"] + \
               [f"drawable-{d}" for d in DENSITIES]:
        os.makedirs(os.path.join(res, sub), exist_ok=True)

    def note(m):
        if not args.quiet:
            print(m, file=sys.stderr)

    # --- the glass tile, once per density -----------------------------------
    note("[*] rendering the glass tile")
    for dpi, scale in DENSITIES.items():
        px = int(round(BASE_TILE_PX * scale))
        render_tile(px).save(os.path.join(res, f"drawable-{dpi}", "facetui_tile.png"))
        note(f"    {dpi:8s} {px}x{px}")

    # --- glyphs --------------------------------------------------------------
    used = sorted({g for g, _ in APPS.values()} | {FALLBACK_GLYPH})
    missing = [g for g in used if g not in GLYPHS]
    if missing:
        sys.exit(f"error: glyphs referenced but not defined: {', '.join(missing)}")

    hue_for = {}
    for glyph, hue in APPS.values():
        hue_for.setdefault(glyph, hue)
    hue_for.setdefault(FALLBACK_GLYPH, 0.5)

    note(f"[*] writing {len(used)} glyphs and adaptive icons")
    for name in used:
        write_vector(os.path.join(res, "drawable", f"facetui_glyph_{name}.xml"),
                     GLYPHS[name], glyph_colour(hue_for[name]))
        # The monochrome layer is the same artwork in a single flat colour, for
        # launchers that request it. Same path data, so the two cannot diverge.
        write_vector(os.path.join(res, "drawable", f"facetui_mono_{name}.xml"),
                     GLYPHS[name], "#FFFFFFFF")
        with open(os.path.join(res, "mipmap-anydpi-v26", f"facetui_{name}.xml"),
                  "w", encoding="utf-8") as fh:
            fh.write(ADAPTIVE_TEMPLATE.format(name=name))

    # --- appfilter -----------------------------------------------------------
    entries = [(component, glyph) for component, (glyph, _) in APPS.items()]
    write_appfilter(os.path.join(res, "xml", "appfilter.xml"), entries)
    note(f"[*] appfilter: {len(entries)} components -> {len(used)} icons")

    # --- sanity: every generated file is well-formed XML ---------------------
    bad = 0
    for dirpath, _, filenames in os.walk(res):
        for fn in filenames:
            if fn.endswith(".xml"):
                try:
                    ET.parse(os.path.join(dirpath, fn))
                except ET.ParseError as e:
                    print(f"  FAIL {fn}: {e}", file=sys.stderr)
                    bad += 1
    if bad:
        sys.exit(f"error: {bad} generated files are not well-formed")
    note("[*] all generated XML is well-formed")

    if args.preview:
        write_preview(args.preview, used, hue_for)
        note(f"[*] preview -> {args.preview}")


def write_preview(path, names, hue_for):
    """A contact sheet of every icon, composited the way a launcher would."""
    from PIL import ImageDraw
    cell = 132
    tile_px = 108
    cols = 8
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGBA", (cell * cols, cell * rows), (10, 12, 18, 255))
    tile = render_tile(tile_px)

    for i, name in enumerate(names):
        x = (i % cols) * cell + (cell - tile_px) // 2
        y = (i // cols) * cell + (cell - tile_px) // 2
        sheet.alpha_composite(tile, (x, y))
        glyph = rasterize_glyph(GLYPHS[name], tile_px, glyph_colour(hue_for[name]))
        sheet.alpha_composite(glyph, (x, y))

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sheet.convert("RGB").save(path)


def rasterize_glyph(path_data, px, colour_hex):
    """Render glyph path data, for the preview only.

    A deliberately small subset of SVG path syntax -- M, L, A, C, Z, absolute
    only -- which is all the glyphs use. Android parses the same data with its
    own full parser; this exists so the pack can be looked at without a device,
    not as a general SVG renderer.
    """
    from PIL import ImageDraw
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    ss = 4                                    # supersample; glyphs are thin

    # Reproduce the vector drawable's own group transform exactly: scale about
    # the glyph centre, then translate into the 108-unit viewport, then map
    # that viewport onto the pixel size. A preview drawn any other way would
    # show a layout the device will not produce.
    def place(x, y):
        gx = (x - GLYPH_PIVOT) * GLYPH_SCALE + GLYPH_PIVOT + GLYPH_TRANSLATE
        gy = (y - GLYPH_PIVOT) * GLYPH_SCALE + GLYPH_PIVOT + GLYPH_TRANSLATE
        k = px * ss / float(ADAPTIVE_SIZE)
        return gx * k, gy * k

    big = Image.new("L", (px * ss, px * ss), 0)

    rgb = tuple(int(colour_hex[i:i + 2], 16) for i in (3, 5, 7))

    for sub in _subpaths(path_data):
        pts = _flatten(sub)
        if len(pts) >= 3:
            # evenOdd: XOR each subpath so the counters punch through.
            layer = Image.new("L", big.size, 0)
            ImageDraw.Draw(layer).polygon(
                [place(x, y) for x, y in pts], fill=255)
            big = Image.fromarray(
                (np.asarray(big).astype(np.int16) ^ np.asarray(layer).astype(np.int16)
                 ).astype(np.uint8))

    mask = big.resize((px, px), Image.LANCZOS)
    img.paste(Image.new("RGBA", (px, px), rgb + (255,)), (0, 0), mask)
    return img


def _subpaths(data):
    out, cur = [], ""
    for tok in re.findall(r"[MmLlAaCcZzHhVv][^MmLlAaCcZzHhVv]*", data):
        if tok[0] in "Mm" and cur:
            out.append(cur)
            cur = tok
        else:
            cur += tok
    if cur:
        out.append(cur)
    return out


def _nums(s):
    return [float(n) for n in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", s)]


def _flatten(sub, steps=24):
    """Path to a polygon. Arcs and cubics are sampled, not solved exactly."""
    pts, cx, cy, start = [], 0.0, 0.0, None
    for tok in re.findall(r"[MmLlAaCcZzHhVv][^MmLlAaCcZzHhVv]*", sub):
        cmd, n = tok[0], _nums(tok[1:])
        if cmd == "M":
            for i in range(0, len(n) - 1, 2):
                cx, cy = n[i], n[i + 1]
                pts.append((cx, cy))
            start = pts[0] if pts else None
        elif cmd == "L":
            for i in range(0, len(n) - 1, 2):
                cx, cy = n[i], n[i + 1]
                pts.append((cx, cy))
        elif cmd == "H":
            for v in n:
                cx = v
                pts.append((cx, cy))
        elif cmd == "V":
            for v in n:
                cy = v
                pts.append((cx, cy))
        elif cmd == "C":
            for i in range(0, len(n) - 5, 6):
                x1, y1, x2, y2, x, y = n[i:i + 6]
                for k in range(1, steps + 1):
                    t = k / steps
                    u = 1 - t
                    pts.append((
                        u**3 * cx + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x,
                        u**3 * cy + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y))
                cx, cy = x, y
        elif cmd == "A":
            for i in range(0, len(n) - 6, 7):
                rx, ry, _, _, sweep, x, y = n[i:i + 7]
                pts.extend(_arc(cx, cy, rx, ry, sweep, x, y, steps))
                cx, cy = x, y
        elif cmd == "Z" and start:
            pts.append(start)
    return pts


def _arc(x0, y0, rx, ry, sweep, x1, y1, steps):
    """Sample an SVG arc. Only the circular, non-rotated case the glyphs use."""
    if rx <= 0 or ry <= 0:
        return [(x1, y1)]
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    d2 = (dx / rx) ** 2 + (dy / ry) ** 2
    if d2 > 1:                                # radii too small; scale them up
        k = math.sqrt(d2)
        rx, ry = rx * k, ry * k
        d2 = 1.0
    c = math.sqrt(max(0.0, 1.0 / d2 - 1.0))
    sign = 1.0 if sweep else -1.0
    ccx = mx + sign * c * rx * (dy / ry)
    ccy = my - sign * c * ry * (dx / rx)
    a0 = math.atan2((y0 - ccy) / ry, (x0 - ccx) / rx)
    a1 = math.atan2((y1 - ccy) / ry, (x1 - ccx) / rx)
    if sweep and a1 < a0:
        a1 += 2 * math.pi
    if not sweep and a1 > a0:
        a1 -= 2 * math.pi
    return [(ccx + rx * math.cos(a0 + (a1 - a0) * k / steps),
             ccy + ry * math.sin(a0 + (a1 - a0) * k / steps))
            for k in range(1, steps + 1)]


if __name__ == "__main__":
    main()
