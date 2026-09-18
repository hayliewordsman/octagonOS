#!/usr/bin/env python3
"""
Build the octagonOS boot animation.

Renders an eight-facet glass octagon -- the octagonOS mark -- lit by FacetUI's
own shader maths, and packs it as an Android ``bootanimation.zip``.

    ./make-bootanimation.py --out out/bootanimation.zip

Why a square canvas: octagonOS targets both slab phones (tall, ~20:9) and
physical-keyboard phones (Titan-class, near-square). Android's bootanimation
scales the animation to fit the display and centres it, so a square canvas
centres correctly on both instead of being letterboxed on one. See
docs/bootanimation.md.

Requires Pillow and NumPy. No Android SDK, no device.
"""

import argparse
import math
import os
import shutil
import sys
import tempfile
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from facet_math import edge_highlight, rim_darkening  # noqa: E402

# --- Brand ------------------------------------------------------------------
# No spaces in either name; they are single tokens everywhere they appear.
WORDMARK = "octagonOS"
SUBMARK = "FacetUI"

#: Deep background. Not pure black: glass needs something to sample.
#:
#: This is a FLAT colour, deliberately. The canvas is square and the screen is
#: not, so bootanimation clears the letterbox around the frames to the per-part
#: background colour from desc.txt. If the frame's own edges did not match that
#: colour exactly, the letterbox seam would be visible as a band across the
#: screen -- and on a slab phone that band is most of the display. Everything
#: with a gradient is kept away from the canvas edge instead.
BG_BASE = np.array([0.016, 0.021, 0.031])

#: The two accents the facets grade between, giving the mark a spectral read.
ACCENT_A = np.array([0.36, 0.72, 1.00])   # cool cyan-blue
ACCENT_B = np.array([0.62, 0.50, 1.00])   # violet

#: Facet geometry. A regular octagon with a flat top: edge normals lie on
#: multiples of 45 degrees, vertices on the 22.5-degree offsets.
FACETS = 8
FACET_HALF_ANGLE = math.pi / FACETS          # 22.5 degrees
FACET_TILT = math.radians(52.0)              # how far each facet leans outward
LIGHT_ELEVATION = math.radians(58.0)

#: Shading constants.
AMBIENT = 0.21
SPECULAR_POWER = 48.0
SPECULAR_STRENGTH = 1.5
GLASS_ALPHA = 0.88

#: The gem's flat top, as a fraction of the apothem, and how transparent it is.
#: A cut stone has a table; without one the facets converge to a spike and the
#: mark stops reading as an octagon.
TABLE_FRAC = 0.46
TABLE_ALPHA = 0.74

#: Bloom. Above the threshold, blurred and added back.
BLOOM_THRESHOLD = 0.62
BLOOM_GAIN = 0.55

#: FacetUI parameters, matching the SystemUI patch defaults where they map.
RIM_WIDTH = 0.42        # fraction of the facet half-width
RIM_AMOUNT = 0.35       # FACET_RIM_AMOUNT in ScrimView
EDGE_INTENSITY = 0.50   # FACET_EDGE_MAX_INTENSITY in ScrimView

#: Fonts, in preference order. DejaVu ships with essentially every Linux
#: distribution, so the last entries are the portable fallback.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_LIGHT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def pick_font(candidates, size, override=None):
    paths = ([override] if override else []) + candidates
    for path in paths:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise SystemExit(
        "error: no usable TrueType font found. Install fonts-dejavu-core, or "
        "pass --font / --font-light with a path to a .ttf"
    )


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


# --- Geometry ---------------------------------------------------------------

