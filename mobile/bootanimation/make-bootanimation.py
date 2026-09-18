#!/usr/bin/env python3
"""
Build the octagonOS boot animation.

    ./make-bootanimation.py --out out/bootanimation.zip

Renders the octagonOS mark -- see shared/facetui/mark.py, which both editions
render from -- and packs it as an Android ``bootanimation.zip``. Everything
specific to Android is here: the desc.txt format, the STORED zip, and the
texture budget that decides how long the looping part may be.

Why a square canvas: octagonOS targets both slab phones (tall, ~20:9) and
physical-keyboard phones (Titan-class, near-square). Android's bootanimation
scales the animation to fit the display and centres it, so a square canvas
centres correctly on both instead of being letterboxed on one. See
docs/bootanimation.md.

Requires Pillow and NumPy. No Android SDK, no device.
"""

import argparse
import os
import shutil
import sys
import tempfile
import zipfile

# The FacetUI core is shared with the desktop edition, so it lives outside
# this directory rather than beside the thing that happens to use it first.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from facetui.mark import (  # noqa: E402
    BG_BASE, FONT_CANDIDATES, FONT_LIGHT_CANDIDATES, build_frames, pick_font,
)

#: A fixed timestamp for every zip entry, so two builds of the same frames
#: produce the same bytes. The value is arbitrary; only its fixedness matters.
#: (1980-01-01 is the earliest a zip can represent.)
REPRODUCIBLE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

#: The background colour bootanimation clears to, as #RRGGBB. Must equal
#: BG_BASE -- which is shared -- or the letterbox around the square canvas
#: will not match the frames.
BG_HEX = "".join(f"{int(round(c * 255)):02x}" for c in BG_BASE)

#: part0 plays once (`p 1`), part1 loops until boot completes (`p 0`), part2
#: plays to completion whatever happens (`c 1`) so the mark resolves instead of
#: being cut off mid-sweep.
#:
#: Only part1 is memory-resident: bootanimation allocates a GL texture per
#: frame for any part whose count != 1 and frees them only when the whole
#: animation ends. part0 and part2 decode into one reused texture. That is why
#: the loop is the short part. See loop_texture_bytes().
DESC_TEMPLATE = """{w} {h} {fps}
p 1 0 part0 #{bg}
p 0 0 part1 #{bg}
c 1 0 part2 #{bg}
"""


#: How much GL texture memory the looping part may occupy. bootanimation keeps
#: a decoded texture per frame for every part whose count != 1, for the whole
#: boot, so a long high-resolution loop can cost hundreds of megabytes on a
#: device that has barely finished mounting /data. Verified against
#: frameworks/base/cmds/bootanimation/BootAnimation.cpp on lineage-24.0:
#: playAnimation() calls glGenTextures per frame under `if (part.count != 1)`,
#: and the matching glDeleteTextures only runs after the animation completes.
LOOP_TEXTURE_BUDGET_MIB = 64.0


def loop_texture_bytes(size, loop_frames):
    """Resident GL texture cost of the looping part, in bytes (RGBA8)."""
    return size * size * 4 * loop_frames


def check_loop_budget(size, loop_frames, quiet=False):
    mib = loop_texture_bytes(size, loop_frames) / 1048576.0
    msg = (f"[*] loop part: {loop_frames} frames x {size}x{size} RGBA "
           f"= {mib:.0f} MiB resident GL texture")
    if mib > LOOP_TEXTURE_BUDGET_MIB:
        print(msg, file=sys.stderr)
        print(f"warning: that exceeds the {LOOP_TEXTURE_BUDGET_MIB:.0f} MiB budget. "
              f"bootanimation holds every frame of a looping part in GPU memory "
              f"for the whole boot. Reduce --loop or --size.", file=sys.stderr)
    elif not quiet:
        print(msg, file=sys.stderr)
    return mib


def write_zip(parts, out_path, size, fps, png_optimise=True, quiet=False):
    """Pack the parts as a bootanimation.zip.

    Every entry is STORED, never deflated: bootanimation memory-maps the zip
    and reads frames straight out of it, so a compressed entry costs a
    decompression on the critical boot path -- and the frames are PNG, which
    is already compressed, so deflate would buy nothing anyway.
    """
    staging = tempfile.mkdtemp(prefix="octagonos-boot-")
    try:
        for name, frames in sorted(parts.items()):
            d = os.path.join(staging, name)
            os.makedirs(d, exist_ok=True)
            for i, img in enumerate(frames):
                img.save(os.path.join(d, f"{i:04d}.png"),
                         optimize=png_optimise)

        desc = DESC_TEMPLATE.format(w=size, h=size, fps=fps, bg=BG_HEX)
        with open(os.path.join(staging, "desc.txt"), "w", newline="\n") as fh:
            fh.write(desc)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

        def add(z, path, arcname):
            """Add an entry with a fixed timestamp.

            zipfile.write() stamps each entry with the file's mtime, and the
            staging directory is a fresh mktemp every run -- so two builds of
            identical frames produced zips that differed in every header. That
            is not a hypothetical: it made a CI check comparing the committed
            animation against a rebuild fail on every single run, for no
            reason. Pinning the timestamp makes the build reproducible, which
            is what lets that check mean anything.
            """
            info = zipfile.ZipInfo(arcname, date_time=REPRODUCIBLE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as fh:
                z.writestr(info, fh.read())

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as z:
            # desc.txt first: the player reads it before anything else.
            add(z, os.path.join(staging, "desc.txt"), "desc.txt")
            for name in sorted(parts):
                d = os.path.join(staging, name)
                for fn in sorted(os.listdir(d)):
                    add(z, os.path.join(d, fn), f"{name}/{fn}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not quiet:
        print(f"[*] wrote {out_path} "
              f"({os.path.getsize(out_path) / 1048576:.1f} MiB)", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Build the octagonOS boot animation.")
    ap.add_argument("--out", default="out/bootanimation.zip")
    ap.add_argument("--size", type=int, default=720,
                    help="square canvas edge, px (default: 720)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--intro", type=int, default=40, help="part0 frame count")
    ap.add_argument("--loop", type=int, default=30,
                    help="part1 frame count -- this is the memory-resident part")
    ap.add_argument("--outro", type=int, default=22, help="part2 frame count")
    ap.add_argument("--font", help="override the wordmark font (.ttf)")
    ap.add_argument("--font-light", help="override the FacetUI font (.ttf)")
    ap.add_argument("--frames-dir",
                    help="also write the raw PNG frames here, for inspection")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    size = args.size
    apothem = size * 0.255
    fonts = (
        pick_font(FONT_CANDIDATES, int(size * 0.072), args.font),
        pick_font(FONT_LIGHT_CANDIDATES, int(size * 0.030), args.font_light),
    )

    check_loop_budget(size, args.loop, quiet=args.quiet)

    parts = build_frames(size, args.fps, args.intro, args.loop, args.outro,
                         fonts, apothem, quiet=args.quiet)

    if args.frames_dir:
        for name, frames in parts.items():
            d = os.path.join(args.frames_dir, name)
            os.makedirs(d, exist_ok=True)
            for i, img in enumerate(frames):
                img.save(os.path.join(d, f"{i:04d}.png"))

    write_zip(parts, args.out, size, args.fps, quiet=args.quiet)


if __name__ == "__main__":
    main()
