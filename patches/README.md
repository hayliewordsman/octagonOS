# Source patches

Changes that RRO overlays cannot express. Everything that *can* be an overlay
is one; see [`overlay/`](../overlay/).

| Patch | What it does |
|---|---|
| [`systemui/0001`](systemui/0001-facetui-specular-edge.patch) | `FacetEdgeShader` (AGSL) and a specular highlight along the top of the shade scrim |
| [`systemui/0002`](systemui/0002-facetui-rim-darkening.patch) | `FacetRimShader` (AGSL), **chained** onto the scrim's existing blur |
| [`systemui/0003`](systemui/0003-facetui-status-bar-icon-modes.patch) | Four status bar notification icon modes, including a neutral dot |
| [`ime/0001`](ime/0001-facetui-glass-keyboard-window.patch) | Blurs behind the virtual keyboard window |
| [`iconloader/0001`](iconloader/0001-facetui-icon-glass.patch) | Recomposes **every** app icon onto the FacetUI glass |

Apply the SystemUI patches in order; `0002` builds on `0001`.

## Applying

Always `--check` first, and believe it if it fails rather than forcing it.

```bash
cd frameworks/base
git apply --check ~/octagonOS/patches/systemui/0001-facetui-specular-edge.patch
git apply         ~/octagonOS/patches/systemui/0001-facetui-specular-edge.patch
```

Generated against, and verified to apply to, pristine checkouts of:

- `LineageOS/android_frameworks_base` at `lineage-24.0` (`017d6ac3f`)
- `LineageOS/android_packages_inputmethods_LatinIME` at `lineage-24.0` (`0f72f94`)
- `LineageOS/android_frameworks_libs_systemui` at `lineage-24.0` (`0e181d3`)

They should port across nearby branches, but a tree carrying its own SystemUI
changes may move the context lines. `ScrimView.onDraw` is the hunk most likely
to drift.

## Verification status

- all five patches pass `git apply --check` against pristine trees, the three
  SystemUI ones in sequence, and then apply
- every symbol introduced is declared or imported, checked explicitly. This is
  worth doing rather than assuming: in the Android 16 original, `0001`'s import
  was missing on the first attempt and would not have compiled, despite the
  diff looking healthy

**Not compiled and not run.** There is no Android SDK or build tree in the
environment this was written in. Treat it as reviewed-but-unbuilt: expect to fix
something on the first compile. The AGSL is the likeliest thing to fail, because
it is a string compiled at runtime rather than anything a build checks — see
[../docs/status.md](../docs/status.md).

## What `0003` had to change for Android 17

`ActiveNotificationIconModel` lost `whenTime` and `isSilent` this release. The
Android 16 patch sorted by timestamp before `take(1)`, because the source is a
`Set` and taking one element of an unordered collection picks an arbitrary
member — the dot would flicker between notifications on every emission.

With no timestamp available, this sorts by `notifKey` instead. Not
chronological, but *stable*, which is the property that actually matters here:
mode 2 replaces the icon with a plain circle, so which notification backs the
dot is not observable. Only whether it keeps changing is.

Mode 1 filters on `isAmbient`, which the model does still carry.

## What `iconloader/0001` hooks, and why there

`IconProvider.getIcon(PackageItemInfo, ApplicationInfo, int)` -- the one private
method every icon load funnels through, and the only place left in the pipeline
that still has the component to key on.

It composes a real `AdaptiveIconDrawable` (glass tile as background, the app's
own foreground on top) rather than filtering the finished bitmap. A post-filter
would have to be re-applied by every consumer that rasterises an icon, and would
defeat monochrome extraction, shadow generation and the mask; composing an
adaptive icon means all of those keep working with no further changes anywhere.

The calendar and clock packages are deliberately excluded: both draw their own
icon contents and swap them as the date and time change, so wrapping them would
freeze them at whatever they showed when the icon was first loaded.

See [../docs/icons.md](../docs/icons.md).
