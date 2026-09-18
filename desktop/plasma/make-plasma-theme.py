#!/usr/bin/env python3
"""
Build the FacetUI Plasma style and colour scheme.

    ./make-plasma-theme.py

WHAT THIS SUPPLIES, AND WHY IT IS NEEDED

Three things must be true together for a surface to be glass: blur,
translucency, and a boundary. On octagonOS Desktop they come from three
different places, and this is two of them.

    blur          KWin's blur effect
    translucency  HERE -- the theme's surfaces, and how opaque they are
    a boundary    HERE -- the hairline, a 1px stroke at every surface edge

The fourth piece, the specular edge and the rim, is the KWin effect in
desktop/kwin. It assumes the other two are already true; without them it lights
a surface that is not glass.

THE TINT IS NOT WRITTEN HERE

Plasma recolours a theme's SVGs by replacing a stylesheet with the live colour
scheme, so an element marked `class="ColorScheme-Background"` and filled with
`currentColor` takes the system's colour rather than one baked in. That is the
same rule the Android edition follows -- neutral-to-accent, not
dynamic-to-fixed -- expressed in the mechanism the platform already has.

What IS written here is the alpha, from shared/facetui/palette.py, so a dialog
on the desktop is as translucent as a dialog on the phone.

Requires NumPy (for the palette only).
"""

import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "shared"))

from facetui.palette import (  # noqa: E402
    ACCENT_A, ACCENT_B, HAIRLINE_ALPHA, SURFACE_ALPHA,
)

THEME = "FacetUI"

#: Corner radius, in the SVG's own units. Plasma scales the frame, so this is a
#: proportion rather than a pixel count.
R = 8
#: The stretched middle of each edge, and of the centre.
M = 16
#: Space between elements in the sheet. Plasma reads each element's bounding
#: box, so they must not touch -- two elements sharing an edge get bounding
#: boxes that overlap, and the frame comes out a pixel wrong on every side.
GAP = 4

#: Which surface gets which alpha, and how far its content sits from the edge.
#: The tier names are the ones in shared/facetui/palette.py.
#:
#: THE MARGIN HAS TO CLEAR THE CORNER RADIUS. A rounded frame with a one-pixel
#: margin puts content inside the curve, where the surface has already fallen
#: away -- text clipped by a corner, and it only shows at the corners, so it
#: reads as a font problem. A square-cornered frame has no such constraint, so
#: the panel is free to be tight.
SURFACES = {
    ("widgets", "panel-background"): ("shade", 2),
    ("widgets", "background"): ("dialog", R),
    ("widgets", "tooltip"): ("tooltip", R - 2),
    ("dialogs", "background"): ("dialog", R),
}


def rgb(v):
    """A 0..1 triple as an ini colour, which KColorScheme wants comma-separated."""
    return ",".join(str(int(round(max(0.0, min(1.0, c)) * 255))) for c in v)


def hexc(v):
    return "#" + "".join(f"{int(round(max(0.0, min(1.0, c)) * 255)):02x}" for c in v)


def mix(a, b, t):
    return a * (1.0 - t) + b * t


# --- the colour scheme ------------------------------------------------------
#
# Derived from the two accents rather than typed as hex, so the desktop's
# chrome and the boot animation's facets come from one pair of numbers.
#
# The ramp is deliberately NEAR-NEUTRAL: these are large areas, and FacetUI's
# rule for large surfaces is the muted accent ramp, not the loud one. A desktop
# tinted as strongly as the mark would be exhausting to look at.
ACCENT = (ACCENT_A + ACCENT_B) / 2.0


def ramp(level, tint=0.10):
    """A neutral step, pulled a little toward the accent."""
    import numpy as np
    return mix(np.array([level, level, level]), ACCENT * level * 1.6, tint)


