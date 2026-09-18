"""
The FacetUI glass tile: an octagon of cut glass, lit from a fixed angle.

The same construction as the boot animation's mark -- eight crown facets around
a flat table, rim-darkened, with a specular edge -- but lit from one direction
rather than animated, and sized to sit inside an icon.

WHY THIS IS SHARED

Both editions draw this. The Android icon pack renders it as the background of
every adaptive icon; the desktop icon theme renders it at each of the sizes a
freedesktop theme ships. They are the same surface, and a second copy of this
arithmetic would be free to drift away from the first -- which is the whole
reason `shared/` exists.

What is NOT here is how big the octagon is relative to its canvas. Android
reserves the outer edge of an adaptive icon for parallax bleed, so its tile
fills two thirds of the drawable; a desktop icon has no such reserve and fills
most of its box. That is a platform's geometry, not FacetUI's, so it is passed
in.

Requires Pillow and NumPy.
"""

import math

import numpy as np
from PIL import Image

from .facet_math import edge_highlight, rim_darkening
from .palette import (
    ACCENT_A, ACCENT_B, EDGE_INTENSITY, FACETS, FACET_HALF_ANGLE, FACET_TILT,
    LIGHT_ELEVATION, RIM_AMOUNT, RIM_WIDTH,
)

#: Where the light sits. Fixed, not animated: every icon on the screen is lit
#: from the same direction, which is what makes a grid of them read as one
#: surface rather than as a scatter of unrelated buttons.
ICON_LIGHT_ANGLE = math.radians(-118.0)

AMBIENT = 0.30
SPECULAR_POWER = 36.0
SPECULAR_STRENGTH = 0.85

#: The flat table, as a fraction of the octagon's apothem.
#:
#: Much larger than the boot animation's mark uses (0.46). There the facets are
#: the subject; here they are a bezel and the subject is the glyph on top of
#: them. Eight facets' worth of value variation running under a thin glyph
#: makes the glyph unreadable, so the crown is pushed out to a ring and the
#: middle left calm.
#:
#: 0.84, not the 0.70 this started at. At 0.70 fifteen of the twenty-five
#: glyphs ran straight over the table's edge onto the facets: the calm centre
#: existed, but most glyphs were not inside it.
TABLE_FRAC = 0.84


def table_radius(apothem):
    """Octagon-distance of the table's edge, for an octagon of this apothem.

    The boundary between the calm centre a glyph should sit on and the faceted
    crown it should not. Exported because the icon verifiers check every glyph
    against it, and a second copy of this multiplication would be free to drift.
    """
    return apothem * TABLE_FRAC


def facet_lighting(psi):
    """Diffuse and specular for the eight crown facets, plus the flat table."""
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
    half = light + np.array([0.0, 0.0, 1.0])
    half /= np.linalg.norm(half)
    return (
        np.maximum(normals @ light, 0.0),
        np.maximum(normals @ half, 0.0) ** SPECULAR_POWER,
        max(float(light[2]), 0.0),
        max(float(half[2]), 0.0) ** SPECULAR_POWER,
    )


def render_tile(px, apothem, seam_scale=None):
    """The glass octagon, as an RGBA image `px` wide.

    :param px: the canvas, in pixels.
    :param apothem: the octagon's apothem, in pixels. How much of the canvas
        the octagon fills is the platform's business, not FacetUI's.
    :param seam_scale: the width the facet seams and the outline are drawn at,
        in pixels. Defaults to the canvas size over 108, which is the Android
        drawable's unit; passed explicitly by anything that is not drawing an
        adaptive icon.
    """
    cx = cy = px / 2.0

    ys, xs = np.mgrid[0:px, 0:px].astype(np.float32)
    dx, dy = xs - cx, ys - cy

    phis = np.arange(FACETS) * (2.0 * math.pi / FACETS)
    dists = np.stack([dx * math.cos(p) + dy * math.sin(p) for p in phis])
    order = np.argsort(dists, axis=0)
    facet = order[-1]
    d_max = np.take_along_axis(dists, order[-1][None], 0)[0]
    d_second = np.take_along_axis(dists, order[-2][None], 0)[0]

    phi = phis[facet]
    lateral_px = -dx * np.sin(phi) + dy * np.cos(phi)
    half_width = np.maximum(d_max, 1e-3) * math.tan(FACET_HALF_ANGLE)
    lateral = np.clip(lateral_px / half_width, -1.0, 1.0)

    diffuse, specular, table_diff, table_spec = facet_lighting(ICON_LIGHT_ANGLE)

    t = np.arange(FACETS) / (FACETS - 1.0)
    t = 1.0 - np.abs(t * 2.0 - 1.0)
    tints = ACCENT_A[None, :] * (1.0 - t[:, None]) + ACCENT_B[None, :] * t[:, None]

    table_r = table_radius(apothem)
    inside = d_max <= apothem
    is_table = inside & (d_max <= table_r)
    is_crown = inside & ~is_table

    shade = AMBIENT + (1.0 - AMBIENT) * diffuse
    colour = (tints * shade[:, None] + specular[:, None] * SPECULAR_STRENGTH)[facet]

    span = max(apothem - table_r, 1e-3)
    along = np.clip((apothem - d_max) / span, 0.0, 1.0)
    colour = colour * (0.74 + 0.36 * along)[:, :, None]
    colour = colour * rim_darkening(lateral, RIM_WIDTH, RIM_AMOUNT)[:, :, None]

    table_tint = ACCENT_A * 0.44 + ACCENT_B * 0.56
    table_lat = np.clip(d_max / max(table_r, 1e-3), 0.0, 1.0)
    gather = 1.0 - 0.30 * table_lat ** 2
    table_col = (table_tint[None, None, :]
                 * (AMBIENT + (1.0 - AMBIENT) * table_diff)
                 * gather[:, :, None] * 1.40
                 + table_spec * SPECULAR_STRENGTH * 0.75)
    table_col = table_col * rim_darkening(
        table_lat, RIM_WIDTH, RIM_AMOUNT * 0.8)[:, :, None]
    colour = np.where(is_table[:, :, None], table_col, colour)

    lit = EDGE_INTENSITY * (0.34 + 0.66 * np.clip(specular * 2.4, 0.0, 1.0))
    colour = colour + edge_highlight(
        apothem - d_max, apothem * 0.10, lateral, lit[facet])[:, :, None]

    w = max(px / 108.0 if seam_scale is None else seam_scale, 0.7)
    seam = np.exp(-((d_max - d_second) / w) ** 2) * 0.34 * is_crown
    girdle = np.exp(-((d_max - table_r) / (w * 1.3)) ** 2) * 0.30
    outline = np.exp(-((d_max - apothem) / (w * 1.4)) ** 2) * 0.60
    colour = colour + (seam + girdle + outline)[:, :, None]

    # Antialias the silhouette: a hard inside/outside test leaves stair-stepped
    # diagonals, and an octagon is mostly diagonals.
    alpha = np.clip((apothem - d_max) / max(w, 0.5) + 0.5, 0.0, 1.0)
    alpha = np.where(inside | (d_max < apothem + w), alpha, 0.0)

    rgb = np.clip(colour, 0.0, 1.0)
    out = np.dstack([rgb, alpha[:, :, None]])
    return Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), "RGBA")
