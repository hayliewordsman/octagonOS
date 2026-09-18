#!/usr/bin/env python3
"""
Compile the FacetUI AGSL, and check everything that claims to mirror it.

    pip install skia-python     # needs libegl1 libgl1 on Linux
    tools/validate-shaders.py

The shaders are the riskiest thing in this repository. They are strings,
compiled at runtime by Skia, so a mistake in them is not a build error -- it is
a blank surface or a crash on the first frame of a ROM that took hours to
build. Nothing else here fails that late.

Three checks:

  1. both shaders compile, using Skia's own SkSL compiler
  2. the compiler is actually rejecting things, proven on five broken shaders,
     so that check 1 means something
  3. everything that claims to mirror the AGSL still does -- the NumPy
     transcription the generators render from, and the parameter values spread
     across the shader defaults, ScrimView and both generators

Check 3 exists because this repository repeatedly says the boot screen, the
shade and the app icons are lit by the same maths, and until now nothing
enforced it. A constant edited in one place and not the others would have kept
every other check green.

AGSL is Android's binding of Skia runtime effects, so Skia rejects most of what
Android would. It is not the same compiler as any given Android release, so a
pass here is strong evidence, not proof. The on-device harness in
titan2e-eos/tools/shader-check settles it; this is what can be run without an
SDK, an emulator or a device.

Adapted from titan2e-eos/tools/shader-check/validate-sksl.py, which established
this approach.
"""

import pathlib
import re
import sys

#: mobile/, which is where the patches live.
ROOT = pathlib.Path(__file__).resolve().parents[1]
#: shared/, which is where the maths and the palette live. The FacetUI core is
#: shared with the desktop edition, so it sits outside this platform's tree.
SHARED = ROOT.parent / "shared" / "facetui"

#: The AGSL lives in the patches, since that is the only copy that ships.
SHADERS = {
    "FacetEdgeShader": "patches/systemui/0001-facetui-specular-edge.patch",
    "FacetRimShader": "patches/systemui/0002-facetui-rim-darkening.patch",
}

#: Shaders that must be rejected. If any of these compiles, check 1 is
#: meaningless and this tool is lying.
MUST_REJECT = {
    "undeclared variable": "vec4 main(vec2 p){ return vec4(nope, 0, 0, 1); }",
    "type mismatch": "vec4 main(vec2 p){ float x = vec3(1.0); return vec4(x); }",
    "missing main": "uniform float a; vec4 notmain(vec2 p){ return vec4(1); }",
    "syntax error": "vec4 main(vec2 p) { return vec4(1.0 ; }",
    "wrong main signature": "float main(vec2 p){ return 1.0; }",
}
MUST_ACCEPT = "vec4 main(vec2 p){ return vec4(p.x, p.y, 0.0, 1.0); }"


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


def added_lines(path):
    """The lines a patch adds, without the leading '+'."""
    return "\n".join(
        l[1:] for l in path.read_text().splitlines()
        if l.startswith("+") and not l.startswith("+++")
    )


def agsl_from_patch(path):
    """UNIFORMS + MAIN, as the Kotlin concatenates them into the shader."""
    added = added_lines(path)
    parts = []
    for block in ("UNIFORMS", "MAIN"):
        m = re.search(block + r'\s*=\s*"""(.*?)"""', added, re.S)
        if not m:
            return None
        parts.append(m.group(1))
    return "".join(parts)


def compile_sksl(src):
    """None if it compiles, else the compiler's complaint."""
    import skia
    fn = getattr(skia.RuntimeEffect, "MakeForShader", None) \
        or getattr(skia.RuntimeEffect, "Make", None)
    if fn is None:
        return "no usable RuntimeEffect entry point in skia-python"
    try:
        r = fn(src)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    if isinstance(r, tuple):
        effect, err = (r + (None,))[:2]
        return None if effect is not None else (err or "rejected, no message")
    return None if r is not None else "rejected, no message"


def find_float(text, pattern, label, c):
    """The single float a pattern captures, or None with a failure logged."""
    m = re.search(pattern, text)
    if not m:
        c.fail(f"could not find {label} -- this check has gone stale and is "
               f"no longer verifying anything")
        return None
    return float(m.group(1))