def colours():
    import numpy as np
    bg = ramp(0.085)                 # window background
    view = ramp(0.055)               # text entry, lists -- deeper than window
    button = ramp(0.135)
    header = ramp(0.115)
    tooltip = ramp(0.105)
    fg = mix(np.array([0.98, 0.98, 0.98]), ACCENT, 0.06)
    dim = mix(np.array([0.63, 0.66, 0.70]), ACCENT, 0.10)

    common = {
        "ForegroundNormal": rgb(fg),
        "ForegroundInactive": rgb(dim),
        "ForegroundActive": rgb(mix(fg, ACCENT_A, 0.55)),
        "ForegroundLink": rgb(ACCENT_A),
        "ForegroundVisited": rgb(ACCENT_B),
        "ForegroundNegative": "224,102,102",
        "ForegroundNeutral": "230,170,90",
        "ForegroundPositive": "108,200,150",
    }

    def group(normal, alternate):
        d = dict(common)
        d["BackgroundNormal"] = rgb(normal)
        d["BackgroundAlternate"] = rgb(alternate)
        return d

    out = {
        "Colors:Window": group(bg, ramp(0.105)),
        "Colors:View": group(view, ramp(0.075)),
        "Colors:Button": group(button, ramp(0.115)),
        "Colors:Tooltip": group(tooltip, ramp(0.085)),
        "Colors:Header": group(header, ramp(0.095)),
        "Colors:Complementary": group(ramp(0.07), ramp(0.09)),
        "Colors:Selection": {
            **common,
            "BackgroundNormal": rgb(ACCENT_A * 0.62),
            "BackgroundAlternate": rgb(ACCENT_B * 0.62),
            "ForegroundNormal": "255,255,255",
        },
        "WM": {
            "activeBackground": rgb(ramp(0.10)),
            "activeForeground": rgb(fg),
            "activeBlend": rgb(fg),
            "inactiveBackground": rgb(ramp(0.075)),
            "inactiveForeground": rgb(dim),
            "inactiveBlend": rgb(dim),
        },
        "General": {
            "ColorScheme": THEME,
            "Name": THEME,
            "shadeSortColumn": "true",
        },
    }
    return out


def write_colours(path):
    with open(path, "w") as fh:
        for group, entries in colours().items():
            fh.write(f"[{group}]\n")
            for key in sorted(entries):
                fh.write(f"{key}={entries[key]}\n")
            fh.write("\n")


# --- the frame SVGs ---------------------------------------------------------

def stylesheet():
    """The block Plasma replaces with the live colour scheme.

    The values here are only what a plain SVG viewer sees; Plasma overwrites
    the whole element. They are the FacetUI colours so that opening one of
    these files outside Plasma shows something honest rather than black.
    """
    c = colours()["Colors:Window"]
    bg = "#%02x%02x%02x" % tuple(int(x) for x in c["BackgroundNormal"].split(","))
    fg = "#%02x%02x%02x" % tuple(int(x) for x in c["ForegroundNormal"].split(","))
    return (f'  <style type="text/css" id="current-color-scheme">\n'
            f'    .ColorScheme-Background {{ color: {bg}; stop-color: {bg}; }}\n'
            f'    .ColorScheme-Text {{ color: {fg}; stop-color: {fg}; }}\n'
            f'  </style>\n')


def tile(eid, x, y, w, h, alpha, corners, edges):
    """One element of the nine.

    `corners` names which of this tile's corners are rounded, `edges` which of
    its sides carry the hairline. Both are about the OUTSIDE of the frame: the
    centre tile has neither, because a hairline through the middle of a panel
    is a line across a panel.
    """
    parts = [f'  <g id="{eid}" transform="translate({x},{y})">']

    # The fill. `currentColor` plus the class is what lets Plasma recolour it.
    if corners:
        parts.append(f'    <path d="{corner_fill(w, h, corners[0])}" '
                     f'class="ColorScheme-Background" '
                     f'style="fill:currentColor;fill-opacity:{alpha:.4f};'
                     f'stroke:none" />')
    else:
        parts.append(f'    <rect x="0" y="0" width="{w}" height="{h}" '
                     f'class="ColorScheme-Background" '
                     f'style="fill:currentColor;fill-opacity:{alpha:.4f};'
                     f'stroke:none" />')

    # The hairline. NOTHING IN THIS THEME IS STROKED, and that is not a style
    # choice -- it is two separate bugs, both measured.
    #
    # A stroke on a REPEATED element: Plasma tiles the four border elements to
    # fill a frame of any width. A stroke is centred on its path and
    # antialiased on both sides, so where two repeats meet, each contributes
    # partial coverage to the seam pixel and the two do not sum to one. The
    # line comes out with a dip at every repeat -- 12 against 40 -- which is a
    # dotted line if you look closely and a clean one if you do not.
    #
    # A stroke on a CORNER element: Plasma sizes each element from its
    # bounding box, and a stroke makes that box wider than the geometry it
    # decorates. The whole tile is then squeezed to fit, leaving its last row
    # and column half-covered -- a hairline seam between the corner and the two
    # borders it meets. Over a dark backdrop that reads as a dark notch; over a
    # bright wallpaper it reads as a bright one. Removing the stroke was what
    # identified it: the seam went from 9 back to 17, the surface's own value.
    #
    # A fill has exact edges and no bounds of its own beyond its geometry.
    if edges:
        for d in hairline_shapes(w, h, corners, edges):
            parts.append(f'    <path d="{d}" class="ColorScheme-Text" '
                         f'style="fill:currentColor;'
                         f'fill-opacity:{HAIRLINE_ALPHA:.4f};'
                         f'stroke:none" />')
    parts.append("  </g>")
    return "\n".join(parts)


