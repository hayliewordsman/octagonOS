#!/usr/bin/env python3
"""
Build the octagonOS Plymouth theme.

    ./make-plymouth-theme.py

Renders the octagonOS mark from `shared/facetui/mark.py` -- the same code the
Android boot animation renders from -- and packages it as a Plymouth theme:
frames, the `.plymouth` config, and the bullet and fallback images the script
needs.

The script itself is hand-written and lives beside this file. Only the frames
and the generated images come from here.

WHY THE FRAMES ARE SMALLER THAN ANDROID'S

Plymouth loads every image at script load, into an initramfs that is copied
into RAM at boot and whose size is charged to every boot on the machine. The
Android animation's 92 frames at 720x720 would be roughly 9 MB of initramfs for
a few seconds of animation. 54 frames at 384x384 is closer to 1.5 MB, which is
a proportionate thing to spend.

Requires Pillow and NumPy.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))

from facetui.mark import (  # noqa: E402
    BG_BASE, FONT_CANDIDATES, FONT_LIGHT_CANDIDATES, build_frames, pick_font,
)
from facetui.facet_math import edge_highlight, rim_darkening  # noqa: E402
from facetui.palette import ACCENT_A, ACCENT_B  # noqa: E402

#: Frame geometry. See the note above on why this is not the Android size.
SIZE = 384
INTRO, LOOP, OUTRO = 18, 24, 12

#: Plymouth's own refresh is ~50Hz; the script advances a frame every Nth tick.
#: 24fps to match the Android animation, so the two read as the same thing.
FPS = 24

THEME_NAME = "octagonos"
INSTALL_DIR = f"/usr/share/plymouth/themes/{THEME_NAME}"


def bullet(px=18):
    """A passphrase bullet, as a small glass octagon.

    An image rather than a character, deliberately: a bullet drawn with
    Image.Text needs a font present in the initramfs, and the bullets are the
    one piece of feedback telling a user their keystrokes are registering. They
    must not be the thing that goes missing.
    """
    ss = 4
    n = px * ss
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    dx, dy = xs - n / 2.0, ys - n / 2.0

    # Same construction as the mark: eight edge planes, the largest wins.
    import math
    phis = [k * 2.0 * math.pi / 8 for k in range(8)]
    d = np.max(np.stack([dx * math.cos(p) + dy * math.sin(p) for p in phis]), 0)
    apothem = n * 0.42

    tint = ACCENT_A * 0.55 + ACCENT_B * 0.45
    rgb = np.broadcast_to(tint.astype(np.float32), (n, n, 3)).copy()
    # A touch of the edge highlight, so a bullet is glass rather than a dot.
    rgb += edge_highlight(apothem - d, apothem * 0.5,
                          np.zeros_like(d), 0.45)[..., None]
    alpha = np.clip((apothem - d) / (n / 48.0) + 0.5, 0.0, 1.0)

    out = np.dstack([np.clip(rgb, 0, 1), alpha[..., None]])
    img = Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")
    return img.resize((px, px), Image.LANCZOS)


def fallback_prompt(width=520, height=34):
    """"Enter passphrase", pre-rendered.

    THE POINT OF THIS IMAGE

    The real prompt comes from the initramfs and is drawn with Image.Text,
    which needs a font. If that font is not in the initramfs -- a real and
    common packaging mistake -- Image.Text yields nothing, and a user with an
    encrypted disk gets an animation, no prompt, and no way to know the machine
    is waiting for them.

    So the script measures the text image it built, and if it came out empty it
    shows this instead. English-only and generic, which is much better than
    silence.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = pick_font(FONT_LIGHT_CANDIDATES, 22)
    text = "Enter passphrase"
    w = d.textlength(text, font=font)
    d.text(((width - w) / 2.0, height / 2.0), text, font=font,
           fill=(226, 236, 250, 255), anchor="lm")
    return img


