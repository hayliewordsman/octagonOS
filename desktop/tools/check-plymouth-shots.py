#!/usr/bin/env python3
"""
Check the screenshots run-plymouth-theme.sh took actually show the right thing.

    desktop/tools/check-plymouth-shots.py desktop/tools/ci

Expects the shots from this run, in this order:

    <prefix>-1.png   the splash, nothing asked for yet
    <prefix>-2.png   a passphrase has been asked for
    <prefix>-3.png   a passphrase has been typed
    <prefix>-4.png   it has been entered

WHY THIS IS SEPARATE FROM THE HARNESS

Running the theme proves it does not crash. It does not prove the passphrase
prompt appeared -- and a theme that runs happily while drawing no prompt is
exactly the failure that strands someone at a black screen with an encrypted
disk. The harness produces evidence; this reads it.

The bands are derived from the theme's own geometry rather than hardcoded, so
changing the frame size or the layout does not quietly turn these checks into
assertions about empty space.

Requires NumPy and Pillow.
"""

import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
THEME = os.path.join(HERE, "..", "plymouth", "octagonos")

#: The harness's Xvfb screen. Kept here because the bands are computed from it.
SCREEN_W, SCREEN_H = 1280, 800

#: BG_BASE, as the frames and Window.SetBackground*Color use it.
BG = np.array([4, 5, 7])


def ink(img, y0, y1):
    """How many pixels in this horizontal band are not the background."""
    a = np.asarray(img.convert("RGB")).astype(int)
    return int((np.abs(a[y0:y1] - BG).sum(-1) > 12).sum())


def bullet_groups(img, y0, y1):
    """How many separate bullets are in this band.

    Counted as runs of columns containing ink, rather than by pixel total, so
    a change to the bullet's size does not silently change the answer.
    """
    a = np.asarray(img.convert("RGB")).astype(int)
    cols = (np.abs(a[y0:y1] - BG).sum(-1) > 12).any(0)
    return len(re.findall(r"1+", "".join("1" if c else "0" for c in cols)))


def geometry():
    """The bands, from the theme's own numbers."""
    script = os.path.join(THEME, "octagonos.script")
    src = open(script).read()
    frame = int(re.search(r"^frame_size\s*=\s*(\d+)\s*;", src, re.M).group(1))

    mark_y = (SCREEN_H - frame) // 2 - SCREEN_H // 12
    prompt_y = mark_y + frame + SCREEN_H // 24
    bullet_y = prompt_y + 46
    bullet_h = Image.open(os.path.join(THEME, "bullet.png")).size[1]
    return {
        "mark": (mark_y, mark_y + frame),
        "prompt": (prompt_y, bullet_y - 2),
        "bullets": (bullet_y - 4, bullet_y + bullet_h + 4),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    prefix = sys.argv[1]
    shots = {}
    for n in ("1", "2", "3", "4"):
        p = f"{prefix}-{n}.png"
        if not os.path.exists(p):
            print(f"[FAIL] missing screenshot {p} -- the harness did not get "
                  f"that far, or it was run with different steps")
            return 1
        shots[n] = Image.open(p)

    g = geometry()
    splash, asked, typed, entered = shots["1"], shots["2"], shots["3"], shots["4"]
    fails = []

    def check(cond, msg):
        print(f"  {'ok  ' if cond else 'FAIL'}  {msg}")
        if not cond:
            fails.append(msg)

    print("the splash")
    mark_bright = ink(splash, *g["mark"])
    check(mark_bright > 5000,
          f"the mark is drawn ({mark_bright} px) -- a theme whose script fails "
          f"to load still paints the background, so an empty frame here means "
          f"the script did nothing")
    check(ink(splash, *g["prompt"]) == 0, "nothing is prompting yet")

    print("a passphrase is asked for")
    prompt_ink = ink(asked, *g["prompt"])
    check(prompt_ink > 200,
          f"the prompt is drawn ({prompt_ink} px) -- THE check: without it a "
          f"machine with an encrypted disk waits with no sign of it")
    dimmed = ink(asked, *g["mark"])
    check(dimmed < mark_bright,
          f"the mark dims behind it ({dimmed} < {mark_bright} px)")
    check(bullet_groups(asked, *g["bullets"]) == 0, "no bullets before typing")

    print("a passphrase is typed")
    n = bullet_groups(typed, *g["bullets"])
    check(n == 7,
          f"one bullet per character: {n} for 'hunter2' -- sprites made inside "
          f"a callback are discarded, and that draws exactly zero")

    print("it is entered")
    check(ink(entered, *g["prompt"]) == 0,
          "the prompt is torn down -- display_normal; forgetting it leaves the "
          "prompt over the rest of the boot")
    check(bullet_groups(entered, *g["bullets"]) == 0, "the bullets are gone")
    back = ink(entered, *g["mark"])
    check(back > dimmed, f"the mark comes back up ({back} > {dimmed} px)")

    if fails:
        print(f"\nFAILED: {len(fails)} of the boot states is wrong")
        return 1
    print("\n[ok] every state the theme is asked for is on screen, and torn "
          "down again")
    return 0


if __name__ == "__main__":
    sys.exit(main())
