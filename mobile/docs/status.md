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
| Icon engine patch | `git apply --check` passes against a pristine `LineageOS/android_frameworks_libs_systemui` `lineage-24.0` checkout, then applies. Every Android API it calls checked to exist with the signature used -- `InsetDrawable(Drawable, float)`, `AdaptiveIconDrawable(Drawable, Drawable)`, `Resources.getDrawableForDensity`, and `XmlResourceParser` implementing `AutoCloseable` |
| Icon pack | **Generated and verified.** `tools/verify-iconpack.py` passes: 68 resource files well-formed, 40 appfilter entries all resolving, 22 adaptive icons with every layer resolving, the tile present at 5 densities with a real alpha channel, no orphans, and every glyph inside both bounds -- worst at 28.1 of a 33-unit mask radius and 27.9 of a 30.2 table edge |
| The glyph bounds check itself | Verified to fail on purpose: regenerating the pack with the pre-fix constants makes it name all fifteen offending glyphs and exit non-zero, while the mask-only check it replaced still passes at 32.4 of 33 |
| Octagon icon mask | The path is a true regular octagon, checked numerically: all eight sides 41.4214 |
| Dialog glass | The theme path was read out of `PhoneWindow.generateLayout()` rather than assumed: all three blur attributes are consumed there unconditionally, and no platform theme sets any of them. `Theme.Material.Dialog` and its Light twin were confirmed empty in the platform, so overriding them risks losing nothing |
| Popup glass patch | `git apply --check` passes on a pristine `frameworks/base`, both alone and after the three SystemUI patches. Every API it calls verified present with the signature used, including both `addCrossWindowBlurEnabledListener` overloads |
| The popup limitation | Checked rather than assumed: `Dialog` builds a `PhoneWindow`, and `PopupWindow` contains no blur API at all. That is why menus needed `patches/framework/0001` rather than an overlay entry |
| Style and drawable overrides | `validate-overlays.py` now covers both. All three new failure modes verified to fail on purpose: a dropped style item (named all 20), a changed parent, and a drawable absent from the target |
| Every symbol the patches introduce | Checked to be imported or declared, including `Icon.createWithResource(String, int)` being the public overload and not the one marked "Do not use", and `isAmbient`/`notifKey` existing on `ActiveNotificationIconModel` |
| Overlay resources | `tools/validate-overlays.py` passes: every overridden resource exists in its target tree, with the patch-provided ones exempted by name |
| Overlays and icon pack, linked | **Built with `aapt2`, signed with `apksigner`, signatures verified.** Building found two real bugs a name check cannot see: framework attributes used unqualified, and a private framework parent style referenced without the `@*android:` form. Both would have failed for anyone who tried to build |
| Form-factor detection | `tools/test-formfactor-detect.sh` passes 7 cases, including a bitmask whose top bit is set and therefore wraps negative in 64-bit shell arithmetic |
| **The AGSL, compiled** | **Both shaders compile** under Skia's own SkSL compiler, via `tools/validate-shaders.py`. The compiler was first proven awake on five deliberately broken shaders -- undeclared variable, type mismatch, missing `main`, syntax error, wrong `main` signature -- all rejected, and a valid one accepted |
| FacetUI constants, everywhere | The same tool checks that `facet_math.py` still matches the AGSL's own literals, and that the four parameter values agree across the shader defaults, `ScrimView` and both generators. Verified to fail on purpose by drifting one of each |

## Not verified

| Piece | State |
|---|---|
| **Any of it, on hardware** | **Nothing here has been near a phone.** No device, no emulator |
| The patches, compiled | They apply. They have never been built. Expect to fix something on the first compile |
| The AGSL, on Android's own compiler | Skia has compiled both, but AGSL is Android's *binding* of Skia runtime effects and this is not the Skia in any given release. Strong evidence, not proof |
| ~~The overlays, built~~ | **All eight build and sign.** `aapt2` linked them against android-35 and `apksigner` verified each one |
| ~~The icon pack, built~~ | **Builds and signs.** 240 KB |
| Whether icons actually look right on a device | The preview renders the adaptive icon's own group transform, so it should match -- but it is Pillow's rasteriser, not Android's. Thin strokes and the `evenOdd` fill are where the two are most likely to disagree |
| Whether the overlays take effect | Now declared in `/product/overlay/config/config.xml`, which `OverlayConfigParser` reads at boot — the attribute handling was read out of that parser rather than assumed. Still never run |
| The cost of blur-behind on dialogs | `windowBlurBehindEnabled` blurs the entire screen behind every dialog. That is the most expensive thing FacetUI asks for, and on an unmeasured GPU it is the first candidate to turn off |
| Whether blur renders acceptably | `ro.surface_flinger.supports_background_blur=1` makes SurfaceFlinger attempt blur. Whether it holds frame rate is a per-device measurement nobody has taken |
| ~~SELinux for the first-boot service~~ | **Resolved by deletion.** The service needed privilege a Tier 2 image cannot grant. Overlay enablement is now declarative, the IME default belongs to the injection tool, and nothing read the property, so the service had no remaining job |
| The GSI itself | **No image has been built.** A GSI needs roughly 250-400 GB and many CPU-hours; see [building.md](building.md) |

## The things most likely to break first

**~~The AGSL.~~ Retired, mostly.** This was the top of this list for the whole
project: the shaders are strings compiled at runtime by Skia, so a mistake in
them is a blank surface or a first-frame crash rather than a build error.

Both now compile under Skia's own SkSL compiler
(`tools/validate-shaders.py`). What remains is the gap between SkSL and AGSL,
which is Android's binding of it, and between this Skia and the one in a given
Android release. titan2e-eos's on-device harness is what closes that, and it
applies unchanged here because the shader bodies are unchanged.

**The icon engine, on a device with many apps.** It runs inside the icon load
path for every app on the system. The composition itself is cheap -- an
`AdaptiveIconDrawable` around two existing drawables -- and the results are
cached by the launcher's own icon cache, but nothing here has measured a cold
app-drawer open with a few hundred apps installed.

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
- [x] Compile the AGSL. Both shaders pass Skia's SkSL compiler
- [ ] Run titan2e-eos's on-device harness to confirm against Android's own AGSL
      compiler, which is the only thing that settles it
- [x] SELinux domain for `octagonos-formfactor` — not written; the service it
      was for no longer exists
- [ ] Build the overlays and confirm `cmd overlay list` shows all four
- [ ] Measure blur cost on a real GPU before recommending `config_sf_slowBlur=false`
- [ ] Confirm the boot animation centres correctly on a near-square display,
      which is the case the square canvas exists for and the one no emulator
      profile covers by default
- [ ] Measure a dialog open with blur-behind on. If it drops frames, drop
      `windowBlurBehindEnabled` first and keep `windowBackgroundBlurRadius`
- [ ] Retune the popup fill alpha once the patch is running: it is currently a
      compromise between the blurred and unblurred cases
- [ ] Look at the icons on a real launcher at real density. 48dp is much smaller
      than any preview here, and legibility at that size is the whole question
- [ ] Check the icon engine's cost on a cold app-drawer open. It composes an
      adaptive icon per app, which should be cheap and cached, but "should be"
      is not a measurement
