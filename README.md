# octagonOS

An Android 17 GSI built on **FacetUI**, a glass design language, for phones with
**physical keyboards** and for **slabs** — from one image.

![The octagonOS boot animation, from assembly through the looping light sweep](docs/preview/bootanimation-arc.png)

*The boot animation, rendered by evaluating FacetUI's own shader maths.*

## Status — read this first

**Beta, and nothing here has run on a phone.** No device, no emulator, no image
built. What *has* been built and checked is listed below; the full ledger,
including everything that has not, is in **[docs/status.md](docs/status.md)**.

| Piece | State |
|---|---|
| Boot animation | **Built and verified.** 8.9 MiB, 92 frames, all checks pass |
| SystemUI patches (3) | **Apply cleanly** to a pristine `lineage-24.0` tree. Never compiled |
| Keyboard glass patch | **Applies cleanly** to a pristine LatinIME tree. Never compiled |
| RRO overlays (4) | Sources **validate** against their target trees. Never built — no SDK here |
| Form-factor detection | **7/7 tests pass**, against synthetic bitmasks |
| The AGSL shaders | **Never handed to a shader compiler.** Most likely thing to fail first |
| The GSI itself | **Not built.** Needs 250–400 GB |

Base is `lineage-24.0`, confirmed Android 17 by
`Build.VERSION_CODES.CINNAMON_BUN == 37` in the tree itself, not by assumption.

## What FacetUI reaches

Glass is applied as a system, not a theme — the point is that surfaces at the
same visual depth are the same material, even where Android gives them
unrelated resource names.

| Surface | How | Tier |
|---|---|---|
| Notification shade | Blur radii, transparent scrim | overlay |
| **Push notifications** | `notification_background_blur_radius` | overlay |
| **Lockscreen** | Shortcut and fingerprint blur | overlay |
| **Homescreen** | Folder, popup and organizer blur, retuned to match the shade | overlay |
| **Virtual keyboard** | Translucent background **and** a blurred window | overlay **+** patch |
| Volume, power menu, bottom sheets | Pulled onto one depth tier | overlay |
| Shade edge and rim | Two AGSL shaders | patch |
| Status bar icons | Four modes, incl. a neutral privacy dot | patch |
| Boot animation | Rendered from the same shader maths | generated |

Notifications and the lockscreen are overlays rather than patches because
**Android 17 exposes far more blur as resources than Android 16 did** — work
that needed a SystemUI recompile a release ago now does not. That finding, and
the three places Android 17 moved *against* us, are in
[docs/facetui.md](docs/facetui.md).

## Keyboards and slabs, from one image

A GSI cannot be built per device, and the difference is not knowable at build
time, so it is resolved on first boot: read the kernel's input table, look for
three full letter rows in a device's `KEY` capability bitmask, and set
`persist.octagonos.formfactor` to `keyboard` or `slab`.

Requiring all three rows is what separates a real keyboard from a volume rocker
— both advertise `EV_KEY`. The arithmetic is tested in
`tools/test-formfactor-detect.sh`, including a numeric keypad, a two-row
keyboard, and a bitmask that wraps negative in 64-bit shell arithmetic.

## Layout

| Path | What it is |
|---|---|
| [`bootanimation/`](bootanimation/) | The generator, and `facet_math.py` — FacetUI's AGSL transcribed to NumPy |
| [`overlay/`](overlay/) | Four RRO overlays: SystemUI, framework, launcher, IME |
| [`patches/`](patches/) | Source patches for what resources cannot express |
| [`product/`](product/) | Product makefile, first-boot form-factor service |
| [`tools/`](tools/) | Verifiers — boot animation, overlays, form-factor detection |
| [`docs/`](docs/) | [status](docs/status.md) · [FacetUI](docs/facetui.md) · [building](docs/building.md) · [boot animation](docs/bootanimation.md) |

## Quick start

```bash
bootanimation/build.sh        # builds and verifies; no Android SDK needed

tools/validate-overlays.py --systemui <frameworks/base> \
                           --launcher <Launcher3> --ime <LatinIME>
tools/test-formfactor-detect.sh
```

Full instructions, both tiers: [docs/building.md](docs/building.md).

## Three findings worth carrying forward

**A looping boot animation part is resident for the whole boot.**
`bootanimation` allocates a GL texture per frame for any part with `count != 1`
and frees them only when the animation ends. An unremarkable 84-frame loop at
1080×1080 would hold **374 MiB** of texture memory on a phone that has barely
mounted `/data`, with nothing to warn you. octagonOS's loop is 30 frames at
720×720 — 59 MiB — and the intro and outro are long because, at `count == 1`,
they are free. Read out of `BootAnimation.cpp`, not assumed.

**An overlay naming a resource its target does not define fails silently.** It
links, installs, and does nothing. `shade_panel_base`, which FacetUI overrode on
Android 16, does not exist on Android 17 — so
[`tools/validate-overlays.py`](tools/validate-overlays.py) checks every override
against the real tree. It also found that three tint overrides had become
redundant; those were deleted rather than kept as decoration.

**Translucent is not glass.** An RRO can make the keyboard translucent, but the
app behind then shows through unmodified, which reads as a tinted window.
Blurring what is behind is a window property, reachable only from code — so the
glass keyboard is deliberately half overlay, half patch, and **needs both**.

## Credit

FacetUI is from
**[titan2e-eos](https://github.com/hayliewordsman/titan2e-eos)**, where it was
designed against Android 16, along with the rule that governs it:

> On a blurred surface, any effect that works by **displacing samples** is
> invisible. Only effects that **modify values** survive the blur.

That repository's `tools/inject-ime.sh` is also what octagonOS uses to build
images, rather than shipping a second copy of the fiddly part.

## Licence

Apache 2.0. See [LICENSE](LICENSE).
