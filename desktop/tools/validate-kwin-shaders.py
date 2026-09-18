#!/usr/bin/env python3
"""
Compile the FacetUI GLSL the way KWin compiles it, and check it computes what
the rest of FacetUI computes.

    desktop/tools/validate-kwin-shaders.py

WHY THIS IS THE MOST IMPORTANT CHECK IN desktop/

A compositor shader is a string, compiled at runtime. A mistake in it is not a
build error -- it is a blank panel, or a compositor that refuses to start, on a
machine that has already been installed. Nothing else in this edition fails
that late.

Four checks:

  1. The shader compiles, in a real GLES 3 driver, with the exact preamble
     KWin's GLShader::preprocess prepends. Not a desktop-GL approximation:
     KWin emits "#version 300 es", and a desktop GL context rejects that
     outright, so compiling it there would prove nothing.

  2. The compiler is actually rejecting things, proven on broken shaders, so
     that check 1 means something.

  3. The shader's OUTPUT agrees with shared/facetui/facet_math.py -- the same
     NumPy the boot animation, the icon pack and the Plymouth theme are lit by
     -- evaluated over a grid and compared per pixel.

     This is stronger than the mobile edition's equivalent, which compares the
     AGSL and the NumPy as text. Text comparison catches a renamed constant. It
     does not catch a sign error, a swapped axis, or a transcription that reads
     correctly and computes something else.

  4. The GLSL and the AGSL are still literal transcriptions of each other, so a
     constant changed on one platform and not the other is caught where it
     happened rather than as a numeric drift somewhere downstream.

Needs a GL driver. llvmpipe is fine and is what CI uses -- the shader compiler
is Mesa's either way, and check 3 does not care how fast the pixels arrive.

Requires NumPy, a C compiler, and libEGL/libGLESv2 headers.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
DESKTOP = HERE.parent
ROOT = DESKTOP.parent
SHARED = ROOT / "shared" / "facetui"
SHADER = DESKTOP / "kwin" / "facetui-glass" / "shaders" / "facetui-glass.frag"
#: The AGSL that ships on Android, which this is a transcription of.
AGSL_PATCHES = {
    "edge": ROOT / "mobile" / "patches" / "systemui" / "0001-facetui-specular-edge.patch",
    "rim": ROOT / "mobile" / "patches" / "systemui" / "0002-facetui-rim-darkening.patch",
}

sys.path.insert(0, str(ROOT / "shared"))
from facetui.facet_math import edge_highlight, rim_darkening  # noqa: E402

#: Exactly what KWin 6 prepends. From src/opengl/glshader.cpp, GLShader::preprocess,
#: in the coreShader branch -- which is the only branch that runs on a GLSL
#: version >= 3.0, i.e. everywhere KWin runs today.
KWIN_PREAMBLE = """#version 300 es
precision highp float;
precision highp sampler2D;
precision highp sampler3D;
"""

#: KWin's ShaderManager::listDefines, for the traits the effect asks for.
#: RoundedCorners is what makes base.vert emit position0; the effect wants the
#: varying, not the corner rounding.
KWIN_DEFINES = """#define TRAIT_MAP_TEXTURE 1
#define TRAIT_UNIFORM_COLOR 0
#define TRAIT_MODULATE 0
#define TRAIT_ADJUST_SATURATION 0
#define TRAIT_TRANSFORM_COLORSPACE 0
#define TRAIT_MAP_EXTERNAL_TEXTURE 0
#define TRAIT_MAP_MULTI_PLANE_TEXTURE 0
#define TRAIT_ROUNDED_CORNERS 1
#define TRAIT_BORDER 0
"""

#: KWin resolves #include from its own Qt resources, which are not on disk
#: here. These stand in for them AS IDENTITIES, deliberately: the thing being
#: verified is the FacetUI maths, and running it through a real colour pipeline
#: would mean comparing against a NumPy model of KWin's colour management
#: rather than against FacetUI's. What is NOT verified here is that the
#: pipeline calls are in KWin's order -- check 4 reads them, and only a running
#: compositor settles it.
INCLUDE_STUBS = {
    "colormanagement.glsl": (
        "vec4 sourceEncodingToNitsInDestinationColorspace(vec4 c) { return c; }\n"
        "vec4 nitsToDestinationEncoding(vec4 c) { return c; }\n"
    ),
    "saturation.glsl": "vec4 adjustSaturation(vec4 c) { return c; }\n",
}

#: Shaders that must be rejected. If any compiles, check 1 is meaningless.
MUST_REJECT = {
    "undeclared variable":
        "out vec4 fragColor;\nvoid main(){ fragColor = vec4(nope, 0, 0, 1); }",
    "type mismatch":
        "out vec4 fragColor;\nvoid main(){ float x = vec3(1.0); fragColor = vec4(x); }",
    "missing main":
        "out vec4 fragColor;\nvoid notmain(){ fragColor = vec4(1); }",
    "syntax error":
        "out vec4 fragColor;\nvoid main(){ fragColor = vec4(1.0 ; }",
    "wrong argument count":
        "out vec4 fragColor;\nvoid main(){ fragColor = vec4(clamp(1.0, 0.0)); }",
}

PROBE_SRC = HERE / "glsl-probe.c"

fails = []


def fail(msg):
    fails.append(msg)
    print(f"[FAIL] {msg}")


def ok(msg):
    print(f"[ok]   {msg}")


def build_probe(workdir):
    """Build the GL harness. It is C because KWin uses GLSL ES."""
    exe = workdir / "glsl-probe"
    r = subprocess.run(
        ["cc", "-O2", "-o", str(exe), str(PROBE_SRC), "-lEGL", "-lGLESv2"],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("[FAIL] could not build the GL harness:")
        print(r.stderr.strip()[:2000])
        print("       Needs a C compiler and libEGL/libGLESv2 headers:")
        print("         apt install build-essential libegl1-mesa-dev libgles2-mesa-dev")
        sys.exit(2)
    return exe


def preprocess(source):
    """What KWin hands the driver, for this shader.

    Mirrors GLShader::preprocess: the version line in the file is DROPPED and
    KWin's own preamble is prepended, #include is resolved, and the trait
    defines sit between the two.
    """
    body = []
    for line in source.splitlines():
        if line.startswith("#version"):
            continue                        # intentionally ignored, as KWin does
        m = re.match(r'#include\s+"([^"]+)"', line)
        if m:
            name = m.group(1)
            if name not in INCLUDE_STUBS:
                fail(f'the shader includes "{name}", which this validator has '
                     f'no stand-in for; add one or the compile below is not '
                     f'testing the real source')
                continue
            body.append(INCLUDE_STUBS[name])
            continue
        body.append(line)
    return KWIN_PREAMBLE + KWIN_DEFINES + "\n".join(body) + "\n"


def compile_shader(probe, source, workdir, name="shader"):
    path = workdir / f"{name}.frag"
    path.write_text(source)
    r = subprocess.run([str(probe), "--compile", str(path)],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def evaluate(probe, source, workdir, w, h, uniforms):
    path = workdir / "eval.frag"
    path.write_text(source)
    raw = workdir / "eval.raw"
    args = [str(probe), "--eval", str(path), str(w), str(h), str(raw)]
    args += [f"{k}={v}" for k, v in uniforms.items()]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"evaluating the shader failed: {(r.stderr or r.stdout).strip()}")
        return None
    return np.fromfile(raw, dtype=np.float32).reshape(h, w, 4)


def reference(w, h, p, origin=(0.0, 0.0)):
    """The same composite, in the NumPy the rest of FacetUI is lit by.

    Mirrors main() in the shader, in the same order: rim scales the
    premultiplied colour, then the edge is composited over it source-over,
    and both are gated to the window frame.

    `origin` shifts the sampled grid the way probe_origin does, so the grid can
    straddle the frame edge -- which is the only way the gate gets tested.
    """
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    # Pixel centres, which is where the rasteriser evaluates.
    px, py = xs + 0.5 - origin[0], ys + 0.5 - origin[1]

    size_x, size_y = p["size"]
    inside = ((px >= 0) & (py >= 0) & (px <= size_x) & (py <= size_y)).astype(np.float64)

    lateral = (px / max(size_x, 1)) * 2.0 - 1.0

    tex = np.broadcast_to(np.asarray(p["tex"], np.float64), (h, w, 4)).copy()

    # FacetRimShader. facet_math works in normalised coordinates with the rim
    # as a fraction of the width; the shader works in pixels. They agree when
    # the fraction is the pixel width over the surface width -- which is the
    # conversion this line is, and getting it wrong is the likeliest way this
    # check would pass while the shader is wrong.
    band = 1.0 - rim_darkening(lateral, p["rim"] / size_x, p["amount"])
    tex[..., :3] *= (1.0 - inside * band)[..., None]

    # FacetEdgeShader, composited over, and gated the same way.
    a = edge_highlight(py, p["thickness"], lateral, p["intensity"]) * inside
    tint = np.asarray(p["tint"], np.float64)
    out = np.empty_like(tex)
    out[..., :3] = tint * a[..., None] + tex[..., :3] * (1.0 - a[..., None])
    out[..., 3] = a + tex[..., 3] * (1.0 - a)
    return out


def check_transcription(glsl):
    """The GLSL and the AGSL still say the same thing.

    Compares the expressions, not the whitespace: a constant edited on one
    platform and not the other is the failure this is for, and it is invisible
    to every other check until something looks subtly wrong on one of them.
    """
    def exprs(text, keys):
        out = {}
        for key in keys:
            m = re.search(rf"\b{key}\s*=\s*([^;]+);", text)
            if m:
                out[key] = re.sub(r"\s+", "", m.group(1))
        return out

    agsl = {}
    for path in AGSL_PATCHES.values():
        body = "\n".join(l[1:] for l in path.read_text().splitlines()
                         if l.startswith("+"))
        agsl.update(exprs(body, ["edge", "arc", "a", "band"]))
    mine = exprs(glsl, ["edge", "arc", "a", "band"])

    # The AGSL reads uniforms as in_*; the GLSL calls them facet_*, and the rim
    # returns its band rather than assigning it. Normalise those two spellings
    # and nothing else.
    def norm(s):
        s = s.replace("in_thickness", "facet_thickness")
        s = s.replace("in_intensity", "facet_intensity")
        s = s.replace("in_size", "facet_size")
        s = s.replace("in_rim", "facet_rim")
        s = s.replace("in_amount", "facet_amount")
        return s

    if not agsl:
        fail("could not read any AGSL expressions out of the patches -- this "
             "check is not running, whatever it prints")
        return
    for key, want in agsl.items():
        if key not in mine:
            fail(f"the GLSL has no `{key}` expression; the AGSL does "
                 f"(`{want}`), so the two are no longer transcriptions")
        elif norm(want) != mine[key]:
            fail(f"`{key}` differs between the AGSL and the GLSL:\n"
                 f"         AGSL: {norm(want)}\n"
                 f"         GLSL: {mine[key]}")
    if not fails:
        ok(f"the GLSL and the AGSL agree on {len(agsl)} expressions "
           f"({', '.join(sorted(agsl))})")


def main():
    if not SHADER.exists():
        print(f"[FAIL] no shader at {SHADER}")
        return 1

    glsl = SHADER.read_text()

    with tempfile.TemporaryDirectory() as td:
        workdir = pathlib.Path(td)
        probe = build_probe(workdir)

        # 1 -- it compiles, as KWin would compile it.
        source = preprocess(glsl)
        good, log = compile_shader(probe, source, workdir, "facetui")
        if good:
            ok(f"facetui-glass.frag compiles as KWin builds it ({log.split(' on ')[-1]})")
        else:
            fail("facetui-glass.frag does not compile:\n" +
                 "\n".join("         " + l for l in log.splitlines()[:20]))

        # 2 -- and the compiler is live.
        survived = []
        for name, src in MUST_REJECT.items():
            accepted, _ = compile_shader(
                probe, KWIN_PREAMBLE + src, workdir, "reject")
            if accepted:
                survived.append(name)
        if survived:
            fail(f"the compiler accepted {len(survived)} shader(s) it must "
                 f"reject ({', '.join(survived)}) -- the check above proves "
                 f"nothing")
        else:
            ok(f"the compiler rejected all {len(MUST_REJECT)} broken shaders, "
               f"so the check above means something")

        # 3 -- and it computes what the rest of FacetUI computes.
        if good:
            # The grid is LARGER than the frame and offset, so it reaches
            # negative coordinates on two sides and past facet_size on the
            # other two -- which is where a window's shadow lives, and the only
            # place the frame gate can be caught missing.
            w, h = 97, 61          # deliberately not round, and not square
            origin = (18.0, 11.0)
            p = {
                "tex": (0.31, 0.37, 0.48, 0.78),
                "size": (w - 36.0, h - 22.0),
                "thickness": 12.0,
                "intensity": 0.5,
                "tint": (0.92, 0.96, 1.0),
                "rim": 26.0,
                "amount": 0.35,
            }
            got = evaluate(probe, source, workdir, w, h, {
                "sampler": ",".join(str(v) for v in p["tex"]),
                "probe_origin": f"{origin[0]},{origin[1]}",
                "facet_size": f"{p['size'][0]},{p['size'][1]}",
                "facet_thickness": p["thickness"],
                "facet_intensity": p["intensity"],
                "facet_tint": ",".join(str(v) for v in p["tint"]),
                "facet_rim": p["rim"],
                "facet_amount": p["amount"],
                "modulation": "1,1,1,1",
            })
            if got is not None:
                want = reference(w, h, p, origin)
                err = np.abs(got.astype(np.float64) - want)
                worst = err.max()
                # Generous next to float32 rounding, tight next to any real
                # disagreement: a swapped axis or a wrong constant is off by
                # orders of magnitude more than this.
                if worst > 2e-4:
                    yi, xi, ci = np.unravel_index(err.argmax(), err.shape)
                    fail(f"the shader and shared/facetui/facet_math.py "
                         f"disagree by {worst:.2e} at pixel ({xi}, {yi}) "
                         f"channel {'rgba'[ci]}: shader {got[yi, xi, ci]:.6f}, "
                         f"NumPy {want[yi, xi, ci]:.6f}")
                else:
                    ok(f"the shader's output matches facet_math.py over "
                       f"{w}x{h} pixels (worst error {worst:.1e})")

                # A comparison that would pass on a flat image proves nothing,
                # so check the test actually exercised both effects.
                y0, x0 = int(origin[1]), int(origin[0])
                y1 = y0 + int(p["size"][1])
                x1 = x0 + int(p["size"][0])
                frame = got[y0:y1, x0:x1]
                edge_range = float(frame[:, :, 3].max() - frame[:, :, 3].min())
                rim_drop = float(frame[frame.shape[0] // 2, frame.shape[1] // 2, 0]
                                 - frame[frame.shape[0] // 2, 0, 0])
                if edge_range < 0.05:
                    fail(f"the evaluated image barely varies in alpha "
                         f"({edge_range:.3f}) -- the edge highlight was not "
                         f"exercised, so the agreement above is vacuous")
                elif rim_drop < 0.01:
                    fail(f"the evaluated image barely varies across x "
                         f"({rim_drop:.3f}) -- the rim darkening was not "
                         f"exercised, so the agreement above is vacuous")
                else:
                    ok(f"both effects are visible in the test image "
                       f"(edge alpha range {edge_range:.2f}, rim drop "
                       f"{rim_drop:.2f}), so the agreement is not vacuous")

                # Outside the frame is the window's shadow. Both effects are
                # even in p, so an ungated shader mirrors the highlight into it.
                outside = got.copy()
                outside[y0:y1, x0:x1] = np.asarray(p["tex"], np.float32)
                spill = float(np.abs(outside - np.asarray(p["tex"], np.float32)).max())
                if spill > 2e-4:
                    fail(f"the shader changes pixels OUTSIDE the window frame "
                         f"by up to {spill:.3f} -- that region is the window's "
                         f"shadow, and a highlight there floats above the "
                         f"window")
                else:
                    ok("nothing is drawn outside the window frame, so the "
                       "highlight is not mirrored into the shadow")

    # 4 -- and it is still the same shader as the one on Android.
    check_transcription(glsl)

    if fails:
        print(f"\nFAILED: {len(fails)} problem(s)")
        return 1
    print("\nThe GLSL compiles under a real driver and computes what the rest "
          "of FacetUI\ncomputes. It has NOT been run in a compositor -- see "
          "desktop/kwin/README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
