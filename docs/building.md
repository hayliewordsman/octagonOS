# Building octagonOS

Two paths. Pick by how much of the glass you need and how much disk you have.

| | Tier 2 | Tier 3 |
|---|---|---|
| What you get | Blur, tint, depth model, glass notifications and lockscreen, boot animation | All of that, plus the AGSL shaders and the glass keyboard |
| Needs | A prebuilt Android 17 GSI, the Android SDK for `aapt2` | A full source tree |
| Disk | A few GB | **250-400 GB** |
| Time | Minutes | 1-4 hours for a first build |

Tier 2 is genuinely most of the look, and Android 17 makes it more so than
Android 16 did -- notifications and the lockscreen moved into resources this
release. See [facetui.md](facetui.md).

**Nothing below has been run.** No image has been built from this repository.
See [status.md](status.md).

## Tier 2 -- from a prebuilt GSI

You need an Android 17 (API 37, `CINNAMON_BUN`) arm64 GSI. Any will do as a
base; a microG or de-Googled one keeps the privacy posture octagonOS inherits
from titan2e-eos.

```bash
# 1. Validate the overlay sources against the trees they target. An overlay
#    naming a resource its target does not define links, installs, and then
#    silently does nothing -- this is the check that catches it.
tools/validate-overlays.py \
    --systemui ~/src/frameworks_base \
    --launcher ~/src/Launcher3 \
    --ime      ~/src/LatinIME

# 2. Build the overlays. Needs the Android SDK.
export ANDROID_JAR=$ANDROID_HOME/platforms/android-37/android.jar
export KEYSTORE=~/octagonos.jks KEYSTORE_PASS=...
overlay/build.sh

# 3. Build and verify the boot animation. No SDK needed.
bootanimation/build.sh
```

