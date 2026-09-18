#!/usr/bin/env python3
"""
Check the FacetUI icon theme without a toolkit.

    desktop/tools/verify-icon-theme.py [theme-dir]

The running check, `desktop/tools/run-icon-theme.sh`, asks Qt and GTK to
resolve every icon and compares what comes back against the files on disk.
Where it can run it settles more than this does. This is the fast version, and
it carries one check a toolkit cannot make: whether a GLYPH STILL FITS THE
GLASS.

That is the check the Android pack learned the hard way. Fifteen of its
twenty-five glyphs used to run over the table's edge and onto the faceted
crown, and every other check stayed green, because a glyph that overhangs is
not an error to anything -- it is just harder to read.

Requires NumPy, Pillow and cairosvg (the same as the generator).
"""

import argparse
import configparser
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "desktop" / "icons"))

fails = []


def fail(msg):
    fails.append(msg)


def load_generator():
    """The generator module, so its arithmetic is used rather than copied.

    A second implementation of the glyph scale here would be free to drift away
    from the one that draws the icons, and then this would be checking
    something nothing ships.
    """
    import importlib.util
    path = ROOT / "desktop" / "icons" / "make-icon-theme.py"
    spec = importlib.util.spec_from_file_location("_facetui_icons", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="Check the FacetUI icon theme.")
    ap.add_argument("theme", nargs="?",
                    default=str(ROOT / "desktop" / "icons" / "FacetUI"))
    args = ap.parse_args()

    theme = pathlib.Path(args.theme).resolve()
    if not theme.is_dir():
        print(f"[FAIL] no such theme: {theme}")
        return 2

    index = theme / "index.theme"
    if not index.exists():
        print("[FAIL] no index.theme; nothing will find this theme at all")
        return 1

    cp = configparser.ConfigParser(strict=False)
    cp.optionxform = str
    try:
        cp.read_string(index.read_text())
    except configparser.Error as exc:
        print(f"[FAIL] index.theme does not parse -- {exc}")
        return 1

    if "Icon Theme" not in cp:
        fail("index.theme has no [Icon Theme] section")
        print(f"[FAIL] {fails[0]}")
        return 1

    head = cp["Icon Theme"]
    for key in ("Name", "Directories"):
        if key not in head:
            fail(f"index.theme has no {key}")

    # Inherits is what makes a partial theme usable. Without it, every icon the
    # theme does not define is simply absent, which on a desktop means most of
    # them.
    inherits = head.get("Inherits", "")
    if not inherits:
        fail("index.theme has no Inherits, so every icon this theme does not "
             "define would be missing rather than falling back")
    elif not inherits.split(",")[-1].strip() == "hicolor":
        fail(f"Inherits is {inherits!r}; the spec wants hicolor reachable as "
             f"the last resort")

    listed = [d.strip() for d in head.get("Directories", "").split(",") if d.strip()]
    if not listed:
        fail("index.theme lists no Directories")

    declared = {}
    for d in listed:
        if d not in cp:
            fail(f"directory {d} is listed in Directories but has no section")
            continue
        sec = cp[d]
        if "Size" not in sec:
            fail(f"[{d}] has no Size")
            continue
        declared[d] = int(sec["Size"])
        if "Context" not in sec:
            fail(f"[{d}] has no Context")
        if sec.get("Type", "Threshold") not in ("Fixed", "Scalable", "Threshold"):
            fail(f"[{d}] has an unknown Type {sec.get('Type')!r}")
        if not (theme / d).is_dir():
            fail(f"[{d}] is listed but the directory does not exist; every "
                 f"lookup in it silently falls through to an inherited theme")

    # A directory on disk that nothing lists is dead weight that looks live.
    on_disk = {str(p.relative_to(theme)) for p in theme.rglob("*")
               if p.is_dir() and any(c.suffix == ".png" for c in p.iterdir())}
    for d in sorted(on_disk - set(listed)):
        fail(f"{d} holds icons but is not in Directories, so nothing will "
             f"look in it")

    # Declared size against actual pixels. A mismatch is not an error to
    # anything: the toolkit picks some other directory and the theme quietly
    # renders at the wrong scale.
    try:
        from PIL import Image
    except ImportError:
        print("[FAIL] Pillow is needed to check icon sizes")
        return 2

    names_by_dir = {}
    for d, size in declared.items():
        folder = theme / d
        if not folder.is_dir():
            continue
        names = set()
        for png in sorted(folder.glob("*.png")):
            names.add(png.stem)
            with Image.open(png) as im:
                if im.size != (size, size):
                    fail(f"{d}/{png.name} is {im.size[0]}x{im.size[1]} but "
                         f"[{d}] declares Size={size}")
                    break
        names_by_dir[d] = names

    # Every name at every size, or a lookup at one size falls through while its
    # neighbours do not -- one icon in a toolbar from another theme.
    if names_by_dir:
        union = set().union(*names_by_dir.values())
        for d, names in sorted(names_by_dir.items()):
            missing = union - names
            if missing:
                fail(f"{d} is missing {len(missing)} icon(s) the other sizes "
                     f"have (e.g. {sorted(missing)[0]})")

    # THE ONE A TOOLKIT CANNOT MAKE: does the glyph still fit the glass?
    #
    # Measured on the SHIPPED PIXELS, by rendering the bare tile at the same
    # size and subtracting it. The first version of this check recomputed the
    # generator's own arithmetic instead, and was worthless: the scale is
    # DERIVED from the widest glyph, so the widest glyph always lands exactly
    # at the clearance and the comparison could never fail. It passed on every
    # input, including ones it was written to reject.
    #
    # What can still go wrong is real: a clearance set too loose, a tile whose
    # apothem changed without the glyph scale following, a glyph added that
    # renders wider than its path suggests.
    try:
        import numpy as np
        gen = load_generator()
        size = max(declared.values()) if declared else 128
        folder = next(d for d, v in declared.items() if v == size)
        apothem = size * gen.APOTHEM_FRAC
        table = gen.table_radius(apothem)

        bare = np.asarray(gen.render_tile(size, apothem,
                                          seam_scale=apothem / 36.0)).astype(int)
        ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
        c = size / 2.0
        dist = np.maximum.reduce([
            (xs - c) * np.cos(k * 2.0 * np.pi / 8)
            + (ys - c) * np.sin(k * 2.0 * np.pi / 8) for k in range(8)])

        worst_name, worst_reach = None, 0.0
        for png in sorted((theme / folder).glob("*.png")):
            icon = np.asarray(Image.open(png).convert("RGBA")).astype(int)
            # Where the icon differs from the bare tile, a glyph was drawn.
            delta = np.abs(icon - bare).sum(axis=2)
            glyph = delta > 40
            if not glyph.any():
                fail(f"{folder}/{png.name} is identical to the bare tile -- "
                     f"no glyph was drawn on it")
                continue
            reach = float(dist[glyph].max())
            if reach > worst_reach:
                worst_reach, worst_name = reach, png.stem

        if worst_name is None:
            fail("no icons could be measured against the table")
        elif worst_reach > table:
            fail(f"{worst_name} reaches {worst_reach:.1f} from centre, past "
                 f"the table's edge at {table:.1f}. It sits across the "
                 f"faceted crown, where eight facets' worth of value "
                 f"variation runs under it -- which is exactly what the "
                 f"Android pack shipped until it was measured")
        else:
            print(f"[ok]   glyphs fit the glass: widest is {worst_name} at "
                  f"{worst_reach:.1f} against a table edge of {table:.1f} "
                  f"({worst_reach / table:.3f} of it), measured on the "
                  f"{size}px icons")
    except Exception as exc:                              # noqa: BLE001
        fail(f"could not measure the glyphs against the table: {exc}")

    # Does each name carry the glyph it was mapped to?
    #
    # Nothing above asks this. The running pass proves Qt used OUR file; it
    # cannot know whether our file holds the right artwork, because both sides
    # of its comparison are that file. But the generator maps many names onto
    # few glyphs, and that is a checkable shape: two names sharing a glyph must
    # render identically, and two names with different glyphs must not.
    try:
        import numpy as np
        gen = load_generator()
        size = max(declared.values()) if declared else 128
        folder = next(d for d, v in declared.items() if v == size)

        by_glyph = {}
        for glyph, aliases in gen.NAMES.items():
            for alias in aliases:
                by_glyph.setdefault(glyph, []).append(alias)

        signature = {}
        for glyph, aliases in sorted(by_glyph.items()):
            first = None
            for alias in aliases:
                png = theme / folder / f"{alias}.png"
                if not png.exists():
                    fail(f"{folder}/{alias}.png is missing; the generator maps "
                         f"it to the {glyph} glyph")
                    continue
                arr = np.asarray(Image.open(png).convert("RGBA")).astype(int)
                if first is None:
                    first = arr
                    signature[glyph] = arr
                elif not np.array_equal(arr, first):
                    fail(f"{alias} and {aliases[0]} are both mapped to the "
                         f"{glyph} glyph but render differently")

        pairs = sorted(signature)
        for i, a in enumerate(pairs):
            for b in pairs[i + 1:]:
                if np.array_equal(signature[a], signature[b]):
                    fail(f"the {a} and {b} glyphs render identically, so one "
                         f"of them is not drawing what it should")
        if not fails:
            print(f"[ok]   {sum(len(v) for v in by_glyph.values())} names carry "
                  f"{len(by_glyph)} distinct glyphs, each name matching the "
                  f"others mapped to it")
    except Exception as exc:                              # noqa: BLE001
        fail(f"could not check names against glyphs: {exc}")

    for m in fails:
        print(f"[FAIL] {m}")
    if fails:
        print(f"\nFAILED: {len(fails)} problem(s) in {theme}")
        return 1
    total = sum(len(n) for n in names_by_dir.values())
    print(f"[ok] {theme}: {total} icons, {len(declared)} sizes, inherits "
          f"{inherits}")
    print("     Static only. It does not ask a toolkit to resolve anything --")
    print("     see desktop/tools/run-icon-theme.sh, which does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
