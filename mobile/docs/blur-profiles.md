# Blur on hardware nobody has measured

FacetUI asks a GPU for real work: a blur behind every dialog, the whole screen
behind a modal one, and a blurred surface under every menu. octagonOS is a GSI,
so it will run on hardware none of this was measured on, some of it
considerably weaker than whatever it was designed against.

**Nothing here has been profiled.** This is the tuning order to follow when it
is, and what to turn down first.

## What costs what

Roughly, most to least expensive:

| Setting | Where | Cost |
|---|---|---|
| `windowBlurBehindEnabled` | dialogs | **Highest.** Blurs the *entire screen* behind every dialog |
| `max_shade_window_blur_radius` (L4, 64dp) | shade | High. Large surface, large radius |
| `facetui_popup_blur_radius` (L2) | menus | Moderate, but frequent — menus open constantly |
| `notification_background_blur_radius` (L3) | notifications | Moderate, multiplied by notification count |
| `config_sf_slowBlur` | SurfaceFlinger | Quality/cost switch, global |

## Turn down in this order

1. **`windowBlurBehindEnabled` → false.** Dialogs keep
   `windowBackgroundBlurRadius`, so the panel is still glass; only the
   full-screen blur behind it goes. Biggest saving, smallest visible loss.
2. **L4 → L3.** Drop the shade window from 64dp to 48dp. The depth model
   survives; it just gets shallower.
3. **`facetui_popup_blur_radius` → 0.** Menus fall back to tint and hairline.
   With `facetui_solidify_when_no_blur` on they go opaque instead, which is
   legible but no longer glass.
4. **Everything off.** Setting
   `ro.surface_flinger.supports_background_blur=0` disables cross-window blur
   entirely; the solidify path then makes every surface opaque, and the result
   is a flat but coherent theme rather than a broken one.

Step 4 is worth knowing about: **the design has a defined bottom.** It degrades
to something deliberate rather than to washed-out panels.

## How to profile it

The numbers that matter are frame time while the shade is being dragged, and
while a dialog opens over a busy screen — not steady state, which is cheap.

```bash
adb shell dumpsys SurfaceFlinger --latency          # frame timing
adb shell dumpsys gfxinfo com.android.systemui      # jank, percentiles
```

Compare against the same interactions with
`ro.surface_flinger.supports_background_blur=0`. If the gap is large the GPU is
telling you which tier to drop.

## Doing it per device

A GSI cannot branch on hardware at build time, and FacetUI deliberately has no
runtime device database — that is a maintenance burden with no owner.

The supported route is a **second overlay**, layered above the FacetUI ones with
a higher priority, carrying only the radii a given device needs. The depth
model stays in one place and the device-specific exception is small, visible and
separately removable. Which is the same reason the FacetUI overlays are separate
from the apps they theme.
