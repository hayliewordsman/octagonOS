# FacetUI RRO overlays

Resource-only changes. No recompile, so these work against a prebuilt GSI.

| Overlay | Target package | Reaches |
|---|---|---|
| `FacetUISystemUI` | `com.android.systemui` | Shade, notifications, lockscreen, volume, power menu, bottom sheets |
| `FacetUIFramework` | `android` | SurfaceFlinger blur quality, the octagonal icon mask, **glass dialogs**, popup and menu panels |
| `FacetUILauncher` | `com.android.launcher3` | Homescreen folders, popups, organizer |
| `FacetUIIME` | `com.android.inputmethod.latin` | Virtual keyboard translucency |
| `FacetUISettings` | `com.android.settings` | Settings surfaces, on FacetUI's palette |

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

## Per-app overlays are colour, not glass

The system overlays above can make surfaces glass because the surfaces they
touch are *windows* -- the shade, dialogs, menus, the keyboard -- and a window
can blur what is behind it.

An app's own headers, cards and list backgrounds are **views inside the app's
single window**, and Android has no backdrop blur for a view: a view can blur
its own content, not what is painted beneath it in the same window. So a
per-app overlay aligns the app's palette with FacetUI and stops there. Making
an app bar genuinely glass would need per-app code, not a resource.

Some apps narrow it further. Settings' own dialogs are AppCompat, bundled into
its APK rather than inherited from the platform, so the framework dialog glass
does not reach them; overriding a bundled AppCompat theme would mean restating
every item it declares, and its source is not in the tree to read. Left alone,
deliberately.

### One APK, more than one repository

A statically linked library's resources compile into the app that links it and
become overridable entries of *that* package. `FacetUISettings` names resources
that only exist in SettingsLib, which lives in `frameworks/base` --
`validate-overlays.py` checks both trees for that overlay, because checking the
app's own `res/` alone would report every one of them as missing.
