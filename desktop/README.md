# octagonOS Desktop

An Ubuntu-based Linux distribution carrying FacetUI — the same glass design
language as the mobile edition, from the same maths in
[`shared/facetui`](../shared/facetui).

**Started.** The boot splash, the compositor effect, the Plasma style and the
icon theme are built, and they are the first pieces of octagonOS that have
actually been *run* rather than verified.

![The Plymouth theme](docs/preview/plymouth.png)

![Blur and tint alone, and the same surfaces with facetui-glass](docs/preview/kwin-glass.png)

![The FacetUI Plasma surfaces](docs/preview/plasma.png)

![The FacetUI icon theme](docs/preview/icons.png)

## Status

| | |
|---|---|
| [Plymouth theme](plymouth/) | **Built and run.** The mark, the passphrase prompt, messages, teardown |
| [KWin glass effect](kwin/) | **Built and loaded.** Compiles against KWin 6.7.5; KWin accepts the plugin. Drawing needs a GPU |
| [Plasma style](plasma/) | **Built and rendered.** Every surface composited by KSvg and measured: alpha, hairline, corners |
| [Icon theme](icons/) | **Built and resolved.** 124 names over 8 sizes, each checked against the file it ships, by Qt and by GTK |
| [Packaging](packaging/) | **Built and installed.** Five `.deb`s, lintian-clean; FacetUI verified to be the default, not an option |
| ISO | Not started |

## The compositor: KWin/Plasma on Wayland

Settled, and almost everything else follows from it.

Glass needs compositor-level blur, and how much control a compositor gives over
it varies enormously. KWin is the one that gives the most: its blur is a real
effect with a source that can be modified, it already reads a per-window blur
region, and Plasma's theming reaches far enough to put the rest of FacetUI —
the tint, the hairline, the depth tiers — on system surfaces without patching
applications.

Wayland rather than X11 because the blur-behind path is the one that works
there, and because it is where the platform is going; an X11-first effect would
be written twice.

The consequence worth naming: **the "only windows can blur" rule holds here
too.** It is not an Android quirk. A compositor can blur what is behind a
surface it composites, which is a window. An application's own toolbar, cards
and list backgrounds are drawn inside that window and can only be tinted unless
the application does the work itself. The line between glass and merely-tinted
is the same line, drawn by the same rule, on both editions.

## Why this edition is more provable than the mobile one

The Android work in [`mobile/`](../mobile) can be verified but not *run*: a GSI
needs 250–400 GB to build and a phone to boot. Desktop Linux does not have that
problem, and the Plymouth theme is the proof — it was built, installed, driven
with real keystrokes and screenshotted, and four bugs came out of doing that
which no amount of reading the script had found.

That is the standard this edition is held to: seen working, not verified as far
as possible. Where it cannot be met, it is named rather than blurred — the
compositor effect builds, loads and is accepted by KWin, and whether it *draws*
correctly needs a GPU this has not had. Its arithmetic is settled separately,
against a real driver.

## What ported, and what did not

| Asset | Desktop form |
|---|---|
| `facet_math.py` | Unchanged — already NumPy |
| The mark renderer | Unchanged — `shared/facetui/mark.py`, shared with the Android boot animation |
| The boot animation | A Plymouth theme, [`plymouth/`](plymouth/) |
| The AGSL shaders | A KWin GLSL effect, [`kwin/facetui-glass`](kwin/facetui-glass) — transcribed nearly verbatim, and checked against the NumPy to 1.7e-07 |
| The icon pack | A freedesktop icon theme, [`icons/`](icons/) -- the tile is `shared/facetui/tile.py`, the glyphs `shared/facetui/glyphs.py` |
| The depth model, `L0`–`L4` | Blur strength per surface type |
| The octagon, the palette, the hairline | Directly |

What does not port: RROs, `AndroidManifest.xml`, adaptive icons, `PopupWindow`,
form-factor detection — everything shaped by Android rather than by FacetUI.

## Layout

| | |
|---|---|
| [`plymouth/`](plymouth/) | The boot splash |
| [`kwin/`](kwin/) | The compositor effect: FacetUI's two shaders |
| [`plasma/`](plasma/) | The Plasma style: translucency, the hairline, the colour scheme |
| [`icons/`](icons/) | The icon theme: the glass octagon, with the shared glyphs |
| [`packaging/`](packaging/) | The `.deb`s, and the defaults that select FacetUI |
| [`tools/`](tools/) | Verifiers, and the harness that runs a theme for real |
| `docs/preview/` | Screenshots, taken by those tools |