def corner_fill(w, h, which):
    """One rounded corner, as the quarter disc it actually is.

    Written out per corner rather than derived from a general rounded-rectangle
    routine. The general version was right for the top-left and wrong for the
    bottom-left -- an arc with the wrong sweep flag draws a leaf, not a corner
    -- and the mistake was invisible while a stroke sat on top of it. Four
    explicit paths cannot go quietly wrong in three cases out of four.

    The centre of curvature is the tile corner DIAGONALLY OPPOSITE the one
    being rounded, which is the whole trick.
    """
    r = min(R, w, h)
    if which == "tl":                       # centre (r, r)
        return f"M 0,{r} A {r},{r} 0 0 1 {r},0 L {r},{r} Z"
    if which == "tr":                       # centre (0, r)
        return f"M 0,0 A {r},{r} 0 0 1 {r},{r} L 0,{r} Z"
    if which == "bl":                       # centre (r, 0)
        return f"M 0,0 A {r},{r} 0 0 0 {r},{r} L {r},0 Z"
    if which == "br":                       # centre (0, 0)
        return f"M {r},0 A {r},{r} 0 0 1 0,{r} L 0,0 Z"
    raise ValueError(which)


def hairline_shapes(w, h, corners, edges):
    """The hairline for one tile, as filled paths one unit thick.

    A straight edge is a rectangle spanning the tile's FULL length -- no inset
    along the edge, or every repeat leaves a gap. A rounded corner is an
    annular sector between radius r and r-1, which is the same one-unit band
    following the curve, and meets the straight rectangles exactly.
    """
    r = min(R, w, h)

    if corners:
        which = corners[0]
        # The same quarter arc as a band one unit thick: out along radius r,
        # back along radius r-1, same centres as corner_fill above.
        q = r - 1
        if which == "tl":
            return [f"M 0,{r} A {r},{r} 0 0 1 {r},0 L {r},1 "
                    f"A {q},{q} 0 0 0 1,{r} Z"]
        if which == "tr":
            return [f"M 0,0 A {r},{r} 0 0 1 {r},{r} L {r - 1},{r} "
                    f"A {q},{q} 0 0 0 0,1 Z"]
        if which == "bl":
            return [f"M 0,0 A {r},{r} 0 0 0 {r},{r} L {r},{r - 1} "
                    f"A {q},{q} 0 0 1 1,0 Z"]
        if which == "br":
            return [f"M {r},0 A {r},{r} 0 0 1 0,{r} L 0,{r - 1} "
                    f"A {q},{q} 0 0 0 {r - 1},0 Z"]
        return []

    out = []
    if "t" in edges:
        out.append(f"M 0,0 H {w} V 1 H 0 Z")
    if "b" in edges:
        out.append(f"M 0,{h - 1} H {w} V {h} H 0 Z")
    if "l" in edges:
        out.append(f"M 0,0 H 1 V {h} H 0 Z")
    if "r" in edges:
        out.append(f"M {w - 1},0 H {w} V {h} H {w - 1} Z")
    return out


