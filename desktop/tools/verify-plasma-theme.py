#!/usr/bin/env python3
"""
Check the FacetUI Plasma style without Plasma.

    desktop/tools/verify-plasma-theme.py [theme-dir]

THE RUNNING CHECK IS THE STRONGER ONE

`desktop/tools/run-plasma-theme.sh` renders every surface with Plasma's own
SVG engine and measures what came out. Where it can run, it settles more than
this does. This is the fast version, for a machine without KSvg's development
packages -- and for the rules below, which are about the SOURCE and are
therefore invisible to a renderer that only sees pixels.

Every check exists because the corresponding mistake was made here.

Requires NumPy (for the shared palette only).
"""

import argparse
import configparser
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "shared"))

from facetui.palette import HAIRLINE_ALPHA, SURFACE_ALPHA  # noqa: E402

SVG = "{http://www.w3.org/2000/svg}"

#: The nine. KSvg asks for exactly these, and a missing one is not an error --
#: it draws nothing there and the frame comes out with a bite missing.
FRAME_ELEMENTS = [
    "center", "top", "bottom", "left", "right",
    "topleft", "topright", "bottomleft", "bottomright",
]

#: The four that KSvg REPEATS to fill a frame of any size. The corners are
#: drawn once; these are not, and that distinction has consequences below.
TILED_ELEMENTS = ["top", "bottom", "left", "right"]

#: Colour groups KColorScheme expects. A missing one is not fatal, but it means
#: that part of the desktop falls back to some other scheme's colours, which
#: looks like a rendering bug in one widget.
COLOUR_GROUPS = [
    "Colors:Window", "Colors:View", "Colors:Button", "Colors:Selection",
    "Colors:Tooltip", "Colors:Complementary", "WM", "General",
]

#: Which alpha each surface should carry, by tier name in the shared palette.
EXPECTED = {
    "widgets/panel-background": "shade",
    "widgets/background": "dialog",
    "dialogs/background": "dialog",
    "widgets/tooltip": "tooltip",
}

fails = []


def fail(msg):
    fails.append(msg)


def ids_of(root):
    return {el.get("id"): el for el in root.iter() if el.get("id")}


def check_svg(path, rel, translucent):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        fail(f"{rel}: not well-formed XML -- {exc}")
        return

    # The recurring one. XML forbids a double hyphen inside a comment body, and
    # every tool in this project has rejected it at some point: aapt2 on the
    # Android overlays, rcc on the KWin effect's .qrc.
    text = path.read_text()
    for comment in re.findall(r"<!--(.*?)-->", text, re.S):
        if "--" in comment:
            fail(f"{rel}: a comment contains a double hyphen, which XML "
                 f"forbids inside a comment body")

    elements = ids_of(root)

    missing = [e for e in FRAME_ELEMENTS if e not in elements]
    if missing:
        fail(f"{rel}: frame elements missing: {', '.join(missing)}. KSvg draws "
             f"nothing for an element it cannot find and does not call that an "
             f"error, so the frame comes out with a bite taken out of it")

    # THE SEAM RULE.
    #
    # KSvg repeats the border elements. A stroke is centred on its path and
    # antialiased on both sides, so where two repeats meet, each contributes
    # partial coverage to the seam pixel and the two do not sum to one. The
    # hairline comes out with a dip at every repeat -- measurably 12 against 40
    # -- which reads as a dotted line. A filled rectangle has exact edges and
    # tiles without a seam. The corners are drawn once, so they may stroke.
    for name in TILED_ELEMENTS:
        el = elements.get(name)
        if el is None:
            continue
        for child in el.iter():
            style = child.get("style", "")
            if "stroke:currentColor" in style or re.search(r"stroke-width", style):
                fail(f"{rel}: the '{name}' element strokes its hairline. KSvg "
                     f"REPEATS this element, and two repeats of a stroke leave "
                     f"a gap at every seam -- a dotted line, not a missing one. "
                     f"Use a filled rectangle; only the corner elements, which "
                     f"are drawn once, may stroke")

    # Margins have to clear the corner radius, or content sits inside the curve
    # -- clipped text, but only at the corners, so it reads as a font problem.
    radius = 0.0
    tl = elements.get("topleft")
    if tl is not None:
        for child in tl.iter():
            d = child.get("d", "")
            m = re.search(r"A\s*([\d.]+)", d)
            if m:
                radius = max(radius, float(m.group(1)))
    for side in ("top", "bottom", "left", "right"):
        hint = elements.get(f"hint-{side}-margin")
        if hint is None:
            fail(f"{rel}: no hint-{side}-margin. Without it KSvg uses the "
                 f"corner element's size as the content inset")
            continue
        try:
            margin = float(hint.get("width" if side in ("left", "right")
                                    else "height"))
        except (TypeError, ValueError):
            fail(f"{rel}: hint-{side}-margin has no usable size")
            continue
        if radius and margin < radius * 0.7:
            fail(f"{rel}: hint-{side}-margin is {margin:g} but the corner "
                 f"radius is about {radius:g}; content would sit inside the "
                 f"curve and be clipped at the corners")

    # Bounding boxes must not touch. Two elements sharing an edge get
    # overlapping bounding boxes, and the frame comes out a pixel wrong on
    # every side.
    boxes = {}
    for name in FRAME_ELEMENTS:
        el = elements.get(name)
        if el is None:
            continue
        m = re.match(r"translate\(([-\d.]+),\s*([-\d.]+)\)",
                     el.get("transform", ""))
        if m:
            boxes[name] = (float(m.group(1)), float(m.group(2)))
    for a, (ax, ay) in boxes.items():
        for b, (bx, by) in boxes.items():
            if a < b and (ax, ay) == (bx, by):
                fail(f"{rel}: '{a}' and '{b}' are at the same position, so "
                     f"their bounding boxes coincide")

    # The alpha, against the one definition in shared/facetui/palette.py.
    key = rel.replace(".svg", "")
    for prefix in ("translucent/", "solid/", ""):
        if key.startswith(prefix) and prefix:
            key = key[len(prefix):]
            break
    tier = EXPECTED.get(key)
    if tier is not None:
        want = SURFACE_ALPHA[tier] if translucent else 1.0
        centre = elements.get("center")
        got = None
        if centre is not None:
            for child in centre.iter():
                m = re.search(r"fill-opacity:([\d.]+)", child.get("style", ""))
                if m:
                    got = float(m.group(1))
                    break
        if got is None:
            fail(f"{rel}: the centre element has no fill-opacity")
        elif abs(got - want) > 0.002:
            fail(f"{rel}: centre alpha is {got:.4f}, but "
                 f"shared/facetui/palette.py says {want:.4f} for this tier")

    # The recolouring hook. Without it Plasma cannot apply the colour scheme,
    # and the surface keeps whatever colour is written in the file -- which is
    # the opposite of FacetUI's rule that the tint comes from the system.
    if not any(el.get("id") == "current-color-scheme" for el in root.iter()):
        fail(f"{rel}: no element with id 'current-color-scheme'. Plasma "
             f"replaces that stylesheet with the live colour scheme; without "
             f"it the surface is a fixed colour")
    # Looked for on the ELEMENTS, not in the file. The stylesheet block
    # declares `.ColorScheme-Background` too, so a plain substring search over
    # the text passes even when every element has been moved off the class --
    # which is exactly the case where nothing takes the system's tint.
    tinted = [el for el in root.iter()
              if "ColorScheme-Background" in (el.get("class") or "")]
    if not tinted:
        fail(f"{rel}: no element is classed ColorScheme-Background, so nothing "
             f"takes the system's tint. FacetUI's rule is that the colour "
             f"comes from the platform's live scheme, never from the file")


