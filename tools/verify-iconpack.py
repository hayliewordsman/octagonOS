#!/usr/bin/env python3
"""
Verify the FacetUIIcons pack before it is packaged.

    tools/verify-iconpack.py iconpack/FacetUIIcons

Checks the things that break an icon pack silently -- the app keeps its stock
icon and nothing anywhere says why:

  1. every generated XML file is well-formed
  2. every appfilter entry names a drawable or mipmap the pack contains
  3. every adaptive icon's background, foreground and monochrome layers resolve
  4. the glass tile exists at every density, is square, and has real
     transparency (a tile that came out fully opaque would show as a square
     behind every octagon)
  5. every glyph stays inside BOTH bounds that constrain it, once its group
     transform is applied: Android's mask safe zone, and -- the tighter one --
     FacetUI's own calm centre, the table the glass tile leaves flat
  6. nothing in the pack is orphaned

Exits non-zero on any failure. Needs Pillow; everything else is stdlib.
"""

import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

try:
    from PIL import Image
except ImportError:
    sys.exit("error: this needs Pillow (pip install Pillow)")

ANDROID = "{http://schemas.android.com/apk/res/android}"

#: Android's adaptive icon geometry, and the safe zone it documents: a circle
#: of diameter 66 centred in the 108-unit viewport.
ADAPTIVE_SIZE = 108.0
SAFE_DIAMETER = 66.0

#: The eight edge normals of the octagon, for measuring a point against it.
#: The table is an octagon, not a circle, so a plain radius over-reports in the
#: vertex directions and would reject artwork that actually fits.
OCTAGON_NORMALS = [(math.cos(k * math.pi / 4), math.sin(k * math.pi / 4))
                   for k in range(8)]


def load_generator(pack):
    """Import the generator beside the pack, for its geometry and flattener.

    The design's own numbers, not a second copy of them here: the table radius
    and the glyph transform are what the tile is drawn from, so a duplicate set
    in this file would be free to drift away from the thing being checked.

    Returns None if it cannot be loaded, in which case the table check is
    skipped and said to be skipped rather than quietly passing.
    """
    import importlib.util
    gen = os.path.join(os.path.dirname(os.path.abspath(pack)), "make-icons.py")
    if not os.path.exists(gen):
        return None
    try:
        sys.path.insert(0, os.path.dirname(gen))
        sys.path.insert(0, os.path.join(os.path.dirname(gen), "..", "bootanimation"))
        spec = importlib.util.spec_from_file_location("_facetui_gen", gen)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"  warn  could not load {gen}: {e}")
        return None


def octagon_distance(gx, gy):
    """How far a point is out along the octagon, in 108-unit viewport space."""
    dx, dy = gx - ADAPTIVE_SIZE / 2.0, gy - ADAPTIVE_SIZE / 2.0
    return max(dx * nx + dy * ny for nx, ny in OCTAGON_NORMALS)

#: Densities the tile must exist at.
DENSITIES = ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]


class Checker:
    def __init__(self):
        self.failed = 0
        self.warned = 0

    def ok(self, m):
        print(f"  ok    {m}")

    def fail(self, m):
        print(f"  FAIL  {m}")
        self.failed += 1

    def warn(self, m):
        print(f"  warn  {m}")
        self.warned += 1


def res_names(res, kinds):
    """Resource names present under any directory of the given kinds."""
    found = {}
    for entry in sorted(os.listdir(res)):
        kind = entry.split("-", 1)[0]
        if kind not in kinds:
            continue
        d = os.path.join(res, entry)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            found.setdefault(os.path.splitext(fn)[0], []).append(entry)
    return found