def main():
    c = Checker()

    # --- 1 & 2. the compiler, and whether it is awake -----------------------
    print("SkSL compiler")
    try:
        import skia  # noqa: F401
    except ImportError as e:
        print(f"  FAIL  skia-python is not usable: {e}")
        print("        pip install skia-python, and on Linux the system needs")
        print("        libegl1 and libgl1 for it to import at all")
        print("\nFAILED")
        return 1

    accepted_bad = [name for name, src in MUST_REJECT.items()
                    if compile_sksl(src) is None]
    if accepted_bad:
        c.fail(f"the compiler accepted invalid shaders ({', '.join(accepted_bad)}) "
               f"-- every other result from it is worthless")
    elif compile_sksl(MUST_ACCEPT) is not None:
        c.fail("the compiler rejected a valid shader; it is not usable here")
    else:
        c.ok(f"rejects all {len(MUST_REJECT)} deliberately broken shaders and "
             f"accepts a valid one")

    # --- 1. the real shaders ------------------------------------------------
    print("\nFacetUI shaders")
    sources = {}
    for name, rel in SHADERS.items():
        path = ROOT / rel
        if not path.exists():
            c.fail(f"{name}: {rel} is missing")
            continue
        src = agsl_from_patch(path)
        if src is None:
            c.fail(f"{name}: could not extract AGSL from {rel}")
            continue
        sources[name] = src
        err = compile_sksl(src)
        if err:
            c.fail(f"{name}: does not compile")
            for line in str(err).strip().splitlines():
                print(f"          {line}")
        else:
            c.ok(f"{name}: compiles ({len(src)} chars of AGSL)")

    # --- 3a. the NumPy transcription ---------------------------------------
    # shared/facetui/facet_math.py names two constants that appear as bare
    # literals inside the AGSL. The generators render from that file, so if the
    # two drift, the boot screen and the icons stop being lit by the maths the
    # shade is lit by -- which this repository claims throughout.
    print("\nfacet_math.py against the AGSL")
    fm = SHARED / "facet_math.py"
    edge = sources.get("FacetEdgeShader")
    if not fm.exists():
        c.fail("shared/facetui/facet_math.py is missing")
    elif edge is None:
        c.warn("edge shader unavailable; cannot compare")
    else:
        text = fm.read_text()
        pairs = [
            # (label, AGSL pattern, python pattern)
            ("falloff",
             r"exp\(-d \* d \* ([0-9.]+)\)",
             r"EDGE_FALLOFF\s*=\s*([0-9.]+)"),
            ("centre bias",
             r"1\.0 - x \* x \* ([0-9.]+)",
             r"EDGE_ARC_BIAS\s*=\s*([0-9.]+)"),
        ]
        for label, agsl_pat, py_pat in pairs:
            a = find_float(edge, agsl_pat, f"{label} in the AGSL", c)
            p = find_float(text, py_pat, f"{label} in facet_math.py", c)
            if a is None or p is None:
                continue
            if abs(a - p) > 1e-9:
                c.fail(f"{label}: AGSL uses {a}, facet_math.py uses {p} -- the "
                       f"transcription has drifted from the shader")
            else:
                c.ok(f"{label}: {a} in both")

    # --- 3b. the parameter values, everywhere they are written --------------
    # Fewer copies than there used to be. The two generators shared their
    # constants into shared/facetui/palette.py, so one definition serves both
    # and cannot drift from itself. What remains are the Kotlin and Java copies
    # inside the patches, which genuinely cannot import a Python file, so those
    # are still compared against the shared one.
    print("\nFacetUI parameters, across every copy")
    sites = {
        "rim amount": [
            ("FacetRimShader default", SHADERS["FacetRimShader"],
             r"var amount: Float = ([0-9.]+)f"),
            ("ScrimView", SHADERS["FacetRimShader"],
             r"FACETUI_RIM_AMOUNT = ([0-9.]+)f"),
            ("shared palette", "../shared/facetui/palette.py",
             r"^RIM_AMOUNT = ([0-9.]+)"),
        ],
        "edge intensity": [
            ("FacetEdgeShader default", SHADERS["FacetEdgeShader"],
             r"var intensity: Float = ([0-9.]+)f"),
            ("ScrimView", SHADERS["FacetEdgeShader"],
             r"FACETUI_EDGE_MAX_INTENSITY = ([0-9.]+)f"),
            ("shared palette", "../shared/facetui/palette.py",
             r"^EDGE_INTENSITY = ([0-9.]+)"),
        ],
        "rim width (dp)": [
            ("FacetRimShader default", SHADERS["FacetRimShader"],
             r"var rim: Float = ([0-9.]+)f"),
            ("ScrimView", SHADERS["FacetRimShader"],
             r"FACETUI_RIM_DP = ([0-9.]+)f"),
        ],
        "edge thickness (dp)": [
            ("FacetEdgeShader default", SHADERS["FacetEdgeShader"],
             r"var thickness: Float = ([0-9.]+)f"),
            ("ScrimView", SHADERS["FacetEdgeShader"],
             r"FACETUI_EDGE_THICKNESS_DP = ([0-9.]+)f"),
        ],
    }
    for label, places in sites.items():
        values = {}
        for where, rel, pat in places:
            path = ROOT / rel
            if not path.exists():
                c.fail(f"{label}: {rel} is missing")
                values = None
                break
            body = added_lines(path) if rel.endswith(".patch") else path.read_text()
            m = re.search(pat, body, re.M)
            if not m:
                c.fail(f"{label}: could not read it from {where} ({rel}) -- "
                       f"this check has gone stale")
                values = None
                break
            values[where] = float(m.group(1))
        if not values:
            continue
        distinct = sorted(set(values.values()))
        if len(distinct) > 1:
            detail = ", ".join(f"{w}={v}" for w, v in values.items())
            c.fail(f"{label} disagrees across copies: {detail}")
        else:
            c.ok(f"{label}: {distinct[0]} in all {len(values)} places")

    print()
    print("FAILED" if c.failed else
          ("PASSED with warnings" if c.warned else "PASSED"))
    if not c.failed:
        print("\nSkSL is not AGSL and this is not the Skia in any given Android\n"
              "release. Strong evidence, not proof -- the on-device harness in\n"
              "titan2e-eos/tools/shader-check is what settles it.")
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main())
