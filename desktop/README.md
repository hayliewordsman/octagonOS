# octagonOS Desktop

**Nothing here yet.** This directory exists because the repository was laid out
for two editions before the second one was started, rather than being
reorganised under it later.

## The idea

An Ubuntu-based Linux distribution carrying FacetUI — the same glass design
language as the mobile edition, from the same maths in
[`shared/facetui`](../shared/facetui).

## Why this is more provable than the mobile edition

The Android work in [`mobile/`](../mobile) can be verified but not *run*: a GSI
needs 250–400 GB to build and a phone to boot. Desktop Linux does not have that
problem. A compositor effect, a Plymouth theme, an icon theme and an installed
ISO can all be built and looked at on ordinary hardware, which means this
edition can reach "seen working" rather than stopping at "verified as far as
possible".

## What would port, and what would not

| Asset | Desktop form |
|---|---|
| `facet_math.py` | Unchanged — already NumPy |
| The AGSL shaders | GLSL compositor effect; AGSL is close enough to port nearly verbatim |
| The boot animation | A Plymouth theme. The generator already emits PNG frame sequences |
| The icon pack | A freedesktop icon theme. The glyphs are already vectors, the tile already a PNG |
| The depth model, `L0`–`L4` | Blur strength per surface type |
| The octagon, the palette, the hairline | Directly |

What does not port: RROs, `AndroidManifest.xml`, adaptive icons, `PopupWindow`,
form-factor detection — everything shaped by Android rather than by FacetUI.

## The decision that shapes everything else

Which compositor. Glass needs compositor-level blur, and how much control there
is over it varies enormously — enough that it should be settled before any
other work starts, because almost every later choice follows from it.
