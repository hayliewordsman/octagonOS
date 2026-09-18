# FacetUI on Android 17

How the design language is implemented on Android, and what changed in bringing
it from Android 16.

**The language itself — the rule, the depth model, the tint doctrine, why only
windows can blur — is in
[`../../shared/docs/design-language.md`](../../shared/docs/design-language.md).**
This document assumes it.

## The rule that governs everything

> On a blurred surface, any effect that works by **displacing samples** is
> invisible. Only effects that **modify values** -- brightness, tint, contrast
> -- survive the blur.

Established in titan2e-eos by rendering the shader maths rather than reasoning
about it. It killed a refraction shader, and then a chromatic-aberration
replacement, before either cost a build. Both surviving shaders modify values:
the edge highlight adds brightness, the rim darkening scales it. That is not a
coincidence, it is the rule doing its job.

The boot animation obeys it too, and for a reason beyond consistency: it is
rendered by `shared/facetui/facet_math.py`, which is a literal transcription of
the same AGSL. The mark on the boot screen is lit by the arithmetic that lights
the shade.

## The depth model

Glass reads as depth only if blur is *hierarchical*. A single radius everywhere
looks like frosted plastic. Each tier roughly doubles, because the eye reads the
ratio between surfaces rather than absolute radii.

| Tier | Radius | Used for |
|---|---|---|
| `L0` | 0 | opaque surfaces: wallpaper, app content |
| `L1` | 8dp | inline chips, inactive QS tiles |
| `L2` | 24dp | volume dialog, power menu, popups, folders |
| `L3` | 48dp | shade content, notifications, the keyboard |
| `L4` | 64dp | the full shade window, the deepest layer |

The point of writing these down is that surfaces which sit at the same visual
depth should share a tier even when Android gives them unrelated resource names.
Stock ships the volume dialog at 0dp, the power menu at 34dp and folders at
20dp; three surfaces the user reads as the same kind of popup, made of three
different materials. FacetUI puts all three on `L2`.

## What changed from Android 16 to Android 17

The single biggest finding: **Android 17 exposes much more of the glass surface
as resources than Android 16 did.** Work that needed a SystemUI recompile on 16
is now an overlay.

Newly resource-controlled on `lineage-24.0`, under a comment block the AOSP
source labels "Lockscreen blur values":

| Resource | Stock | What it reaches |
|---|---|---|
| `notification_background_blur_radius` | 25dp | **push notifications** |
| `keyguard_shortcuts_blur_radius` | 15dp | **lockscreen** shortcuts |
| `fingerprint_icon_blur_radius` | 15dp | the lockscreen fingerprint affordance |
| `bottomsheet_blur_radius` | 30dp | bottom sheets |
| `volume_dialog_background_surface_blur_radius` | 23px | the volume dialog surface |

That matters for octagonOS specifically, because "notifications and the
lockscreen should be glass" is a Tier 2 change here and would have been a Tier 3
change a release ago. A prebuilt Android 17 GSI can have glass notifications
with no source build at all.

Moving the other way:

- **`shade_panel_base` no longer exists.** titan2e-eos overrode it on Android 16.
  On 17 it is gone, and an overlay naming it would have linked, installed and
  silently done nothing. `tools/validate-overlays.py` exists because of this
  class of failure.
- **The tint overrides became redundant.** `notification_scrim_base`,
  `shade_panel_fallback` and `notification_scrim_fallback` already ship on
  `lineage-24.0` with exactly the values FacetUI wanted. The overlay that set
  them was deleted rather than kept as decoration.
- **`ActiveNotificationIconModel` lost `whenTime` and `isSilent`.** The status
  bar icon patch sorted by timestamp on Android 16 to avoid picking an arbitrary
  element out of a `Set`. On 17 there is no timestamp on that model, so it sorts
  by key instead. Not chronological, but stable -- and since mode 2 replaces the
  icon with a plain circle, *which* notification backs the dot is not observable.
  Only whether it keeps changing is, and sorting fixes that.

## Dialogs are glass. Menus are not, and cannot be from a resource.

The platform has carried three window attributes since Android 12:

