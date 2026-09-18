"""
The FacetUI shader math, in NumPy.

These are direct transcriptions of the AGSL in the FacetUI SystemUI patches --
`FacetEdgeShader.kt` and `FacetRimShader.kt` -- so the boot animation is lit by
the same math that lights the shade, the lockscreen and the keyboard. If a
constant changes in the shaders, change it here too and the branding follows.

The transcription is deliberately literal: the same expressions in the same
order, so the two can be read side by side. See docs/facetui.md.
"""

import numpy as np

# --- FacetEdgeShader -------------------------------------------------------
# AGSL:
#     float d    = p.y / t;
#     float edge = exp(-d * d * 2.0);
#     float x    = (p.x / max(in_size.x, 1.0)) * 2.0 - 1.0;
#     float arc  = max(1.0 - x * x * 0.55, 0.0);
#     float a    = clamp(edge * arc * in_intensity, 0.0, 1.0);

#: Centre-bias strength. `arc` in the AGSL; keeps the highlight reading as a
#: curved surface catching light rather than a painted-on stripe.
EDGE_ARC_BIAS = 0.55

#: Falloff sharpness. `exp(-d*d*2.0)` -- squared so the band stays tight at its
#: peak and fades quickly instead of smearing down the panel.
EDGE_FALLOFF = 2.0


def edge_highlight(distance, thickness, lateral, intensity):
    """Specular edge highlight.

    :param distance: perpendicular distance from the lit edge, in pixels
        (``p.y`` in the shader).
    :param lateral: position across the surface, normalised to -1..1
        (``x`` in the shader, after the remap).
    :param thickness: falloff distance in pixels (``in_thickness``).
    :param intensity: peak alpha (``in_intensity``).
    :returns: alpha in 0..1.
    """
    t = np.maximum(thickness, 1.0)
    d = distance / t
    edge = np.exp(-d * d * EDGE_FALLOFF)
    arc = np.maximum(1.0 - lateral * lateral * EDGE_ARC_BIAS, 0.0)
    return np.clip(edge * arc * intensity, 0.0, 1.0)


# --- FacetRimShader --------------------------------------------------------
# AGSL:
#     float dl   = p.x / r;
#     float dr   = (in_size.x - p.x) / r;
#     float band = abs(exp(-dl * dl) - exp(-dr * dr));
#     return vec4(c.rgb * (1.0 - in_amount * band), c.a);


def rim_darkening(lateral, rim, amount):
    """Rim darkening across a pane.

    A pane of glass is optically thicker where it curves away, so it absorbs
    more light at the rim than through the middle. Peaks at both edges, falls
    to nothing across the centre.

    :param lateral: position across the pane, normalised to -1..1.
    :param rim: width of the darkening band, as a fraction of the half-width.
    :param amount: peak darkening, 0..1.
    :returns: a multiplier for RGB, in 0..1.
    """
    # Remap -1..1 to the shader's 0..in_size.x convention, with in_size.x = 1.
    x = (lateral + 1.0) * 0.5
    r = max(rim, 1e-6)
    dl = x / r
    dr = (1.0 - x) / r
    band = np.abs(np.exp(-dl * dl) - np.exp(-dr * dr))
    return 1.0 - amount * band


# --- The rule that governs both --------------------------------------------
#
#   On a blurred surface, any effect that works by DISPLACING SAMPLES is
#   invisible. Only effects that MODIFY VALUES -- brightness, tint, contrast --
#   survive the blur.
#
# Both functions above modify values. That is not a coincidence: it is why
# these two survived and a refraction shader did not. See
# titan2e-eos/docs/glass-ui.md, which established the rule by rendering the
# maths rather than reasoning about it.