def path_points(data):
    """Every explicit coordinate pair in path data.

    Deliberately crude: it reads the on-path anchor points and ignores bezier
    control points, which can legitimately sit outside the shape they steer.
    Good enough to catch artwork drawn at the wrong scale, which is the failure
    this is for, without re-implementing a path flattener.
    """
    pts = []
    for tok in re.findall(r"[MmLlCcAaHhVv][^MmLlCcAaHhVvZz]*", data):
        cmd, nums = tok[0], [float(n) for n in
                             re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", tok[1:])]
        if cmd in "ML":
            pts += [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
        elif cmd == "C":
            # endpoints only
            pts += [(nums[i + 4], nums[i + 5]) for i in range(0, len(nums) - 5, 6)]
        elif cmd == "A":
            pts += [(nums[i + 5], nums[i + 6]) for i in range(0, len(nums) - 6, 7)]
    return pts


def main():
    ap = argparse.ArgumentParser(description="Verify the FacetUIIcons pack.")
    ap.add_argument("pack", help="path to the FacetUIIcons directory")
    args = ap.parse_args()

    res = os.path.join(args.pack, "res")
    if not os.path.isdir(res):
        sys.exit(f"error: no res/ under {args.pack}")

    c = Checker()

    # --- 1. well-formedness -------------------------------------------------
    print("XML")
    xmls = []
    for dirpath, _, filenames in os.walk(res):
        for fn in sorted(filenames):
            if fn.endswith(".xml"):
                p = os.path.join(dirpath, fn)
                xmls.append(p)
                try:
                    ET.parse(p)
                except ET.ParseError as e:
                    c.fail(f"{os.path.relpath(p, args.pack)}: {e}")
    manifest = os.path.join(args.pack, "AndroidManifest.xml")
    try:
        ET.parse(manifest)
    except (ET.ParseError, FileNotFoundError) as e:
        c.fail(f"AndroidManifest.xml: {e}")
    if not c.failed:
        c.ok(f"{len(xmls)} resource files and the manifest are well-formed")

    drawables = res_names(res, {"drawable", "mipmap"})

    # --- 2. appfilter -------------------------------------------------------
    print("\nappfilter")
    af = os.path.join(res, "xml", "appfilter.xml")
    entries = []
    if not os.path.exists(af):
        c.fail("res/xml/appfilter.xml is missing")
    else:
        root = ET.parse(af).getroot()
        for item in root.findall("item"):
            comp = item.get("component")
            drw = item.get("drawable")
            if not comp or not drw:
                c.fail(f"appfilter item missing component or drawable: "
                       f"{ET.tostring(item, encoding='unicode').strip()}")
                continue
            entries.append((comp, drw))

        missing = sorted({d for _, d in entries if d not in drawables})
        if missing:
            for d in missing:
                c.fail(f"appfilter names '{d}', which the pack does not contain "
                       f"-- that app will silently keep its stock icon")
        else:
            c.ok(f"{len(entries)} entries, all resolving to real drawables")

        dupes = [comp for comp in {x for x, _ in entries}
                 if [x for x, _ in entries].count(comp) > 1]
        if dupes:
            c.fail(f"duplicate components in appfilter: {', '.join(sorted(dupes))}")

    # --- 3. adaptive icon layers -------------------------------------------
    print("\nadaptive icons")
    adaptive = [p for p in xmls if os.sep + "mipmap" in p]
    layer_refs = set()
    bad_layers = 0
    for p in adaptive:
        root = ET.parse(p).getroot()
        if root.tag != "adaptive-icon":
            c.fail(f"{os.path.basename(p)}: root is <{root.tag}>, not <adaptive-icon>")
            continue
        for layer in ("background", "foreground", "monochrome"):
            el = root.find(layer)
            if el is None:
                if layer == "monochrome":
                    c.warn(f"{os.path.basename(p)}: no <monochrome> layer")
                else:
                    c.fail(f"{os.path.basename(p)}: no <{layer}> layer")
                    bad_layers += 1
                continue
            ref = el.get(f"{ANDROID}drawable") or ""
            name = ref.split("/")[-1]
            layer_refs.add(name)
            if name not in drawables:
                c.fail(f"{os.path.basename(p)}: <{layer}> points at '{ref}', "
                       f"which does not exist")
                bad_layers += 1
    if adaptive and not bad_layers:
        c.ok(f"{len(adaptive)} adaptive icons, all layers resolving")

    # --- 4. the glass tile --------------------------------------------------
    print("\nglass tile")
    tile_ok = True
    for dpi in DENSITIES:
        p = os.path.join(res, f"drawable-{dpi}", "facetui_tile.png")
        if not os.path.exists(p):
            c.fail(f"no tile at {dpi}")
            tile_ok = False
            continue
        img = Image.open(p)
        if img.size[0] != img.size[1]:
            c.fail(f"{dpi} tile is {img.size[0]}x{img.size[1]}, not square")
            tile_ok = False
        if img.mode != "RGBA":
            c.fail(f"{dpi} tile is {img.mode}, not RGBA -- it needs an alpha "
                   f"channel or the octagon will render as a square")
            tile_ok = False
            continue
        alpha = img.getchannel("A")
        lo, hi = alpha.getextrema()
        if lo != 0:
            c.fail(f"{dpi} tile has no fully transparent pixels (min alpha "
                   f"{lo}) -- the corners outside the octagon are not cut out")
            tile_ok = False
        if hi != 255:
            c.fail(f"{dpi} tile is nowhere fully opaque (max alpha {hi})")
            tile_ok = False
    if tile_ok:
        c.ok(f"present at all {len(DENSITIES)} densities, square, with "
             f"a real alpha channel")

    # --- 5. glyphs inside both bounds ---------------------------------------
    #
    # Two bounds, and the tighter one is FacetUI's own. A glyph that fits
    # Android's mask can still run off the flat table and across the facets,
    # which is a design fault rather than a clipping one -- and invisible to a
    # check that only knows about the mask.
    print("\nglyph bounds")
    safe_r = SAFE_DIAMETER / 2.0
    centre = ADAPTIVE_SIZE / 2.0

    gen = load_generator(args.pack)
    table_r = gen.table_radius() if gen else None
    if gen is None:
        c.warn("generator not found beside the pack; checking the mask safe "
               "zone only, NOT the table")

    worst_mask = None
    worst_table = None
    over_table = []
    checked = 0
    for p in sorted(xmls):
        if os.sep + "drawable" not in p or "facetui_tile" in p:
            continue
        root = ET.parse(p).getroot()
        if root.tag != "vector":
            continue
        group = root.find("group")
        if group is None:
            continue
        scale = float(group.get(f"{ANDROID}scaleX", "1"))
        pivot = float(group.get(f"{ANDROID}pivotX", "0"))
        tx = float(group.get(f"{ANDROID}translateX", "0"))
        name = os.path.basename(p)

        glyph_mask = 0.0
        glyph_table = 0.0
        for path in group.findall("path"):
            data = path.get(f"{ANDROID}pathData") or ""
            # Flatten curves and arcs where possible. Reading anchor points
            # alone under-reports a glyph whose widest part is mid-curve, which
            # is exactly the artwork most likely to be the problem.
            if gen is not None:
                pts = [pt for sub in gen._subpaths(data) for pt in gen._flatten(sub)]
            else:
                pts = path_points(data)
            for x, y in pts:
                gx = (x - pivot) * scale + pivot + tx
                gy = (y - pivot) * scale + pivot + tx
                glyph_mask = max(glyph_mask, math.hypot(gx - centre, gy - centre))
                glyph_table = max(glyph_table, octagon_distance(gx, gy))

        if worst_mask is None or glyph_mask > worst_mask[0]:
            worst_mask = (glyph_mask, name)
        if worst_table is None or glyph_table > worst_table[0]:
            worst_table = (glyph_table, name)
        if table_r is not None and glyph_table > table_r:
            over_table.append((glyph_table, name))
        checked += 1

    if worst_mask is None:
        c.warn("no glyph vectors found to check")
    else:
        if worst_mask[0] > safe_r:
            c.fail(f"{worst_mask[1]} reaches {worst_mask[0]:.1f} from centre, "
                   f"outside the {safe_r:.0f}-unit mask safe zone -- it will "
                   f"be clipped")
        else:
            c.ok(f"mask safe zone: {checked} glyphs, furthest "
                 f"{worst_mask[0]:.1f} of {safe_r:.0f} ({worst_mask[1]})")

        if table_r is not None:
            if over_table:
                for d, n in sorted(over_table, reverse=True):
                    c.fail(f"{n} reaches {d:.1f} against a table edge of "
                           f"{table_r:.1f} -- the glyph runs off the calm "
                           f"centre and across the facets")
            else:
                c.ok(f"table: furthest {worst_table[0]:.1f} of {table_r:.1f} "
                     f"({worst_table[1]})")

    # --- 6. orphans ---------------------------------------------------------
    print("\norphans")
    referenced = {d for _, d in entries} | layer_refs | {"facetui_tile"}
    orphans = sorted(set(drawables) - referenced)
    if orphans:
        c.warn(f"not referenced by anything: {', '.join(orphans)}")
    else:
        c.ok("every drawable in the pack is referenced")

    n_icons = len({d for _, d in entries})
    print(f"\n{len(entries)} components mapped to {n_icons} curated icons; "
          f"everything else is themed procedurally")
    print("FAILED" if c.failed else
          ("PASSED with warnings" if c.warned else "PASSED"))
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main())