PLYMOUTH_CONF = """[Plymouth Theme]
Name=octagonOS
Description=FacetUI glass, at boot
ModuleName=script

[script]
ImageDir={install_dir}
ScriptFile={install_dir}/{name}.script
"""


def main():
    ap = argparse.ArgumentParser(description="Build the octagonOS Plymouth theme.")
    ap.add_argument("--out", default=os.path.join(HERE, THEME_NAME))
    ap.add_argument("--size", type=int, default=SIZE)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out = args.out
    os.makedirs(out, exist_ok=True)

    def note(m):
        if not args.quiet:
            print(m, file=sys.stderr)

    size = args.size
    apothem = size * 0.255
    fonts = (pick_font(FONT_CANDIDATES, int(size * 0.072)),
             pick_font(FONT_LIGHT_CANDIDATES, int(size * 0.030)))

    note(f"[*] rendering {INTRO + LOOP + OUTRO} frames at {size}x{size}")
    parts = build_frames(size, FPS, INTRO, LOOP, OUTRO, fonts, apothem,
                         quiet=args.quiet)

    # Flat, UNPADDED names. Plymouth's script language has no string
    # formatting -- no StringFormat, no printf -- so the script can only build
    # a filename by concatenating a number, and a padded name is therefore
    # unreachable from it. Naming them the way the script can address them is
    # the fix; the ordering the padding gave is not needed, because the script
    # indexes explicitly rather than listing the directory.
    counts = {}
    for part, prefix in (("part0", "intro"), ("part1", "loop"), ("part2", "outro")):
        for i, img in enumerate(parts[part]):
            img.save(os.path.join(out, f"{prefix}-{i}.png"))
        counts[prefix] = len(parts[part])
    note(f"    intro {counts['intro']}, loop {counts['loop']}, "
         f"outro {counts['outro']}")

    bullet().save(os.path.join(out, "bullet.png"))
    fallback_prompt().save(os.path.join(out, "prompt-fallback.png"))
    note("[*] bullet.png and prompt-fallback.png")

    with open(os.path.join(out, f"{THEME_NAME}.plymouth"), "w") as fh:
        fh.write(PLYMOUTH_CONF.format(install_dir=INSTALL_DIR, name=THEME_NAME))

    # The script is hand-written, but the frame counts are not: the script
    # cannot list a directory, so they have to be written down, and writing
    # them by hand is how they end up disagreeing with the frames.
    #
    # They are PREPENDED to the script rather than shipped beside it, because
    # PLYMOUTH LOADS EXACTLY ONE SCRIPT -- the ScriptFile named in the
    # .plymouth config. A second .script in the theme directory is simply never
    # read. Discovered the hard way: the constants were in their own file, so
    # intro_count was undefined, the frame-loading loop did nothing, and the
    # theme drew its background and then stopped. The background appearing made
    # it look as though the script had run.
    header = (
        "# --- generated by make-plymouth-theme.py, do not edit -------------\n"
        "#\n"
        "# Prepended rather than a separate file: Plymouth loads only the one\n"
        "# ScriptFile named in the .plymouth config, so a second .script here\n"
        "# would never be read.\n"
        f"intro_count = {counts['intro']};\n"
        f"loop_count = {counts['loop']};\n"
        f"outro_count = {counts['outro']};\n"
        f"frame_size = {size};\n"
        f"fps = {FPS};\n"
        "# --- end generated -----------------------------------------------\n\n"
    )
    script_src = os.path.join(HERE, f"{THEME_NAME}.script")
    with open(script_src) as fh:
        body = fh.read()
    with open(os.path.join(out, f"{THEME_NAME}.script"), "w") as fh:
        fh.write(header + body)

    total = sum(os.path.getsize(os.path.join(out, f))
                for f in os.listdir(out))
    note(f"[*] {out}  ({total / 1048576:.1f} MiB, "
         f"{len(os.listdir(out))} files)")


if __name__ == "__main__":
    main()