def facet_fields(size, cx, cy):
    """Per-pixel octagon fields, independent of the mark's scale.

    The octagon never moves; only the light does, and the mark grows during the
    intro. Everything here is either in pixels-from-centre or already
    normalised, so a frame picks its own apothem and the same arrays serve.
    """
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    px = xs - cx
    py = ys - cy

    # Distance to each of the eight edge planes. A regular polygon's interior
    # is where every one is within the apothem, so the maximum over the eight
    # is the governing distance and its index is the facet that owns the pixel.
    phis = np.arange(FACETS) * (2.0 * math.pi / FACETS)
    dists = np.stack([px * math.cos(phi) + py * math.sin(phi) for phi in phis])

    order = np.argsort(dists, axis=0)
    facet = order[-1].astype(np.int8)
    d_max = np.take_along_axis(dists, order[-1][None], 0)[0]
    d_second = np.take_along_axis(dists, order[-2][None], 0)[0]

    # Position across the owning facet. The facet is a wedge, so its half-width
    # grows with radial distance; dividing by it normalises to -1..1 and is
    # independent of how large the mark is drawn.
    phi = phis[facet.astype(np.intp)]
    lateral_px = -px * np.sin(phi) + py * np.cos(phi)
    half_width = np.maximum(d_max, 1e-3) * math.tan(FACET_HALF_ANGLE)
    lateral = np.clip(lateral_px / half_width, -1.0, 1.0).astype(np.float32)

    return {
        "facet": facet.astype(np.intp),
        "d_max": d_max.astype(np.float32),
        "seam": (d_max - d_second).astype(np.float32),
        "lateral": lateral,
        "radius": np.sqrt(px * px + py * py).astype(np.float32),
    }


def facet_lighting(psi):
    """Diffuse and specular terms for the eight crown facets and the table."""
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

    # Blinn-Phong; the viewer looks straight down the z axis.
    half = light + np.array([0.0, 0.0, 1.0])
    half /= np.linalg.norm(half)

    diffuse = np.maximum(normals @ light, 0.0)
    specular = np.maximum(normals @ half, 0.0) ** SPECULAR_POWER

    # The table is flat, so its normal is simply +z.
    table_diffuse = max(float(light[2]), 0.0)
    table_specular = max(float(half[2]), 0.0) ** SPECULAR_POWER
    return diffuse, specular, table_diffuse, table_specular


def facet_tints():
    """A spectral grade around the mark, so no two adjacent facets match."""
    t = np.arange(FACETS) / (FACETS - 1.0)
    # Fold so the last facet meets the first on the same hue -- the grade has
    # to be cyclic or the seam between them reads as a mistake.
    t = 1.0 - np.abs(t * 2.0 - 1.0)
    return ACCENT_A[None, :] * (1.0 - t[:, None]) + ACCENT_B[None, :] * t[:, None]


# --- Frame rendering --------------------------------------------------------

