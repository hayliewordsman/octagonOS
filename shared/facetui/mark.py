"""
Rendering the octagonOS mark.

The eight-facet glass octagon, the wordmarks under it, and the three-part
timeline that assembles, loops and resolves it -- lit by FacetUI's own shader
maths from `facet_math`.

Shared because both editions boot. Android wants it as a `bootanimation.zip`;
Linux wants it as a Plymouth theme. Those are two ways of packaging the same
frames, and only the packaging differs, so only the packaging lives with its
platform.

Everything here is deliberately free of either: it renders PIL images and
returns them. What to do with them is the caller's problem.
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .facet_math import edge_highlight, rim_darkening
from .palette import (
    ACCENT_A, ACCENT_B, FACETS, FACET_HALF_ANGLE, FACET_TILT, LIGHT_ELEVATION,
    RIM_WIDTH, RIM_AMOUNT, EDGE_INTENSITY,
)

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

#: FacetUI parameters come from shared/facetui/palette.py; see the import above.

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