| Attribute | Effect |
|---|---|
| `windowBackgroundBlurRadius` | blurs what is behind the window, within its background |
| `windowBlurBehindEnabled` | turns on blur of the whole screen behind the window |
| `windowBlurBehindRadius` | how much |

**No platform theme sets any of them.** They are sitting unused, and
`PhoneWindow.generateLayout()` reads all three straight off the window's theme:

```java
if (a.getBoolean(R.styleable.Window_windowBlurBehindEnabled, false)) {
    params.flags |= WindowManager.LayoutParams.FLAG_BLUR_BEHIND;
    params.setBlurBehindRadius(a.getDimensionPixelSize(
            android.R.styleable.Window_windowBlurBehindRadius, 0));
}
setBackgroundBlurRadius(a.getDimensionPixelSize(
        R.styleable.Window_windowBackgroundBlurRadius, 0));
```

`Dialog` builds a `PhoneWindow`, so an overlay can make **every dialog in the
system** glass with no code at all.

### Two empty styles carry it

Overriding a style in an RRO is risky, because the overlay's bag replaces the
target's — anything the original declared and the override forgets is gone.
Which makes it fortunate that in the platform these two are *empty*:

```xml
<style name="Theme.Material.Dialog" parent="Theme.Material.BaseDialog"/>
<style name="Theme.Material.Light.Dialog" parent="Theme.Material.Light.BaseDialog"/>
```

There is nothing in them to lose. Everything a dialog actually gets comes from
`BaseDialog` above, which is left alone, and every dialog variant in the system
inherits down through these two — `Alert`, `MinWidth`, `NoActionBar`, the
`DeviceDefault` counterparts, all of it. Largest possible reach, smallest
possible risk.

### Three things had to be true together

- **blur**, from the attributes above;
- **translucency**, because the blur renders *behind* the window background and
  an opaque background hides it completely. That is the dialog-specific
  `background_floating_device_default_*` pair, not `colorBackground`, which
  would have made every activity window translucent;
- **less dim.** Stock is `0.6`, and `0.7` on some DeviceDefault themes. That
  much black over a blur is just black. Dropped to `0.32`, so the blur is what
  separates the dialog from the app and the dim only deepens it.

Miss any one and the other two are wasted — the same shape as the keyboard.

### Menus needed a patch, and got one

A `PopupWindow` is **not** a `PhoneWindow`. It attaches a view straight to the
`WindowManager`, never runs `generateLayout()`, and exposes no blur API of its
own. So no resource overlay can make a menu glass — that is the ceiling for
Tier 2, and overflow menus, spinner dropdowns and autocomplete lists get tint
and a hairline only, which by the rule at the top of this page is a tinted
window rather than glass.

`patches/framework/0001` lifts that ceiling. The blur comes from
`BackgroundBlurDrawable`, the same mechanism `DecorView` already uses for window
background blur: it blurs what is behind it, clipped to its own rounded bounds,
so it can simply sit **underneath** the popup's existing background. The
translucent fill reads through it and the hairline draws on top, untouched.

Three details decide whether it works:

- **It attaches to the background view, not the decor view.** The decor's
  bounds include room for the drop shadow, so blurring there would put a
  blurred rectangle visibly larger than the menu behind it.
- **It takes the corner radius from the popup's own background** when that is a
  shape drawable, so the blur does not square off inside a rounded menu.
- **It listens for cross-window blur being switched off**, which battery saver
  and the developer "disable blurs" option both do. Reading the flag once would
  leave a translucent menu with nothing blurred behind it.

It is off unless asked for: `R.dimen.facetui_popup_blur_radius` is `0dp` in the
platform, and a build that does not override it gets stock `PopupWindow`
behaviour with nothing allocated. The patch also declines to do anything when
the popup background is opaque — there would be nothing to see through, and
that same opacity is what sets the popup window's pixel format, so the blur
could not composite anyway.

One consequence worth stating: the popup fill alpha is now a **compromise**.
With the patch there is a blur behind it and it could open further; the same
overlay ships on a Tier 2 image where there is not, and at much lower alpha an
unblurred menu is hard to read over busy content.

## The three layers

