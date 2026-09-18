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
  2. every resource it overrides exists in the target tree -- values, styles
     and drawables alike
  3. the value it overrides differs from stock (an override equal to stock is
     dead weight, and usually means the stock value moved)
  4. every overridden STYLE restates every item the stock style declares, and
     keeps its parent
  5. no override replaces a wallpaper-derived colour with a fixed literal

Check 5 exists because this repository got it wrong. The first Settings overlay
replaced @android:color/system_neutral1_100 and friends with hex, which pinned
the app to one blue and broke its colour following on every other wallpaper -
the exact opposite of FacetUI's own rule, which is to pull a surface's tint FROM
the system accent rather than flatten it. The FacetUI move is neutral-to-ACCENT,
not dynamic-to-fixed.

It is a shallow check: it compares the immediate stock value, so it sees
@android:color/system_* and not a reference that resolves to one indirectly.
That catches the common case and is honest about the rest.

Check 4 exists because an RRO replaces a style WHOLESALE. A style is a bag of
attributes, and the overlay's bag replaces the target's rather than merging
into it, so any item the original declared and the override forgets is simply
gone at runtime -- with the app rendering subtly wrong and nothing logged.

Whether every Android version merges or replaces is not worth betting a system
theme on: restating is correct under either behaviour, harmless if it merges
and essential if it does not. So this enforces restating.

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
    "facetui_popup_blur_radius": "patches/framework/0001",
    "facetui_solidify_when_no_blur": "patches/framework/0002",
}

#: Resources where overriding a dynamic colour with a fixed literal is a
#: deliberate, documented trade-off rather than a mistake. Everything else that
#: does it fails check 5.
#:
#: The only reason to be on this list is that resource XML cannot apply alpha
#: to a colour REFERENCE - only to a literal - so any surface that has to be
#: translucent must give up dynamic colour to get there.
LITERAL_INTENTIONAL = {
    "keyboard_background_you":
        "the keyboard must be translucent for the blur behind it to show, and "
        "alpha cannot be applied to a colour reference. See "
        "overlay/FacetUIIME/res/values/colors.xml",
    "emoji_tab_page_indicator_background_you":
        "same window as the keyboard; an opaque slab beside a translucent one "
        "would read as a seam",
}

