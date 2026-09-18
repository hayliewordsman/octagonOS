# Icons

Before this, app icons were the one part of octagonOS that FacetUI did not
reach. The system was glass and the app drawer was whatever each app happened
to ship — which on a real device is a grid of unrelated circles, squares and
squircles sitting on top of a glass homescreen.

FacetUI now applies to all of them.

![The FacetUI icon set](preview/facetui-icons.png)

## Three layers, and only the middle one is a list

**1. The shape.** `overlay/FacetUIFramework` sets `config_icon_mask` to a
regular octagon. `AdaptiveIconDrawable` parses that string into the clip path it
applies to *every* adaptive icon on the device, so this one resource makes every
adaptive icon octagonal — system, preinstalled and user-installed alike, with
nothing done to any of them individually.

The path is a true regular octagon: corner cut `100/(2+√2) = 29.289`, which makes
all eight sides exactly `41.421` long. It is also strictly larger than the circle
Android documents as the safe zone, so no icon drawn correctly for the stock mask
loses anything to it.

**2. The curated pack.** `iconpack/` maps components to purpose-drawn FacetUI
glyphs. Currently 40 components across 22 icons, covering what an
AOSP/LineageOS-derived Android 17 GSI actually ships.

**3. The engine.** `patches/iconloader/0001`. Everything the pack does not
curate — which is every app the user will ever install — is recomposed onto the
same glass. **This is the layer that makes the coverage total.** Without it,
layer 2 is a list somebody has to keep extending; with it, the list is only an
upgrade for apps worth hand-drawing.

## How the engine works

It hooks `IconProvider.getIcon(PackageItemInfo, ApplicationInfo, int)` — the one
private method every icon load funnels through, and the only place in the
pipeline that still has the component to key on.

```
component -> curated icon?  -> return it, already glass
          -> otherwise      -> AdaptiveIconDrawable(glass tile, app's foreground)
```

Three decisions in that are worth stating:

**It builds a real `AdaptiveIconDrawable` rather than filtering the finished
bitmap.** A post-filter would have to be re-applied by every consumer that
rasterises an icon, and would defeat monochrome extraction, shadow generation
and the mask. Composing an adaptive icon means every one of those keeps working
on FacetUI icons exactly as it does on stock ones, with no further changes
anywhere.

**For an app that already ships an adaptive icon, only its foreground is
taken.** Keeping its background would put a coloured square inside the octagon.
Dropping it puts the app's own glyph on FacetUI's surface, which is the whole
point — the app stays recognisable, the material becomes ours.

**The calendar and clock are excluded.** Both draw their own icon contents and
swap them as the date and time change; wrapping them would freeze them at
whatever they showed when the icon was first loaded. This is the kind of thing
that looks fine for a day and then is quietly wrong forever.

## The tile is loaded, not generated twice

The glass octagon is rendered by `iconpack/make-icons.py` from
`shared/facetui/facet_math.py` — FacetUI's AGSL, transcribed. The engine then
loads that rendered tile *out of the pack* rather than generating its own.

So a curated icon and a procedurally themed one are the same asset. There is no
second, approximate glass in Kotlin to keep in sync with the first, and if the
shader constants change, the boot animation, the shade and every app icon move
together.

It also means the engine's dependency is explicit: **with the pack absent it
does nothing at all** and icons are left stock. A missing pack degrades to plain
Android, not to a half-themed system.

## Why the tile is a raster and the glyphs are not

The edge highlight and the rim darkening are exponential falloffs. A vector
drawable has gradients, but nothing that expresses `exp(-d²)`, so a vector tile
would be an approximation of the material rather than the material.

A glyph has the opposite problem: it is flat, and rasterising it would make it
soft at exactly the sizes a launcher asks for. So glyphs are vectors and the
tile is a PNG at five densities. The tile is the pack's only raster and
therefore the whole of its size cost — about 550 KB for the lot.

## The calm centre, and fitting glyphs to it

The tile's flat table is much larger than the boot animation's (`0.84` against
`0.46`). On the boot screen the facets are the subject. On an icon they are a
bezel, and the subject is the glyph on top of them.

Eight facets' worth of value variation running underneath a thin glyph at 48dp
makes the glyph unreadable. So the crown is pushed out to a ring and the middle
is left calm.

**`TABLE_FRAC` and `GLYPH_SCALE` are a pair and cannot be set independently.**
Together they decide whether a glyph sits on calm glass or straddles the girdle
hairline. The first version of this pack got that wrong: the table edge sat at
`25.2` and **fifteen of the twenty-five glyphs ran over it onto the facets** —
the calm centre existed, but most glyphs were not inside it.

The reason it survived a verification pass is worth recording. The check at the
time measured glyphs against Android's *mask* safe zone, radius `33`, and every
glyph cleared it — the worst at `32.4`. But the mask was never the binding
constraint. The table is smaller than the mask, and nothing was measuring
against it, so the check passed while the design was visibly broken.

It is now `0.84` and `0.59`: the widest glyph reaches `27.9` against a table
edge of `30.2` and a mask safe radius of `33`. Both bounds are checked on every
build, and the table one is the one that bites.

## Drawing glyphs

Authored as **outlines on a 100x100 viewport**, never as strokes: a stroked path
scales by line width and an outlined one does not, so the same data has to work
at 48px and at 512px.

The fill is `evenOdd`, so **overlapping subpaths are XORed, not merged**. That
is what makes a gear's centre hole work with no extra machinery. It is also why
`weather` is a disc with separate rays rather than the obvious cloud: a cloud
drawn as several overlapping circles punches holes in itself.

## Verifying

```bash
tools/verify-iconpack.py iconpack/FacetUIIcons
```

Checks the failures that are silent — where the app simply keeps its stock icon
and nothing says why:

1. every generated XML file is well-formed
2. every appfilter entry names a drawable the pack actually contains
3. every adaptive icon's background, foreground and monochrome layers resolve
4. the tile exists at every density, is square, and has real transparency — a
   tile that came out opaque would show as a square behind every octagon
5. every glyph stays inside **both** bounds that constrain it, once its group
   transform is applied: Android's mask safe zone, and — the tighter one —
   FacetUI's own table
6. nothing in the pack is orphaned

Check 5 is the one that earns its place, and it earns it twice.

The glyphs are placed by a `scale`/`pivot`/`translate` group in each vector, so
getting that transform wrong moves all 22 at once. The mask bound caught the
first problem: the widest glyph at `31.7` against a safe radius of `33`, inside
but with 4% to spare, which would not have survived a launcher using a tighter
mask. The scale came down from `0.72` to `0.68` on that.

The table bound caught the second, and larger, one — see above. It measures
against the octagon rather than a circle, because the table *is* an octagon and
a plain radius over-reports in the vertex directions, rejecting artwork that
actually fits. It reads the table radius out of the generator rather than
keeping its own copy, so the number being checked against is the number the
tile was drawn from.

Both were verified to fail on purpose before being trusted: regenerating the
pack with the old constants makes the table check name all fifteen offending
glyphs and exit non-zero, while the mask check still reports `32.4 of 33` and
passes. That contrast is the whole argument for having the second bound.

## Status

Generated and verified here; **never built into an APK and never seen on a
device.** `aapt2` needs an Android SDK, which this environment does not have.
The engine patch applies cleanly to a pristine `lineage-24.0` icon loader and
has never been compiled. See [status.md](status.md).
