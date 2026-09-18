# FacetUI

The design language both editions of octagonOS are built on. Nothing here is
specific to Android or to Linux; the platform-specific halves are
[`mobile/docs/facetui.md`](../../mobile/docs/facetui.md) and, when it exists,
the desktop equivalent.

FacetUI originates in
[titan2e-eos](https://github.com/hayliewordsman/titan2e-eos), where it was
designed against Android 16.

## The rule that governs everything

> On a blurred surface, any effect that works by **displacing samples** is
> invisible. Only effects that **modify values** — brightness, tint, contrast —
> survive the blur.

Established by rendering the shader maths rather than reasoning about it. It
killed a refraction shader, and then a chromatic-aberration replacement, before
either cost a build.

Both surviving shaders modify values: the edge highlight adds brightness, the
rim darkening scales it. That is not a coincidence, it is the rule doing its
job.

## The two shaders

They are the whole of FacetUI's glass, and they are small.

**The specular edge.** Blur alone reads as frosted plastic. What reads as
*glass* is the edge — a bright, narrow band where the surface curves away and
catches light. A squared falloff keeps the band tight at its peak rather than
smearing, and a centre bias makes it read as a curved surface rather than a
painted stripe.

**The rim darkening.** A pane of glass is optically thicker where it curves
away, so it absorbs more light at the rim than through the middle. Reproducing
that gives a panel a defined boundary without drawing a border on it.

Both live in [`../facetui/facet_math.py`](../facetui/facet_math.py) as a literal
transcription of the AGSL — the same expressions in the same order, so the two
can be read side by side.

## The depth model

Glass reads as depth only if blur is **hierarchical**. A single radius
everywhere looks like frosted plastic. Each tier roughly doubles, because the
eye reads the ratio between surfaces rather than absolute radii.

| Tier | Radius | For |
|---|---|---|
| `L0` | 0 | Opaque surfaces: wallpaper, app content |
| `L1` | 8dp | Inline chips, inactive tiles |
| `L2` | 24dp | Dialogs, menus, popups, folders, small panels |
| `L3` | 48dp | Notification shade, notifications, the keyboard |
| `L4` | 64dp | The deepest layer — the full shade window, the screen behind a dialog |

The point of writing these down is that **surfaces at the same visual depth
should be the same material**, even where the platform gives them unrelated
names. Android ships the volume dialog at 0dp, the power menu at 34dp and
launcher folders at 20dp — three surfaces a user reads as the same kind of
floating panel, made of three different materials. FacetUI puts all three on
`L2`.

## Three things must be true together

A surface is glass only if all three hold. Any one missing wastes the other two.

1. **Blur**, of what is behind the surface.
2. **Translucency**, because the blur renders *behind* the surface and an
   opaque background hides it completely.
3. **A hairline.** A 1px stroke at the edge is what separates glass from
   translucent grey. Without a boundary the surface dissolves into whatever is
   behind it.

This has been the shape of every FacetUI surface so far, and each time one half
was delivered without the other the result looked worse than doing nothing.

## Tint comes from the system, never from us

> The FacetUI move is **neutral-to-accent**, not dynamic-to-fixed.

Blur alone is grey and muddy. A glass surface needs a tint — but the tint is
pulled **from the platform's own wallpaper-derived palette**, so the panel
samples the wallpaper rather than flattening it.

Platforms usually put large surfaces on a neutral grey ramp. FacetUI moves them
to the muted *accent* ramp: the same dynamic palette, read off a tinted ramp
instead of a grey one. The muted ramp rather than the loud one, because large
areas want it.

Replacing a dynamic colour with a fixed literal is the opposite of this, and it
is a mistake this project has actually made and had to correct. The only
defensible reason is a surface that must be translucent where the platform can
only apply alpha to a literal — and that trade-off is named where it is taken,
never silently.

## Only windows can blur

A surface can blur what is behind it **only if it is a window**. Views inside a
window cannot: a view can blur its own content, not what is painted beneath it
in the same surface.

This is the line that decides what can be glass and what can only be tinted, and
it is not a platform quirk — it holds anywhere with a compositor. Dialogs,
menus, keyboards and system panels are windows, and can be glass. An app's own
toolbar, cards and list backgrounds are views, and can only be tinted unless the
application itself does the work.

Say which side of that line a surface is on before promising it glass.

## The mark

A regular octagon: corner cut `100/(2+√2) = 29.289`, all eight sides `41.421`.
Eight crown facets around a flat table, lit from one direction.

The facets are the subject when the mark is large — a boot screen — and a bezel
when it is small, at which point the table grows and the middle is left calm so
a glyph on top of it stays readable. Eight facets' worth of value variation
under a thin glyph at 48dp makes the glyph unreadable.
