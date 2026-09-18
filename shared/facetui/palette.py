"""
The FacetUI palette and shading constants.

One definition, imported by everything that renders FacetUI glass. These lived
in two copies before -- once in the boot animation generator and once in the
icon generator -- with a check in `validate-shaders.py` confirming the copies
still agreed. Sharing them is better than checking them: a constant that exists
once cannot drift.

The parameters that ALSO appear in the SystemUI patches (`FacetRimShader`,
`FacetEdgeShader` and their `ScrimView` constants) are still cross-checked,
because those copies are Kotlin and Java and genuinely cannot import this file.

Anything platform-specific belongs with its platform, not here. This file is
imported by Android tooling today and by desktop tooling later, so it must stay
free of either.
"""

import math

import numpy as np

# --- accents ----------------------------------------------------------------
#
# The two ends of FacetUI's spectral grade. Surfaces sample between them, so no
# two adjacent facets carry the same hue and the mark reads as cut glass rather
# than a flat plate.
#
# These are the *rendering* palette, used for generated artwork -- the boot
# animation and the icon tile. They are not what themes a running system: on
# device, FacetUI pulls its tint from the wallpaper-derived `system_accent*`
# ramps, so panels sample the wallpaper instead of flattening it. See
# shared/docs/design-language.md.
ACCENT_A = np.array([0.36, 0.72, 1.00])   # cool cyan-blue
ACCENT_B = np.array([0.62, 0.50, 1.00])   # violet

# --- geometry ---------------------------------------------------------------
#: The octagon. Eight facets, because the mark is an octagon and the system is
#: named for it.
FACETS = 8
FACET_HALF_ANGLE = math.pi / FACETS          # 22.5 degrees
FACET_TILT = math.radians(52.0)              # how far each facet leans outward
LIGHT_ELEVATION = math.radians(58.0)

# --- FacetUI parameters -----------------------------------------------------
#
# These four are the design, and they are also written down in Kotlin and Java
# inside the SystemUI patches. `mobile/tools/validate-shaders.py` checks that
# all the copies still agree; changing one here without changing those fails
# that check, which is the intended behaviour and not an inconvenience.

#: Width of the rim darkening band, as a fraction of a facet's half-width.
RIM_WIDTH = 0.42

#: Peak darkening at the rim. `FACETUI_RIM_AMOUNT` in ScrimView.
RIM_AMOUNT = 0.35

#: Peak alpha of the specular edge. `FACETUI_EDGE_MAX_INTENSITY` in ScrimView.
EDGE_INTENSITY = 0.50
