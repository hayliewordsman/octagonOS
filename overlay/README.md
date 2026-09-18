# FacetUI RRO overlays

Resource-only changes. No recompile, so these work against a prebuilt GSI.

| Overlay | Target package | Reaches |
|---|---|---|
| `FacetUISystemUI` | `com.android.systemui` | Shade, notifications, lockscreen, volume, power menu, bottom sheets |
| `FacetUIFramework` | `android` | SurfaceFlinger blur quality |
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