def frame_svg(alpha, rounded=True, margin=R):
    """A nine-element FrameSvg sheet.

    The nine ids are not optional and they are not negotiable: Plasma's
    FrameSvg asks for exactly these, and a missing one is not an error -- the
    frame just comes out wrong in a way that looks like a rendering bug.
    """
    c0, c1 = 0, R + GAP
    c2 = c1 + M + GAP
    total = c2 + R
    corners = ("tl", "tr", "br", "bl") if rounded else ()

    els = [
        tile("topleft", c0, c0, R, R, alpha, ("tl",) if rounded else (), "tl"),
        tile("top", c1, c0, M, R, alpha, (), "t"),
        tile("topright", c2, c0, R, R, alpha, ("tr",) if rounded else (), "tr"),
        tile("left", c0, c1, R, M, alpha, (), "l"),
        tile("center", c1, c1, M, M, alpha, (), ""),
        tile("right", c2, c1, R, M, alpha, (), "r"),
        tile("bottomleft", c0, c2, R, R, alpha, ("bl",) if rounded else (), "bl"),
        tile("bottom", c1, c2, M, R, alpha, (), "b"),
        tile("bottomright", c2, c2, R, R, alpha, ("br",) if rounded else (), "br"),
    ]

    # Margin hints. Without them Plasma uses the corner elements' size as the
    # content inset, which on a panel means eight pixels of padding nobody
    # asked for. A zero-size hint element is how the format says "this much".
    hints = []
    for side in ("top", "bottom", "left", "right"):
        hints.append(f'  <rect id="hint-{side}-margin" x="0" y="{total + 8}" '
                     f'width="{margin}" height="{margin}" style="fill:none" />')

    body = "\n".join(els + hints)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!-- Generated by desktop/plasma/make-plasma-theme.py. '
            f'Do not edit. -->\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{total}" height="{total + 16}" '
            f'viewBox="0 0 {total} {total + 16}">\n'
            f'{stylesheet()}{body}\n</svg>\n')


METADATA = {
    "KPlugin": {
        "Category": "",
        "Description": "Glass: translucent surfaces with a hairline, for FacetUI",
        "EnabledByDefault": True,
        "License": "Apache-2.0",
        "Name": THEME,
        "Version": "0.1",
    },
    "X-Plasma-API": "5.0",
}

#: Adaptive transparency turns the panel opaque when a window is maximised.
#: It exists for legibility and it is a reasonable default -- but on this theme
#: it switches the glass off exactly when there is something behind the panel
#: worth seeing through it. Named here rather than left to surprise someone.
PLASMARC = """[AdaptiveTransparency]
enabled=false
"""


def main():
    ap = argparse.ArgumentParser(description="Build the FacetUI Plasma style.")
    ap.add_argument("--out", default=str(HERE / THEME))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out)

    def note(m):
        if not args.quiet:
            print(m, file=sys.stderr)

    written = 0
    for (folder, name), (tier, margin) in SURFACES.items():
        alpha = SURFACE_ALPHA[tier]
        # A panel is docked to an edge, so its outer corners are square; a
        # dialog or a menu floats, so its corners are round.
        rounded = name != "panel-background"

        variants = {
            # Glass, for a compositing session.
            "translucent": alpha,
            # Opaque, for one without. FacetUI's own rule says a translucent
            # surface with nothing blurred behind it is not glass, it is a
            # dirty window -- so when there is no compositor this is honestly
            # solid rather than pretending.
            "solid": 1.0,
        }
        # The base copy Plasma falls back to when neither prefix resolves.
        variants[""] = alpha

        for prefix, a in variants.items():
            d = out / prefix / folder if prefix else out / folder
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.svg").write_text(frame_svg(a, rounded, margin))
            written += 1

    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata.json").write_text(json.dumps(METADATA, indent=4) + "\n")
    write_colours(out / "colors")
    (out / "plasmarc").write_text(PLASMARC)

    note(f"[*] {out}")
    note(f"    {written} frame SVGs, a colour scheme, metadata and plasmarc")
    note(f"    surface alphas: " + ", ".join(
        f"{k} {v:.2f}" for k, v in sorted(SURFACE_ALPHA.items())))


if __name__ == "__main__":
    main()