#: overlay directory -> list of (target tree argument, res dirs to scan).
#:
#: A list, because an APK's resource table is not always one repository. A
#: statically linked library's resources are compiled into the app that links
#: it and become overridable entries of THAT package, so an overlay targeting
#: com.android.settings can legitimately name a resource that only exists in
#: SettingsLib, which lives in frameworks/base. Checking the app's own res
#: alone would report those as missing and be wrong.
OVERLAYS = {
    "FacetUISystemUI": [("systemui", ["packages/SystemUI/res"])],
    "FacetUIFramework": [("systemui", ["core/res/res"])],
    "FacetUILauncher": [("launcher", ["res"])],
    "FacetUIIME": [("ime", ["java/res"])],
    "FacetUISettings": [
        ("settings", ["res"]),
        ("systemui", ["packages/SettingsLib"]),
    ],
    "FacetUIDocumentsUI": [("apps", ["DocumentsUI/res"])],
    "FacetUIEtar": [("apps", ["Etar/app/src/main/res"])],
    "FacetUIDeskClock": [("apps", ["DeskClock/res"])],
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


def normalise_parent(parent):
    """A style parent, stripped to the name both sides can be compared on.

    The target declares a framework parent by bare name, because it IS the
    framework: `parent="Theme.Material.BaseDialog"`. An overlay is a different
    package, so the same parent has to be written
    `@*android:style/Theme.Material.BaseDialog` -- the star because the style is
    not in public-final.xml, and a namespace because a bare name would resolve
    against the overlay's own package and fail to link.

    Both spellings mean the same style. Comparing them literally reported a
    correctly-qualified overlay as moving the style in the hierarchy, which is
    the opposite of true.
    """
    if not parent:
        return None
    for prefix in ("@*android:style/", "@android:style/", "@*style/", "@style/"):
        if parent.startswith(prefix):
            return parent[len(prefix):]
    return parent


def parse_styles(path):
    """{name: (parent, {item names})} for every <style> in an XML file.

    `parent` is the explicit parent attribute, or None when the style relies on
    dot-notation to infer one. The two are not interchangeable: writing an
    explicit parent onto a style that had an implicit one, or the reverse, can
    silently move it in the hierarchy.
    """
    out = {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError(f"{path}: malformed XML: {e}")
    for el in root:
        if el.tag != "style":
            continue
        name = el.get("name")
        if not name:
            continue
        items = {i.get("name") for i in el.findall("item") if i.get("name")}
        out[name] = (el.get("parent"), items)
    return out


def scan_styles(root, res_dirs):
    """Every <style> defined anywhere under the given res dirs."""
    found = {}
    for rd in res_dirs:
        base = os.path.join(root, rd)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            if not os.path.basename(dirpath).startswith("values"):
                continue
            for fn in filenames:
                if not fn.endswith(".xml"):
                    continue
                try:
                    for name, val in parse_styles(os.path.join(dirpath, fn)).items():
                        found.setdefault(name, val)
                except ValueError:
                    pass
    return found


def scan_drawables(root, res_dirs):
    """Names of every drawable and mipmap resource under the given res dirs."""
    found = set()
    for rd in res_dirs:
        base = os.path.join(root, rd)
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            kind = entry.split("-", 1)[0]
            if kind not in ("drawable", "mipmap"):
                continue
            d = os.path.join(base, entry)
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                found.add(os.path.splitext(fn)[0])
    return found


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
    ap.add_argument("--settings", help="path to a Settings checkout")
    ap.add_argument("--apps", help="directory holding the per-app checkouts")
    ap.add_argument("--strict-redundant", action="store_true",
                    help="treat an override equal to stock as a failure")
    args = ap.parse_args()

    trees = {"systemui": args.systemui, "launcher": args.launcher,
             "ime": args.ime, "settings": args.settings, "apps": args.apps}
    failed = 0
    checked = 0
    skipped = []

    for overlay, sources in sorted(OVERLAYS.items()):
        odir = os.path.join(args.overlay_root, overlay)
        if not os.path.isdir(odir):
            continue
        print(f"\n{overlay}")

        # (1) well-formedness, always, even with no target tree available.
        declared = {}
        styles = {}
        drawables = {}
        for dirpath, _, filenames in os.walk(os.path.join(odir, "res")):
            qualifier = os.path.basename(dirpath)
            kind = qualifier.split("-", 1)[0]
            for fn in sorted(filenames):
                path = os.path.join(dirpath, fn)
                # A drawable or mipmap is a whole file, not an entry in one.
                if kind in ("drawable", "mipmap"):
                    drawables[os.path.splitext(fn)[0]] = os.path.relpath(path, odir)
                    if fn.endswith(".xml"):
                        try:
                            ET.parse(path)
                        except ET.ParseError as e:
                            print(f"  FAIL  {path}: malformed XML: {e}")
                            failed += 1
                    continue
                if not fn.endswith(".xml"):
                    continue
                try:
                    for name, val in parse_values(path).items():
                        declared[(qualifier, name)] = val
                    for name, val in parse_styles(path).items():
                        styles[name] = val
                except ValueError as e:
                    print(f"  FAIL  {e}")
                    failed += 1
        manifest = os.path.join(odir, "AndroidManifest.xml")
        try:
            ET.parse(manifest)
            print(f"  ok    manifest and {len(declared)} values, {len(styles)} "
                  f"styles, {len(drawables)} drawables are well-formed")
        except (ET.ParseError, FileNotFoundError) as e:
            print(f"  FAIL  {manifest}: {e}")
            failed += 1

        resolved = []
        missing_tree = None
        for tree_key, res_dirs in sources:
            tree = trees.get(tree_key)
            if not tree:
                missing_tree = tree_key
                break
            if not os.path.isdir(tree):
                print(f"  FAIL  target tree not found: {tree}")
                failed += 1
                missing_tree = tree_key
                break
            resolved.append((tree, res_dirs))
        if missing_tree is not None:
            if trees.get(missing_tree) is None:
                skipped.append(
                    f"{overlay} (pass --{missing_tree} to check its resources)")
            continue

        stock = {}
        for tree, res_dirs in resolved:
            for k, v in scan_tree(tree, res_dirs).items():
                stock.setdefault(k, v)

        # Whether a resource EXISTS does not depend on qualifiers: one name is
        # one resource ID, however many configurations define values for it.
        # SettingsLib, for instance, declares its surface colours only under
        # values-v31 and values-v36, and an overlay quite correctly declares
        # them under plain values and values-night. Matching qualifiers for the
        # existence check reported every one of those as missing.
        stock_names = {name for _, name in stock}

        # Every value stock gives a name, across all qualifiers. The dynamic
        # check needs this for the same reason the existence check does: a
        # resource defined only under values-v31 is not findable at ("values",
        # name), and looking for it there is how the first version of the
        # dynamic check managed to pass on the very mistake it was written to
        # catch.
        stock_values_by_name = {}
        for (_, name), (_, value) in stock.items():
            stock_values_by_name.setdefault(name, set()).add(value)
        missing, redundant, provided = [], [], []
        for (qualifier, name), (tag, value) in sorted(declared.items()):
            checked += 1
            if name in PATCH_PROVIDED:
                provided.append((name, PATCH_PROVIDED[name]))
                continue
            if name not in stock_names:
                missing.append((qualifier, name))
                continue
            # Redundancy, unlike existence, IS qualifier-sensitive: an override
            # only duplicates stock if it duplicates what stock resolves to in
            # the SAME configuration. A night override that matches the light
            # default is not redundant, it is a real change.
            #
            # Matching was previously exact -- ("values", name) or nothing --
            # which silently skipped every resource stock defines only under a
            # version qualifier. SettingsLib declares its surface colours under
            # values-v31 and values-v36, so none of those overrides were ever
            # checked for redundancy at all.
            #
            # Now: night matches night, default matches default, and version
            # qualifiers on the stock side are accepted for either, since an
            # unqualified override applies at every API level.
            hit = None
            want_night = "night" in qualifier
            for (q, n), v in stock.items():
                if n != name or ("night" in q) != want_night:
                    continue
                # Prefer an exact qualifier match, else take any that agrees on
                # night-ness -- values-v31 and values-v36 both count.
                if q == qualifier:
                    hit = v
                    break
                if hit is None:
                    hit = v
            if hit is not None and hit[1] == value:
                redundant.append((name, value))

        # (5) dynamic colour must survive.
        flattened = []
        for (qualifier, name), (tag, value) in sorted(declared.items()):
            if tag != "color" or not value.startswith("#"):
                continue
            if name in LITERAL_INTENTIONAL:
                continue
            dynamic = [v for v in stock_values_by_name.get(name, ())
                       if re.match(r"@\*?android:color/system_", v)]
            if dynamic:
                flattened.append((name, sorted(dynamic)[0], value))
        if flattened:
            for name, was, now in flattened:
                print(f"  FAIL  {name} replaces the wallpaper-derived {was} "
                      f"with the fixed literal {now} -- this surface stops "
                      f"following the system palette. Use an accent ramp "
                      f"reference, or add it to LITERAL_INTENTIONAL with a "
                      f"reason")
            failed += len(flattened)

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

        # (2b) drawables. A drawable override is a whole file replacing a whole
        # file, so the only way to get it wrong is to name one the target does
        # not have -- in which case it is simply dead weight in the APK.
        if drawables:
            stock_drawables = set()
            for tree, res_dirs in resolved:
                stock_drawables |= scan_drawables(tree, res_dirs)
            absent = sorted(n for n in drawables if n not in stock_drawables)
            checked += len(drawables)
            if absent:
                for n in absent:
                    print(f"  FAIL  drawable {n} ({drawables[n]}) does not exist "
                          f"in the target -- nothing will use it")
                failed += len(absent)
            else:
                print(f"  ok    all {len(drawables)} overridden drawables exist "
                      f"in the target")

        # (4) styles. This is the one that can break things silently, because
        # the overlay's bag replaces the target's rather than merging into it.
        if styles:
            stock_styles = {}
            for tree, res_dirs in resolved:
                for k, v in scan_styles(tree, res_dirs).items():
                    stock_styles.setdefault(k, v)
            style_failed = 0
            for name, (parent, items) in sorted(styles.items()):
                checked += 1
                hit = stock_styles.get(name)
                if hit is None:
                    print(f"  FAIL  style {name} is not defined in the target -- "
                          f"this override will silently do nothing")
                    style_failed += 1
                    continue
                stock_parent, stock_items = hit

                if normalise_parent(parent) != normalise_parent(stock_parent):
                    print(f"  FAIL  style {name} declares parent "
                          f"{parent!r} but stock has {stock_parent!r} -- "
                          f"the override moves it in the hierarchy")
                    style_failed += 1

                dropped = sorted(stock_items - items)
                if dropped:
                    print(f"  FAIL  style {name} does not restate "
                          f"{len(dropped)} item(s) stock declares: "
                          f"{', '.join(dropped)}. An RRO replaces a style "
                          f"wholesale, so these would be lost at runtime")
                    style_failed += 1

            failed += style_failed
            if not style_failed:
                total_items = sum(len(v[1]) for v in styles.values())
                print(f"  ok    all {len(styles)} overridden styles keep their "
                      f"parent and restate every stock item "
                      f"({total_items} items declared)")

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
