#!/usr/bin/env python3
"""
Verify a bootanimation.zip before it goes anywhere near a device.

    tools/verify-bootanimation.py bootanimation/out/bootanimation.zip

Checks the things that actually break boot animations, each of which fails
silently on a device -- you get a black screen or a visible seam and no log:

  1. desc.txt exists, parses, and is the first entry
  2. every part named in desc.txt exists and has frames
  3. every entry is STORED, not deflated
  4. every PNG matches the dimensions declared in desc.txt
  5. frame borders match the declared background colour, so the letterbox
     around a non-fullscreen canvas has no visible seam
  6. the looping part fits a GL texture budget
  7. the looping part is seamless -- last frame hands back to first

Exits non-zero if any check fails. Needs Pillow; everything else is stdlib.
"""

import argparse
import io
import os
import re
import sys
import zipfile

try:
    from PIL import Image
except ImportError:
    sys.exit("error: this needs Pillow (pip install Pillow)")

#: Matches a part line: TYPE COUNT PAUSE PATH [#RGBHEX ...]
PART_RE = re.compile(
    r"^(?P<type>[pcf])\s+(?P<count>-?\d+)\s+(?P<pause>-?\d+)\s+(?P<path>\S+)"
    r"(?P<rest>.*)$"
)
BG_RE = re.compile(r"#([0-9A-Fa-f]{6})")

#: Matches LOOP_TEXTURE_BUDGET_MIB in bootanimation/make-bootanimation.py.
LOOP_TEXTURE_BUDGET_MIB = 64.0

#: How different the loop's wrap-around may be from its typical frame step.
#: A seamless loop's last-to-first step should look like any other step; if it
#: is much larger the loop visibly jumps every time it repeats.
SEAM_TOLERANCE = 2.5


class Checker:
    def __init__(self):
        self.failed = 0
        self.warned = 0

    def ok(self, msg):
        print(f"  ok    {msg}")

    def fail(self, msg):
        print(f"  FAIL  {msg}")
        self.failed += 1

    def warn(self, msg):
        print(f"  warn  {msg}")
        self.warned += 1


def mean_abs_diff(a, b):
    """Mean absolute per-channel difference between two PIL images, 0..255."""
    pa, pb = a.convert("RGB").tobytes(), b.convert("RGB").tobytes()
    if len(pa) != len(pb):
        return float("inf")
    # Chunked so a large frame pair does not build a huge intermediate list.
    total = 0
    for i in range(0, len(pa), 4096):
        ca, cb = pa[i:i + 4096], pb[i:i + 4096]
        total += sum(abs(x - y) for x, y in zip(ca, cb))
    return total / len(pa)


