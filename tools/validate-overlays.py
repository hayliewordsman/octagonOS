#!/usr/bin/env python3
"""
Validate the FacetUI RRO overlays against the source trees they target.

    tools/validate-overlays.py --systemui ~/fwb24 --launcher ~/launcher3 \
                               --ime ~/latinime

An RRO that names a resource the target does not define is not an error at
build time and not an error at runtime -- aapt2 links it, the overlay installs,
and the resource is simply never applied. The effect just does not appear, with
nothing in the logs. That failure mode is why this exists.

Checks, per overlay:

  1. the XML is well-formed
  2. every resource it overrides exists in the target tree
  3. the value it overrides differs from stock (an override equal to stock is
     dead weight, and usually means the stock value moved)

Resources the overlay deliberately introduces rather than overrides -- ones a
FacetUI patch adds -- are declared in PATCH_PROVIDED and exempted from (2).

Exits non-zero if any resource is missing. Stdlib only.
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

#: Resources introduced by a FacetUI patch rather than present in stock. These
#: are absent from an unpatched tree by design: the overlay carries them so one
#: overlay serves both a Tier 2 and a Tier 3 image.
PATCH_PROVIDED = {
    "facetui_status_bar_notification_icon_mode": "patches/systemui/0003",
    "facetui_keyboard_blur_radius": "patches/ime/0001",
}

#: overlay directory -> (target tree argument, list of res dirs to scan)
OVERLAYS = {
    "FacetUISystemUI": ("systemui", ["packages/SystemUI/res"]),
    "FacetUIFramework": ("systemui", ["core/res/res"]),
    "FacetUILauncher": ("launcher", ["res"]),
    "FacetUIIME": ("ime", ["java/res"]),
}

VALUE_TAGS = {"bool", "color", "dimen", "integer", "string", "item",
              "integer-array", "string-array", "array", "fraction"}


def parse_values(path):
    """{name: (tag, text)} for every value resource in an XML file."""
    out = {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError(f"{path}: malformed XML: {e}")
    for el in root:
        if el.tag not in VALUE_TAGS:
            continue
        name = el.get("name")
        if not name:
            continue
        text = (el.text or "").strip()
        out[name] = (el.tag, text)
    return out


def scan_tree(root, res_dirs):
    """Every value resource defined anywhere under the given res dirs.

    Keyed by (qualifier, name) where qualifier is the values-* directory, so
    values/ and values-night/ do not collide -- a night-only override must be
    checked against the night-qualified stock value, not the default one.
    """
    found = {}
    for rd in res_dirs:
        base = os.path.join(root, rd)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            qualifier = os.path.basename(dirpath)
            if not qualifier.startswith("values"):
                continue
            for fn in filenames:
                if not fn.endswith(".xml"):
                    continue
                try:
                    for name, val in parse_values(os.path.join(dirpath, fn)).items():
                        found.setdefault((qualifier, name), val)
                except ValueError as e:
                    print(f"  warn  could not parse target file: {e}")
    return found


def main():
    ap = argparse.ArgumentParser(description="Validate FacetUI overlays.")
    ap.add_argument("--overlay-root", default="overlay")
    ap.add_argument("--systemui", help="path to a frameworks/base checkout")
    ap.add_argument("--launcher", help="path to a Launcher3 checkout")
    ap.add_argument("--ime", help="path to a LatinIME checkout")
    ap.add_argument("--strict-redundant", action="store_true",
                    help="treat an override equal to stock as a failure")
    args = ap.parse_args()

    trees = {"systemui": args.systemui, "launcher": args.launcher, "ime": args.ime}
    failed = 0
    checked = 0
    skipped = []

    for overlay, (tree_key, res_dirs) in sorted(OVERLAYS.items()):
        odir = os.path.join(args.overlay_root, overlay)
        if not os.path.isdir(odir):
            continue
        print(f"\n{overlay}")

        # (1) well-formedness, always, even with no target tree available.
        declared = {}
        for dirpath, _, filenames in os.walk(os.path.join(odir, "res")):
            qualifier = os.path.basename(dirpath)
            for fn in sorted(filenames):
                if not fn.endswith(".xml"):
                    continue
                try:
                    for name, val in parse_values(os.path.join(dirpath, fn)).items():
                        declared[(qualifier, name)] = val
                except ValueError as e:
                    print(f"  FAIL  {e}")
                    failed += 1
        manifest = os.path.join(odir, "AndroidManifest.xml")
        try:
            ET.parse(manifest)
            print(f"  ok    manifest and {len(declared)} resources are well-formed")
        except (ET.ParseError, FileNotFoundError) as e:
            print(f"  FAIL  {manifest}: {e}")
            failed += 1

        tree = trees.get(tree_key)
        if not tree:
            skipped.append(f"{overlay} (pass --{tree_key} to check its resources)")
            continue
        if not os.path.isdir(tree):
            print(f"  FAIL  target tree not found: {tree}")
            failed += 1
            continue

        stock = scan_tree(tree, res_dirs)
        missing, redundant, provided = [], [], []
        for (qualifier, name), (tag, value) in sorted(declared.items()):
            checked += 1
            if name in PATCH_PROVIDED:
                provided.append((name, PATCH_PROVIDED[name]))
                continue
            # A night-qualified override may legitimately rely on the default
            # values/ definition existing, so accept either.
            hit = stock.get((qualifier, name)) or stock.get(("values", name))
            if hit is None:
                missing.append((qualifier, name))
            elif hit[1] == value:
                redundant.append((name, value))

        if missing:
            for qualifier, name in missing:
                print(f"  FAIL  {name} ({qualifier}) is not defined in the target -- "
                      f"this override will silently do nothing")
            failed += len(missing)
        else:
            print(f"  ok    all {len(declared) - len(provided)} overridden "
                  f"resources exist in the target")

        for name, where in provided:
            print(f"  ok    {name} is provided by {where}, not stock -- exempt")

        for name, value in redundant:
            msg = (f"{name} is already {value} in stock; the override is dead "
                   f"weight, or stock moved")
            if args.strict_redundant:
                print(f"  FAIL  {msg}")
                failed += 1
            else:
                print(f"  warn  {msg}")

    print()
    for s in skipped:
        print(f"skipped: {s}")
    print(f"\n{checked} resources checked")
    print("FAILED" if failed else "PASSED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
