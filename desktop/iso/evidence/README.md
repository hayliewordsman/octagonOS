# What the booted image actually reported

The file beside this one is the serial console output of `octagonos-selftest`
running inside a booted octagonOS live image, on 2026-09-19. It is kept
because it is the only evidence in this repository that FacetUI *runs*, as
opposed to being installed, correct and selected -- which is all any offline
check can establish.

```
OK   render node: /dev/dri/renderD128
OK   compositing: gl2
OK   facetui-glass is loaded and running
INFO kwin blur loaded: true
OK   kdeglobals [Icons] Theme = FacetUI
OK   plasmarc [Theme] name = FacetUI
OK   kdeglobals [General] ColorScheme = FacetUI
```

## Read the INFO lines before the OK lines

Two of them carry the qualifications, and the result means less than it
looks without them.

**OpenGL was forced.** KWin asks the driver whether it recommends OpenGL
compositing. Mesa's software rasteriser says no, and KWin honours that by
using its QPainter scene -- where no OpenGL effect is loaded at all, not
FacetUI's and not KWin's own. The guest has no GPU, so the boot passes
`octagonos.forcegl`, which sets `KWIN_COMPOSE=O2ES`. Without it this test
could never reach the thing it exists to test.

So: the effect was compiled by Mesa's GLSL compiler, loaded into a real KWin
OpenGL scene, and run over real windows. Every frame was drawn by the CPU.
Nothing here measures performance, and nothing here is a claim about how it
behaves on a GPU.

**Blur is the control.** `kwin blur loaded: true` is the line that makes the
rest attributable. KWin's own blur is an OpenGL effect maintained by people
with no stake in this project; if it had failed to load, the FacetUI line
above it would say nothing about FacetUI and everything about the machine.
Both loaded, so the result is about the effect.

## What is still not proven

That the glass *looks right*. The self-test asks KWin whether the effect is
loaded and running; it does not photograph the screen. QEMU's own screenshot
comes back blank once kwin_wayland takes the DRM device -- the host reports
no active scanout -- so there is no picture from this run. Appearance is
covered offline instead, by the shader's output being compared against NumPy
and the Plasma style's surfaces being rendered and measured, but "loaded and
running" and "looks correct" remain two different claims and only the first
one was made here.

## Reproducing it

```
sudo desktop/iso/build-iso.sh --profile desktop
desktop/tools/verify-iso.sh   desktop/iso/out/octagonos-desktop.iso
sudo desktop/tools/boot-iso-check.sh desktop/iso/out/octagonos-desktop.iso
```

The image itself is not in the repository: it is 1.7G, which is past what
git should carry and past what GitHub accepts. It is rebuilt from the script
above, which pins its archives so the rebuild is the same image.