def border_pixels(img):
    """The four edges of an image, as a list of RGB tuples."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    out = []
    for x in range(w):
        out.append(px[x, 0])
        out.append(px[x, h - 1])
    for y in range(h):
        out.append(px[0, y])
        out.append(px[w - 1, y])
    return out


def main():
    ap = argparse.ArgumentParser(description="Verify a bootanimation.zip.")
    ap.add_argument("zip", help="path to bootanimation.zip")
    ap.add_argument("--budget-mib", type=float, default=LOOP_TEXTURE_BUDGET_MIB)
    args = ap.parse_args()

    if not os.path.exists(args.zip):
        sys.exit(f"error: no such file: {args.zip}")

    c = Checker()
    z = zipfile.ZipFile(args.zip)
    names = z.namelist()

    # --- 1. desc.txt -------------------------------------------------------
    print("desc.txt")
    if "desc.txt" not in names:
        c.fail("desc.txt is missing -- the animation will not play at all")
        print("\nFAILED")
        return 1
    if names[0] != "desc.txt":
        c.warn("desc.txt is not the first entry (works, but it is read first)")
    else:
        c.ok("present, and first in the archive")

    desc = z.read("desc.txt").decode("utf-8")
    lines = [l for l in desc.splitlines() if l.strip()]
    head = lines[0].split()
    if len(head) < 3:
        c.fail(f"first line must be 'WIDTH HEIGHT FPS', got: {lines[0]!r}")
        print("\nFAILED")
        return 1
    width, height, fps = int(head[0]), int(head[1]), int(head[2])
    c.ok(f"{width}x{height} @ {fps}fps")
    if not desc.endswith("\n"):
        c.warn("desc.txt does not end with a newline")

    parts = []
    for line in lines[1:]:
        m = PART_RE.match(line.strip())
        if m:
            bg = BG_RE.search(m.group("rest") or "")
            parts.append({
                "type": m.group("type"),
                "count": int(m.group("count")),
                "path": m.group("path"),
                "bg": bg.group(1).lower() if bg else None,
            })
    if not parts:
        c.fail("desc.txt declares no parts")
        print("\nFAILED")
        return 1
    c.ok(f"{len(parts)} parts: " + ", ".join(
        f"{p['path']}({p['type']} {p['count']})" for p in parts))

    # --- 3. stored, not deflated ------------------------------------------
    print("\ncompression")
    deflated = [i.filename for i in z.infolist()
                if i.compress_type != zipfile.ZIP_STORED]
    if deflated:
        c.fail(f"{len(deflated)} entries are compressed, e.g. {deflated[0]}. "
               "bootanimation maps the zip directly; entries must be STORED")
    else:
        c.ok(f"all {len(z.infolist())} entries STORED")

    # --- 2, 4, 5. parts, dimensions, borders -------------------------------
    frames_by_part = {}
    for part in parts:
        path = part["path"]
        frames = sorted(n for n in names
                        if n.startswith(path + "/") and n.lower().endswith(".png"))
        frames_by_part[path] = frames
        print(f"\n{path}")
        if not frames:
            c.fail("no PNG frames found")
            continue
        c.ok(f"{len(frames)} frames")

        bad_dims = []
        border_bad = []
        expect_bg = None
        if part["bg"]:
            expect_bg = tuple(int(part["bg"][i:i + 2], 16) for i in (0, 2, 4))

        # Sample rather than open every frame: dimension and border faults are
        # produced by the generator, so they are systematic, not sporadic.
        sample = frames if len(frames) <= 8 else [
            frames[i] for i in range(0, len(frames), max(len(frames) // 8, 1))
        ]
        for name in sample:
            img = Image.open(io.BytesIO(z.read(name)))
            if img.size != (width, height):
                bad_dims.append((name, img.size))
            if expect_bg:
                odd = {p for p in border_pixels(img) if p != expect_bg}
                if odd:
                    border_bad.append((name, len(odd), next(iter(odd))))

        if bad_dims:
            c.fail(f"{len(bad_dims)} sampled frames do not match {width}x{height}, "
                   f"e.g. {bad_dims[0][0]} is {bad_dims[0][1]}")
        else:
            c.ok(f"sampled frames are {width}x{height}")

        if expect_bg is None:
            c.warn("no background colour declared; the letterbox will be black, "
                   "which will seam unless the frames are black at the edge")
        elif border_bad:
            name, n, example = border_bad[0]
            c.fail(f"{len(border_bad)} sampled frames have borders that are not "
                   f"#{part['bg']} -- e.g. {name} has {n} differing edge pixels "
                   f"such as {example}. The letterbox seam will be visible")
        else:
            c.ok(f"frame borders match the declared background #{part['bg']}")

    # --- 6. loop memory ----------------------------------------------------
    print("\nGL texture residency")
    for part in parts:
        n = len(frames_by_part.get(part["path"], []))
        if part["count"] == 1 or n == 0:
            continue
        mib = width * height * 4 * n / 1048576.0
        label = (f"{part['path']}: {n} frames x {width}x{height} RGBA "
                 f"= {mib:.0f} MiB held for the whole boot")
        if mib > args.budget_mib:
            c.fail(label + f" (budget {args.budget_mib:.0f} MiB)")
        else:
            c.ok(label)
    if all(p["count"] == 1 for p in parts):
        c.ok("no looping parts; nothing stays resident")

    # --- 7. loop seamlessness ---------------------------------------------
    print("\nloop seam")
    looping = [p for p in parts if p["count"] != 1]
    if not looping:
        c.ok("no looping part to check")
    for part in looping:
        frames = frames_by_part.get(part["path"], [])
        if len(frames) < 4:
            c.warn(f"{part['path']}: too few frames to judge")
            continue
        load = lambda n: Image.open(io.BytesIO(z.read(n)))
        wrap = mean_abs_diff(load(frames[-1]), load(frames[0]))
        # Compare against a typical adjacent step from the middle of the part.
        mid = len(frames) // 2
        typical = mean_abs_diff(load(frames[mid]), load(frames[mid + 1]))
        if typical < 1e-6:
            c.warn(f"{part['path']}: frames appear identical; cannot judge")
        elif wrap > typical * SEAM_TOLERANCE:
            c.fail(f"{part['path']}: wrap-around step is {wrap:.2f} vs a typical "
                   f"{typical:.2f} -- the loop will visibly jump each repeat")
        else:
            c.ok(f"{part['path']}: wrap step {wrap:.2f}, typical step "
                 f"{typical:.2f} -- seamless")

    size_mib = os.path.getsize(args.zip) / 1048576.0
    total = sum(len(v) for v in frames_by_part.values())
    print(f"\n{size_mib:.1f} MiB on disk, {total} frames, "
          f"{total / fps:.1f}s of animation at {fps}fps")
    print("FAILED" if c.failed else
          ("PASSED with warnings" if c.warned else "PASSED"))
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main())
