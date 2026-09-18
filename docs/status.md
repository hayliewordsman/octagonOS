# What is built, what is verified, and what is not

octagonOS is a **beta**, and beta here means a specific thing: the parts below
marked *built* were produced and checked in this repository; the parts marked
*unbuilt* have never been compiled; and **nothing at all has run on a phone.**

This page is the ledger. Nothing else in the repository should claim more than
it does.

## Verified here

These were run, and the output checked, in the environment this repository was
written in.

| Piece | Evidence |
|---|---|
| Boot animation | Built. `tools/verify-bootanimation.py` passes: 93 entries all STORED, every frame 720x720, every frame border equal to the declared background, loop wrap step 1.10 against a typical step of 1.28, 59 MiB resident against a 64 MiB budget |
| Boot animation memory model | The claim that a looping part holds a GL texture per frame for the whole boot was read out of `frameworks/base/cmds/bootanimation/BootAnimation.cpp` on `lineage-24.0`, not assumed: `glGenTextures` under `if (part.count != 1)`, and the matching `glDeleteTextures` only after the animation ends |
| `desc.txt` format | Checked against that file's own parser, including that a `#RRGGBB` background is accepted for a `p`/`c` part and is what `glClearColor` receives |
| SystemUI patches 0001-0003 | `git apply --check` passes in sequence against a pristine `LineageOS/android_frameworks_base` `lineage-24.0` checkout, then applies |
| IME patch | `git apply --check` passes against a pristine `LineageOS/android_packages_inputmethods_LatinIME` `lineage-24.0` checkout, then applies |
| Every symbol the patches introduce | Checked to be imported or declared, including `Icon.createWithResource(String, int)` being the public overload and not the one marked "Do not use", and `isAmbient`/`notifKey` existing on `ActiveNotificationIconModel` |
| Overlay resources | `tools/validate-overlays.py` passes: all 28 overridden resources exist in their target trees, with the patch-provided ones exempted by name |
| Form-factor detection | `tools/test-formfactor-detect.sh` passes 7 cases, including a bitmask whose top bit is set and therefore wraps negative in 64-bit shell arithmetic |

## Not verified

| Piece | State |
|---|---|
| **Any of it, on hardware** | **Nothing here has been near a phone.** No device, no emulator |
| The patches, compiled | They apply. They have never been built. Expect to fix something on the first compile |
| The AGSL, compiled | The two shaders have never been handed to a shader compiler. This is the single likeliest thing to fail first |
| The overlays, built | No Android SDK in this environment, so `aapt2` never ran. The sources validate; the APKs do not exist |
| Whether the overlays take effect | `android:isStatic` is deprecated, so an overlay in `/product/overlay` may need `cmd overlay enable`. The first-boot script does that, but the script has not run |
| Whether blur renders acceptably | `ro.surface_flinger.supports_background_blur=1` makes SurfaceFlinger attempt blur. Whether it holds frame rate is a per-device measurement nobody has taken |
| SELinux for the first-boot service | The service ships with no seclabel, deliberately. On an enforcing build it will not have the permissions it needs. Policy is owed |
| The GSI itself | **No image has been built.** A GSI needs roughly 250-400 GB and many CPU-hours; see [building.md](building.md) |

## The two things most likely to break first

**The AGSL.** Everything else in the Tier 3 path is ordinary Java and Kotlin
that a compiler will check. The shaders are strings, compiled at runtime by
Skia, and a mistake in them surfaces as a blank surface or a crash on the first
frame, not as a build error. titan2e-eos ships `tools/shader-check/`, a ~20 MB
Android app that compiles this AGSL without a 300 GB tree; that is the cheapest
way to retire this risk and it applies unchanged here, because the shader bodies
are unchanged.

**The first-boot service.** It touches three things that SELinux guards, on a
build where it has no policy of its own. The likeliest outcome on an enforcing
image is that it runs, is denied, and the overlays are never enabled -- with the
only symptom being that the system looks entirely stock.

## Where the risk is not

Worth saying, because it is where the effort went and it is now cheap to
re-check:

- the resource names. Android 17 moved several of these, and one -- the shade
  panel tint that titan2e-eos overrode on Android 16 -- **no longer exists.**
  `validate-overlays.py` catches that class of drift, which otherwise fails
  silently: an overlay naming a resource its target does not define links,
  installs, and does nothing
- the boot animation's memory cost, which is the failure this design most
  plausibly would have shipped with, and is now measured against a budget

## Open items

- [ ] **Compile something.** Nothing here has been built
- [ ] Run `tools/shader-check` (from titan2e-eos) against the two AGSL shaders
- [ ] Write an SELinux domain for `octagonos-formfactor`
- [ ] Build the overlays and confirm `cmd overlay list` shows all four
- [ ] Measure blur cost on a real GPU before recommending `config_sf_slowBlur=false`
- [ ] Confirm the boot animation centres correctly on a near-square display,
      which is the case the square canvas exists for and the one no emulator
      profile covers by default