**Tier 1 -- properties.** `ro.surface_flinger.supports_background_blur=1`.
Without it SurfaceFlinger performs no cross-window blur and every radius below
is wasted. It is a property, not a resource, so no overlay can deliver it; it
is set in the image. `surfaceflinger` ships inside the GSI, so this is the
system image's decision to make. What the device still controls is the GPU
driver.

**Tier 2 -- RRO overlays.** `overlay/`. Four packages: SystemUI, framework,
launcher, IME. No recompile. This is most of the glass.

**Tier 3 -- source patches.** `patches/`. Reserved for what resources cannot
express:

| Patch | What it does |
|---|---|
| `systemui/0001` | `FacetEdgeShader`, an AGSL specular highlight along the top of the shade scrim |
| `systemui/0002` | `FacetRimShader`, **chained** onto the scrim's existing blur |
| `systemui/0003` | Four status bar notification icon modes, including a neutral dot |
| `ime/0001` | Blurs behind the keyboard window |
| `framework/0001` | Blurs behind popup menus and dropdowns |

## The trap `0002` avoids

`ScrimView` already applies a `RenderEffect` -- its blur, set in
`setBlurRadius`. Calling `setRenderEffect` again would have *discarded the blur
entirely*, destroying what the design depends on while presenting as "the shader
doesn't work". `0002` composes them with
`RenderEffect.createChainEffect(rim, blur)`, which is also correct physically:
light is diffused by the body of the glass, then absorbed by the thicker rim.

## Why the keyboard needs a patch when the shade does not

An RRO can change colours, and a translucent keyboard background is a colour.
But translucent is not glass: the app behind shows through unmodified, which
reads as a tinted window. What makes it glass is blurring what is behind, and
that is `Window.setBackgroundBlurRadius` -- a window property, reachable only
from code.

So the glass keyboard is deliberately split in half, and **both halves are
required**:

- `overlay/FacetUIIME` makes the background translucent;
- `patches/ime/0001` blurs behind the window.

With only the overlay you get a tinted keyboard. With only the patch you get a
blur nobody can see, behind an opaque surface.

That patch also listens for cross-window blur being turned off at runtime --
battery saver and the developer "disable blurs" option both do it. Reading the
flag once at startup would leave the keyboard translucent with nothing blurred
behind it, which looks worse than no glass at all.

### One thing the overlay costs

Resource XML cannot apply alpha to a colour *reference*, only to a literal. So
anything made translucent stops following the Material You palette. FacetUI
spends that on the keyboard background alone and leaves every key colour on its
dynamic reference: the background is the surface the blur shows through, so it
buys the whole effect, while the keys, which are what the eye actually reads,
keep the wallpaper palette.

## Validating the shaders without a device

```bash
pip install skia-python        # plus libegl1 libgl1 on Linux
tools/validate-shaders.py
```

AGSL is Android's binding of Skia runtime effects, so Skia's own SkSL compiler
rejects most of what Android would -- with no SDK, no emulator and no device.
**Both FacetUI shaders compile.**

The tool proves the compiler is awake before trusting it, on five deliberately
broken shaders: an undeclared variable, a type mismatch, a missing `main`, a
syntax error and a wrong `main` signature. All five are rejected and a valid
shader is accepted. Without that, "it compiles" would only mean the compiler
never says no.

It also checks the things that *claim* to mirror the AGSL and were, until now,
on trust: that `shared/facetui/facet_math.py` still uses the same falloff and
centre-bias constants the shader does, and that the four FacetUI parameters
agree across the shader defaults, `ScrimView`, the boot animation and the icon
pack. This repository says throughout that the boot screen, the shade and the
app icons are lit by the same maths; that sentence is now enforced rather than
asserted.

A pass is strong evidence, not proof: SkSL is not AGSL, and this is not the
Skia in any given Android release. titan2e-eos's on-device harness settles it.

## What is still outstanding at Tier 3

- refraction at panel edges, sampling what is behind the surface. Ruled out for
  now by the rule at the top of this page, unless it is done as a value
  modification rather than a displacement
- reshaped QS tile geometry beyond what dimens allow
- an SELinux domain for the first-boot service (see [status.md](status.md))
