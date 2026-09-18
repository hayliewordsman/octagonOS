# The octagonOS boot animation

An eight-facet glass octagon -- the octagonOS mark -- lit by FacetUI's own
shader maths, with the `octagonOS` and `FacetUI` wordmarks beneath it.

```bash
bootanimation/build.sh          # builds, then verifies
```

Output is `bootanimation/out/bootanimation.zip`: 8.9 MiB, 92 frames, 3.8s at
24fps.

## It is lit by the real shaders

`bootanimation/facet_math.py` is a literal NumPy transcription of the AGSL in
`patches/systemui/0001` and `0002` -- the same expressions in the same order, so
the two can be read side by side. The mark's edge highlight is
`FacetEdgeShader`; the darkening across each facet is `FacetRimShader`; the
table in the middle is darkened toward its own rim by the same function, because
a flat top is a pane of glass too.

This is not decoration. It means the boot screen and the notification shade are
the same material, and that if a constant changes in the shaders, the branding
follows it.

## Three decisions worth knowing about

### The canvas is square

octagonOS targets both slab phones (tall, ~20:9) and physical-keyboard phones
(Titan-class, near-square). `bootanimation` scales the animation to fit the
display and centres it, so a square canvas centres correctly on both rather than
being letterboxed badly on one.

### The frame borders match the letterbox exactly

Because the canvas is square and the screen is not, there is always a letterbox,
and `bootanimation` clears it to the per-part background colour from `desc.txt`.
If the frame's own edge pixels did not match that colour, the seam would show as
a band across the screen -- and on a tall phone that band is most of the display.

So the background is a *flat* colour, and the glow behind the mark is windowed
to reach exactly zero before the canvas edge. Every border pixel is `#040508`,
which is what `desc.txt` declares. `tools/verify-bootanimation.py` checks this
on sampled frames of every part rather than trusting it.

### The loop is short on purpose

This is the constraint that shapes the whole animation, and it is not obvious.

From `frameworks/base/cmds/bootanimation/BootAnimation.cpp` on `lineage-24.0`:

```c++
if (frameIdx > 0) {
    glBindTexture(GL_TEXTURE_2D, frame.tid);
} else {
    if (part.count != 1) {
        glGenTextures(1, &frame.tid);
        glBindTexture(GL_TEXTURE_2D, frame.tid);
    }
    ...
```

and the matching cleanup, which runs only once the whole animation is done:

```c++
// Free textures created for looping parts now that the animation is done.
for (const Animation::Part& part : animation.parts) {
    if (part.count != 1) {
        for (const auto& frame : part.frames) {
            glDeleteTextures(1, &frame.tid);
        }
    }
}
```

So **every frame of a looping part becomes a resident GL texture for the entire
boot**, while a part with `count == 1` decodes into one reused texture and costs
nothing extra.

At 1080x1080 that is 4.45 MiB per frame. An 84-frame loop -- an unremarkable
3.5s at 24fps -- would hold **374 MiB of texture memory** on a phone that has
barely finished mounting `/data`. Nothing warns you; it is simply a boot
animation that makes low-memory devices struggle.

The layout follows from that:

| Part | Type | Frames | Resident |
|---|---|---|---|
| `part0` intro | `p 1 0` | 40 | no |
| `part1` loop | `p 0 0` | 30 | **yes -- 59 MiB** |
| `part2` outro | `c 1 0` | 22 | no |

The intro and outro are long because they are free. The loop is 30 frames at
720x720 because that is what fits a 64 MiB budget.
`make-bootanimation.py` prints the figure on every build and warns above the
budget; `verify-bootanimation.py` fails above it.

## The loop has to be seamless

`part1` repeats until boot completes, so its last frame hands back to its first
several times on every boot. Everything periodic in it -- the light's full
rotation, the breathing of the glow -- completes exactly one cycle across the
part, and the frame parameter is `i / frames` rather than `i / (frames - 1)`, so
the final frame stops one step short of the start instead of duplicating it.

The verifier checks this numerically rather than by eye: it compares the
wrap-around step against a typical adjacent step from the middle of the part.
Currently 1.10 against 1.28, i.e. the wrap is if anything smaller than a normal
step.

## Verifying

```bash
tools/verify-bootanimation.py bootanimation/out/bootanimation.zip
```

Checks the things that break boot animations silently -- you get a black screen
or a visible seam, and nothing in the log:

1. `desc.txt` exists, parses, and is first in the archive
2. every part it names exists and has frames
3. every entry is `STORED` -- `bootanimation` maps the zip directly, and a
   deflated entry costs a decompression on the boot path for no gain, since PNG
   is already compressed
4. every PNG matches the declared dimensions
5. frame borders match the declared background colour
6. the looping part fits the texture budget
7. the loop is seamless

## Rebuilding it differently

```bash
# Bigger, if you have the memory budget for it
python3 bootanimation/make-bootanimation.py --size 1080 --loop 14

# Slower sweep, longer intro
python3 bootanimation/make-bootanimation.py --fps 30 --intro 60 --loop 36

# Inspect the frames
python3 bootanimation/make-bootanimation.py --frames-dir /tmp/frames
```

`--size` and `--loop` trade against each other through the budget; the build
prints the resulting residency, so pick the pair that fits rather than guessing.

Fonts are found from a candidate list, DejaVu last as the portable fallback.
Override with `--font` and `--font-light` to use the brand face of your choice;
the wordmarks are `octagonOS` and `FacetUI`, with no spaces, in both cases.