def render(fields, size, psi, reveal, scale, glow_gain, mark_alpha, sub_alpha,
           fonts, base_apothem):
    """Render one frame. Returns a PIL RGB image."""
    apothem = base_apothem * scale
    diffuse, specular, table_diff, table_spec = facet_lighting(psi)
    tints = facet_tints()

    facet = fields["facet"]
    d_max = fields["d_max"]
    lateral = fields["lateral"]
    radius = fields["radius"]

    # --- background --------------------------------------------------------
    # Flat base, plus a glow behind the mark that tracks the light -- the
    # surface glass samples must not be uniform or the effect collapses. The
    # glow is windowed to reach exactly zero before the canvas edge, so every
    # border pixel is BG_BASE and the letterbox seam cannot show.
    rgb = np.broadcast_to(BG_BASE.astype(np.float32),
                          (size, size, 3)).copy()

    halo_tint = (ACCENT_A * 0.55 + ACCENT_B * 0.45).astype(np.float32)
    window = 1.0 - smoothstep(size * 0.30, size * 0.47, radius)
    halo = np.exp(-(radius / (apothem * 1.30)) ** 2) * glow_gain * window
    rgb = rgb + halo[:, :, None] * halo_tint[None, None, :] * 0.26

    # --- regions -----------------------------------------------------------
    # A cut gem has a flat table at the top and a ring of sloped crown facets
    # around it. Both are panes of glass; they differ in which way they face.
    table_r = apothem * TABLE_FRAC
    inside = d_max <= apothem
    is_table = inside & (d_max <= table_r)
    is_crown = inside & ~is_table

    # Facets arrive one at a time during the intro.
    appear = ease_out_cubic(np.clip(reveal * (FACETS + 1) - np.arange(FACETS), 0.0, 1.0))

    # --- crown -------------------------------------------------------------
    shade = AMBIENT + (1.0 - AMBIENT) * diffuse
    crown_rgb = tints * shade[:, None] + specular[:, None] * SPECULAR_STRENGTH
    colour = crown_rgb[facet]

    # Crown facets are brighter where they meet the table and fall off toward
    # the girdle, the way a bevel catches light along its length.
    span = np.maximum(apothem - table_r, 1e-3)
    along = np.clip((apothem - d_max) / span, 0.0, 1.0)
    colour = colour * (0.72 + 0.38 * along)[:, :, None]

    # FacetUI rim darkening, across each crown facet.
    colour = colour * rim_darkening(lateral, RIM_WIDTH, RIM_AMOUNT)[:, :, None]

    # --- table -------------------------------------------------------------
    table_tint = (ACCENT_A * 0.44 + ACCENT_B * 0.56).astype(np.float32)
    table_lat = np.clip(d_max / max(table_r, 1e-3), 0.0, 1.0)
    # A flat pane still gathers light unevenly: brightest through the middle,
    # where the eye is looking straight through the stone.
    gather = 1.0 - 0.34 * table_lat ** 2
    table_col = (table_tint[None, None, :]
                 * (AMBIENT + (1.0 - AMBIENT) * table_diff)
                 * gather[:, :, None] * 1.45
                 + table_spec * SPECULAR_STRENGTH * 0.75)
    # The table is a pane too: darken it toward its own rim. Normalised so the
    # centre is untouched and the girdle takes the full amount.
    table_col = table_col * rim_darkening(
        table_lat, RIM_WIDTH, RIM_AMOUNT * 0.8)[:, :, None]
    colour = np.where(is_table[:, :, None], table_col, colour)

    # --- FacetUI specular edge --------------------------------------------
    # Along the outer boundary, with intensity tracking each facet's own
    # specular term so the highlight sweeps with the light rather than sitting
    # on every edge at once.
    lit = EDGE_INTENSITY * (0.30 + 0.70 * np.clip(specular * 2.4, 0.0, 1.0))
    edge_a = edge_highlight(apothem - d_max, apothem * 0.085, lateral, lit[facet])
    colour = colour + edge_a[:, :, None]

    # --- hairlines ---------------------------------------------------------
    # Without a boundary this reads as translucent grey rather than glass. A
    # thin stroke at each seam is what separates the two.
    w = max(size / 700.0, 0.8)
    seam_line = np.exp(-(fields["seam"] / w) ** 2) * 0.50          # facet to facet
    girdle = np.exp(-((d_max - table_r) / (w * 1.3)) ** 2) * 0.42  # crown to table
    step = np.exp(-((d_max - table_r * 0.54) / (w * 1.2)) ** 2) * 0.16  # step cut
    outline = np.exp(-((d_max - apothem) / (w * 1.5)) ** 2) * 0.58  # outer edge
    colour = colour + (seam_line * is_crown + girdle + outline
                       + step * is_table)[:, :, None]

    # --- composite ---------------------------------------------------------
    present = appear[facet]
    alpha = np.where(is_crown, GLASS_ALPHA, 0.0) * present
    alpha = np.where(is_table, TABLE_ALPHA * float(np.clip(reveal * 1.6 - 0.6, 0, 1)),
                     alpha).astype(np.float32)

    rgb = rgb * (1.0 - alpha[:, :, None]) + colour * alpha[:, :, None]

    # --- bloom -------------------------------------------------------------
    # Glass without bloom looks like coloured plastic. Bright-pass, blur, add.
    bright = np.clip(rgb.max(axis=2) - BLOOM_THRESHOLD, 0.0, None)
    if float(bright.max()) > 0.01:
        blurred = np.asarray(
            Image.fromarray(np.clip(bright * 255, 0, 255).astype(np.uint8), "L")
            .filter(ImageFilter.GaussianBlur(size / 38.0)),
            dtype=np.float32) / 255.0
        rgb = rgb + blurred[:, :, None] * halo_tint[None, None, :] * BLOOM_GAIN

    img = Image.fromarray(
        (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "RGB")
    draw_wordmark(img, size, fonts, mark_alpha, sub_alpha, base_apothem)
    return img


def draw_wordmark(img, size, fonts, mark_alpha, sub_alpha, apothem):
    """Draw octagonOS, and FacetUI beneath it."""
    if mark_alpha <= 0.004 and sub_alpha <= 0.004:
        return
    font_main, font_sub = fonts
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # Positioned off the base apothem, not the animated one, so the type stays
    # put while the mark grows.
    baseline = size * 0.5 + apothem + size * 0.115

    if mark_alpha > 0.004:
        a = int(round(float(np.clip(mark_alpha, 0, 1)) * 255))
        tracked_text(d, size * 0.5, baseline, WORDMARK, font_main,
                     (242, 248, 255, a), tracking=size * 0.003)

    if sub_alpha > 0.004:
        a = int(round(float(np.clip(sub_alpha, 0, 1)) * 225))
        tint = tuple(int(c * 255) for c in np.clip(ACCENT_A * 0.95, 0, 1))
        tracked_text(d, size * 0.5, baseline + size * 0.070, SUBMARK, font_sub,
                     tint + (a,), tracking=size * 0.020)

    composed = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    img.paste(composed, (0, 0))


def tracked_text(draw, cx, cy, text, font, fill, tracking=0.0):
    """Centred text with letter tracking. PIL has none, so step the glyphs."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2.0
    for ch, w in zip(text, widths):
        draw.text((x, cy), ch, font=font, fill=fill, anchor="lm")
        x += w + tracking


# --- Timeline ---------------------------------------------------------------

def build_frames(size, fps, intro_frames, loop_frames, outro_frames, fonts,
                 apothem, quiet=False):
    """Render every part. Returns {part_name: [PIL.Image, ...]}."""
    fields = facet_fields(size, size / 2.0, size / 2.0)
    parts = {}

    def note(msg):
        if not quiet:
            print(msg, file=sys.stderr, flush=True)

    # part0 -- the mark assembles, facet by facet, and the light starts moving.
    note(f"[*] part0: {intro_frames} frames")
    frames = []
    for i in range(intro_frames):
        t = i / max(intro_frames - 1, 1)
        frames.append(render(
            fields, size,
            psi=-math.pi * 0.55 + t * math.pi * 0.85,
            reveal=ease_out_cubic(smoothstep(0.0, 0.72, t)),
            scale=0.62 + 0.38 * ease_out_cubic(smoothstep(0.0, 0.85, t)),
            glow_gain=0.20 + 0.55 * t,
            mark_alpha=smoothstep(0.55, 0.95, t),
            sub_alpha=smoothstep(0.74, 1.0, t),
            fonts=fonts, base_apothem=apothem))
    parts["part0"] = frames

    # part1 -- the loop. Everything periodic here completes exactly one cycle
    # over the part, so the last frame hands off to the first with no seam.
    note(f"[*] part1: {loop_frames} frames (seamless)")
    frames = []
    for i in range(loop_frames):
        t = i / loop_frames                       # note: not loop_frames - 1
        frames.append(render(
            fields, size,
            psi=math.pi * 0.30 + t * 2.0 * math.pi,
            reveal=1.0,
            scale=1.0,
            glow_gain=0.75 + 0.12 * math.sin(t * 2.0 * math.pi),
            mark_alpha=1.0,
            sub_alpha=1.0,
            fonts=fonts, base_apothem=apothem))
    parts["part1"] = frames

    # part2 -- plays once after boot completes, so the animation resolves
    # instead of being cut off mid-sweep.
    note(f"[*] part2: {outro_frames} frames")
    frames = []
    for i in range(outro_frames):
        t = i / max(outro_frames - 1, 1)
        frames.append(render(
            fields, size,
            psi=math.pi * 0.30 + t * math.pi * 0.5,
            reveal=1.0,
            scale=1.0 + 0.035 * ease_out_cubic(t),
            glow_gain=0.75 + 1.05 * ease_out_cubic(t),
            mark_alpha=1.0,
            sub_alpha=1.0,
            fonts=fonts, base_apothem=apothem))
    parts["part2"] = frames

    return parts


#: The background colour bootanimation clears to, as #RRGGBB. Must equal
#: BG_BASE or the letterbox around the square canvas will not match the frames.
BG_HEX = "".join(f"{int(round(c * 255)):02x}" for c in BG_BASE)

#: part0 plays once (`p 1`), part1 loops until boot completes (`p 0`), part2
#: plays to completion whatever happens (`c 1`) so the mark resolves instead of
#: being cut off mid-sweep.
#:
#: Only part1 is memory-resident: bootanimation allocates a GL texture per
#: frame for any part whose count != 1 and frees them only when the whole
#: animation ends. part0 and part2 decode into one reused texture. That is why
#: the loop is the short part. See loop_texture_bytes().
DESC_TEMPLATE = """{w} {h} {fps}
p 1 0 part0 #{bg}
p 0 0 part1 #{bg}
c 1 0 part2 #{bg}
"""


#: How much GL texture memory the looping part may occupy. bootanimation keeps
#: a decoded texture per frame for every part whose count != 1, for the whole
#: boot, so a long high-resolution loop can cost hundreds of megabytes on a
#: device that has barely finished mounting /data. Verified against
#: frameworks/base/cmds/bootanimation/BootAnimation.cpp on lineage-24.0:
#: playAnimation() calls glGenTextures per frame under `if (part.count != 1)`,
#: and the matching glDeleteTextures only runs after the animation completes.
LOOP_TEXTURE_BUDGET_MIB = 64.0


def loop_texture_bytes(size, loop_frames):
    """Resident GL texture cost of the looping part, in bytes (RGBA8)."""
    return size * size * 4 * loop_frames


def check_loop_budget(size, loop_frames, quiet=False):
    mib = loop_texture_bytes(size, loop_frames) / 1048576.0
    msg = (f"[*] loop part: {loop_frames} frames x {size}x{size} RGBA "
           f"= {mib:.0f} MiB resident GL texture")
    if mib > LOOP_TEXTURE_BUDGET_MIB:
        print(msg, file=sys.stderr)
        print(f"warning: that exceeds the {LOOP_TEXTURE_BUDGET_MIB:.0f} MiB budget. "
              f"bootanimation holds every frame of a looping part in GPU memory "
              f"for the whole boot. Reduce --loop or --size.", file=sys.stderr)
    elif not quiet:
        print(msg, file=sys.stderr)
    return mib


def write_zip(parts, out_path, size, fps, png_optimise=True, quiet=False):
    """Pack the parts as a bootanimation.zip.

    Every entry is STORED, never deflated: bootanimation memory-maps the zip
    and reads frames straight out of it, so a compressed entry costs a
    decompression on the critical boot path -- and the frames are PNG, which
    is already compressed, so deflate would buy nothing anyway.
    """
    staging = tempfile.mkdtemp(prefix="octagonos-boot-")
    try:
        for name, frames in sorted(parts.items()):
            d = os.path.join(staging, name)
            os.makedirs(d, exist_ok=True)
            for i, img in enumerate(frames):
                img.save(os.path.join(d, f"{i:04d}.png"),
                         optimize=png_optimise)

        desc = DESC_TEMPLATE.format(w=size, h=size, fps=fps, bg=BG_HEX)
        with open(os.path.join(staging, "desc.txt"), "w", newline="\n") as fh:
            fh.write(desc)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as z:
            # desc.txt first: the player reads it before anything else.
            z.write(os.path.join(staging, "desc.txt"), "desc.txt")
            for name in sorted(parts):
                d = os.path.join(staging, name)
                for fn in sorted(os.listdir(d)):
                    z.write(os.path.join(d, fn), f"{name}/{fn}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not quiet:
        print(f"[*] wrote {out_path} "
              f"({os.path.getsize(out_path) / 1048576:.1f} MiB)", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Build the octagonOS boot animation.")
    ap.add_argument("--out", default="out/bootanimation.zip")
    ap.add_argument("--size", type=int, default=720,
                    help="square canvas edge, px (default: 720)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--intro", type=int, default=40, help="part0 frame count")
    ap.add_argument("--loop", type=int, default=30,
                    help="part1 frame count -- this is the memory-resident part")
    ap.add_argument("--outro", type=int, default=22, help="part2 frame count")
    ap.add_argument("--font", help="override the wordmark font (.ttf)")
    ap.add_argument("--font-light", help="override the FacetUI font (.ttf)")
    ap.add_argument("--frames-dir",
                    help="also write the raw PNG frames here, for inspection")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    size = args.size
    apothem = size * 0.255
    fonts = (
        pick_font(FONT_CANDIDATES, int(size * 0.072), args.font),
        pick_font(FONT_LIGHT_CANDIDATES, int(size * 0.030), args.font_light),
    )

    check_loop_budget(size, args.loop, quiet=args.quiet)

    parts = build_frames(size, args.fps, args.intro, args.loop, args.outro,
                         fonts, apothem, quiet=args.quiet)

    if args.frames_dir:
        for name, frames in parts.items():
            d = os.path.join(args.frames_dir, name)
            os.makedirs(d, exist_ok=True)
            for i, img in enumerate(frames):
                img.save(os.path.join(d, f"{i:04d}.png"))

    write_zip(parts, args.out, size, args.fps, quiet=args.quiet)


if __name__ == "__main__":
    main()
