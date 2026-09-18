# FacetUI RRO overlays

Resource-only changes. No recompile, so these work against a prebuilt GSI.

| Overlay | Target package | Reaches |
|---|---|---|
| `FacetUISystemUI` | `com.android.systemui` | Shade, notifications, lockscreen, volume, power menu, bottom sheets |
| `FacetUIFramework` | `android` | SurfaceFlinger blur quality, the octagonal icon mask, **glass dialogs**, popup and menu panels |
| `FacetUILauncher` | `com.android.launcher3` | Homescreen folders, popups, organizer |
| `FacetUIIME` | `com.android.inputmethod.latin` | Virtual keyboard translucency |

## Validate before building

An overlay that names a resource its target does not define is **not** an error
at build time and **not** an error at runtime. `aapt2` links it, the overlay
installs, and the resource is simply never applied — the effect just does not
appear, with nothing in the logs.

```bash
tools/validate-overlays.py --systemui <frameworks/base> \
                           --launcher <Launcher3> --ime <LatinIME>
```

This is not theoretical: `shade_panel_base`, which FacetUI overrode on Android
16, does not exist on Android 17.

## Build

```bash
export ANDROID_JAR=$ANDROID_HOME/platforms/android-37/android.jar
export KEYSTORE=~/octagonos.jks KEYSTORE_PASS=...
./build.sh
```

## Overriding a style is not like overriding a value

An RRO replaces a style **wholesale**: the overlay's bag of attributes replaces
the target's rather than merging into it, so anything the original declared and
the override forgets is gone at runtime, with the app rendering subtly wrong and
nothing in the log.

That is why the dialog glass goes in at `Theme.Material.Dialog` and
`Theme.Material.Light.Dialog` — in the platform both are *empty*, so there is
nothing to lose, and every dialog variant in the system still inherits through
them.

`validate-overlays.py` enforces it anyway: every overridden style must keep its
parent and restate every item stock declares. Restating is correct whether a
given Android version merges or replaces, so the check does not depend on
winning that argument.

## Two things to know

**Some overrides are deliberately equal to stock.** `config_sf_slowBlur`,
`config_supportBlurredWallpaper`, `config_translucentStandalonePowerMenu` and
`reduce_workspace_blur_usage` already ship with the values FacetUI wants on
`lineage-24.0`. They are pinned anyway, because octagonOS is a GSI: it boots on
bases nobody here has seen, and a vendor targeting weaker hardware plausibly
flips them. The validator reports each as a warning rather than hiding it — that
is the intended outcome, not an oversight.

**Enablement is not automatic.** `android:isStatic` is deprecated, so an overlay
in `/product/overlay` may need enabling explicitly. `octagonos-formfactor.sh`
does that on first boot; confirm with:

```bash
adb shell cmd overlay list | grep -i facetui
```