Then inject everything into the image. octagonOS does not ship its own
injector: `tools/inject-ime.sh` in
[titan2e-eos](https://github.com/hayliewordsman/titan2e-eos) already does
exactly this job -- ext4 and EROFS, raw and sparse, both root layouts, SELinux
labelling on every injected file, and verification afterwards -- and
reimplementing it here would mean maintaining two copies of the fiddly part.

```bash
titan2e-eos/tools/inject-ime.sh \
  --image  android-17-arm64-gsi.img \
  --out    octagonos-1.0-beta.img \
  --apk    <your physical-keyboard IME>.apk \
  --name   Pastiera \
  --ime-id <read it, do not guess -- see below> \
  --add-file overlay/out/FacetUISystemUI.apk:product/overlay/FacetUISystemUI.apk \
  --add-file overlay/out/FacetUIFramework.apk:product/overlay/FacetUIFramework.apk \
  --add-file overlay/out/FacetUILauncher.apk:product/overlay/FacetUILauncher.apk \
  --add-file overlay/out/FacetUIIME.apk:product/overlay/FacetUIIME.apk \
  --add-file bootanimation/out/bootanimation.zip:system/media/bootanimation.zip \
  --add-file product/octagonos/bin/octagonos-formfactor.sh:system/bin/octagonos-formfactor.sh \
  --add-file product/octagonos/etc/init/octagonos-formfactor.rc:system/etc/init/octagonos-formfactor.rc \
  --set-prop ro.surface_flinger.supports_background_blur=1 \
  --set-prop ro.octagonos.version=1.0-beta \
  --set-prop ro.octagonos.ui=FacetUI \
  --set-prop ro.adb.secure=1 \
  --set-prop ro.debuggable=0
```

### Three flags that are not optional

| Flag | Why |
|---|---|
| `ro.surface_flinger.supports_background_blur=1` | Without it SurfaceFlinger does no cross-window blur and the whole design collapses to flat translucency. It is a property, not a resource, so no overlay can deliver it |
| `ro.adb.secure=1` | GSIs commonly ship this as `0`, which disables ADB authorisation entirely: any USB host attaches without a prompt |
| `ro.debuggable=0` | Commonly shipped as `1`, which allows `adb root` |

### Read the IME component, do not copy it

A keyboard's `applicationId` and its IME class need not share a namespace --
`applicationIdSuffix` does not move the Java package. The short form
(`pkg/.SomeService`) expands to a class that may not exist, and the result is a
keyboard that installs, flashes and boots while **silently never activating**.

```bash
aapt2 dump xmltree <keyboard.apk> --file AndroidManifest.xml | grep -A3 service
# or, with no SDK: python3 titan2e-eos/tools/axml.py <keyboard.apk>
```

## Tier 3 -- from source

```bash
repo init -u https://github.com/LineageOS/android.git -b lineage-24.0
repo sync -c -j8 --no-clone-bundle --no-tags
```

`lineage-24.0` is Android 17: `Build.VERSION_CODES.CINNAMON_BUN` is 37. Confirm
it on the tree you sync rather than trusting this page, because branch-to-version
mappings are exactly the sort of thing that goes stale:

```bash
grep -n 'CINNAMON_BUN' frameworks/base/core/java/android/os/Build.java
```

### Apply the patches

Always `--check` first, and believe it if it fails rather than forcing it.

```bash
cd frameworks/base
for p in ~/octagonOS/patches/systemui/*.patch; do
    git apply --check "$p" && git apply "$p" && echo "applied $(basename "$p")"
done
cd ../..

cd packages/inputmethods/LatinIME
git apply --check ~/octagonOS/patches/ime/0001-facetui-glass-keyboard-window.patch
git apply         ~/octagonOS/patches/ime/0001-facetui-glass-keyboard-window.patch
cd ../../..
```

Apply the SystemUI patches in order; `0002` builds on `0001`.

These were generated against `LineageOS/android_frameworks_base` and
`android_packages_inputmethods_LatinIME` at `lineage-24.0`, and verified to
apply to pristine checkouts of both. They should port across nearby branches,
but a tree carrying its own SystemUI changes may move the context lines --
`ScrimView.onDraw` is the hunk most likely to drift.

### Build

**Do not build a GSI to iterate on the UI.** Build the emulator target: a GSI
exists to run on a real phone, and for UI work it adds an hour and a flashing
step that tell you nothing extra.

```bash
source build/envsetup.sh
lunch sdk_phone64_x86_64-userdebug      # or aosp_cf_x86_64_phone for Cuttlefish
m -j$(nproc)
emulator -writable-system
```

Set the property in the emulator too, or the blur path never runs at all:

```bash
adb root && adb remount
adb shell setprop ro.surface_flinger.supports_background_blur 1
adb shell stop && adb shell start
```

For the GSI itself, once the look is settled:

```bash
lunch lineage_arm64_bvS-userdebug       # generic A/B arm64; no device tree needed
m -j$(nproc) systemimage
```

### Where the disk goes

| | |
|---|---|
| `.repo/` -- git objects for ~600 projects | 80-120 GB |
| the working tree checked out from them | 60-90 GB |
| **`repo sync` total** | **150-200 GB** |
| `out/` | 100-200 GB |
| **Total** | **250-400 GB** |

The part people underestimate is that `.repo` and the checkout both exist at
once, so the source is stored twice. `-c --no-tags` trims the history fetched,
not that duplication. These are standard figures for a tree of this era, not
something measured here.

### If you do not have 250-400 GB

The sync alone exceeds 130 GB, so a build fails before it starts compiling.
Cheapest first:

1. **Validate the shaders instead of building the ROM.** The riskiest untested
   thing is whether the AGSL compiles at all. titan2e-eos ships
   `tools/shader-check/`, a ~20 MB app that compiles both shaders and draws
   them on any Android 13+ emulator. The shader bodies are unchanged in
   octagonOS, so it applies directly.
2. Build on an external SSD. A 1 TB USB SSD is sufficient; the build is I/O
   bound, so a spinning disk will drag.
3. Rent a cloud VM for an afternoon, which is what many ROM developers do.

## Confirming it worked, on a device

```bash
adb shell getprop ro.surface_flinger.supports_background_blur \
                  ro.octagonos.version ro.octagonos.ui \
                  persist.octagonos.formfactor
adb shell cmd overlay list | grep -i facetui
```

All four overlays should be listed and enabled, and `persist.octagonos.formfactor`
should read `keyboard` or `slab` correctly for the phone in your hand.

Then try connecting ADB from an unauthorised host. **If it attaches without
prompting, the hardening did not take effect** and the exposure is still open.