def main():
    ap = argparse.ArgumentParser(description="Check the FacetUI Plasma style.")
    ap.add_argument("theme", nargs="?",
                    default=str(HERE.parent / "plasma" / "FacetUI"))
    args = ap.parse_args()

    theme = pathlib.Path(args.theme).resolve()
    if not theme.is_dir():
        print(f"[FAIL] no such theme directory: {theme}")
        return 2

    meta = theme / "metadata.json"
    if not meta.exists():
        fail("metadata.json is missing; Plasma will not list the theme")
    else:
        try:
            d = json.loads(meta.read_text())
            if d.get("X-Plasma-API") != "5.0":
                fail("metadata.json does not set X-Plasma-API to \"5.0\"")
            if "Name" not in d.get("KPlugin", {}):
                fail("metadata.json has no KPlugin.Name")
        except json.JSONDecodeError as exc:
            fail(f"metadata.json is not valid JSON -- {exc}")

    colours = theme / "colors"
    if not colours.exists():
        fail("the colors file is missing; the theme has no colour scheme")
    else:
        cp = configparser.ConfigParser(strict=False)
        cp.optionxform = str
        try:
            cp.read_string(colours.read_text())
            missing = [g for g in COLOUR_GROUPS if g not in cp]
            if missing:
                fail(f"the colors file has no {', '.join(missing)}")
        except configparser.Error as exc:
            fail(f"the colors file does not parse -- {exc}")

    svgs = sorted(theme.rglob("*.svg"))
    if not svgs:
        fail("the theme contains no SVGs at all")
    for path in svgs:
        rel = str(path.relative_to(theme))
        # The solid variants are the no-compositing fallback and are meant to
        # be opaque: a translucent surface with nothing blurred behind it is
        # not glass, it is a dirty window.
        check_svg(path, rel, translucent=not rel.startswith("solid/"))

    for m in fails:
        print(f"[FAIL] {m}")
    if fails:
        print(f"\nFAILED: {len(fails)} problem(s) in {theme}")
        return 1
    print(f"[ok] {theme}: {len(svgs)} surfaces, nine frame elements each, "
          f"alphas match shared/facetui/palette.py")
    print("     Static only. It does not render anything -- see")
    print("     desktop/tools/run-plasma-theme.sh, which does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
