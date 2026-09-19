#!/usr/bin/env python3
"""
Generate the Calamares branding artwork for octagonOS.

The installer's mark is the same octagon as the boot splash, the icon theme
and the Android boot animation: one renderer in shared/facetui, called here
too. A separate logo drawn by hand would drift from the rest the first time
anybody adjusted the facets, and the whole argument of this project is that
the mark is one piece of maths rather than a family of lookalikes.

    desktop/installer/make-branding.py [out-dir]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from PIL import Image

from shared.facetui.tile import render_tile

#: Calamares scales these itself, so they are generated once at a size that
#: survives a HiDPI sidebar without being resampled up.
LOGO_PX = 256
ICON_PX = 128


def write(path, px):
    # The same apothem/seam ratio the icon theme uses, so the installer's
    # octagon is the icon theme's octagon at a different size rather than a
    # coarser drawing of it.
    apothem = px * 0.47
    tile = render_tile(px, apothem, seam_scale=apothem / 36.0)
    tile.save(path)
    return path


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "calamares" / "branding" / "octagonos"
    out.mkdir(parents=True, exist_ok=True)

    write(out / "logo.png", LOGO_PX)
    write(out / "icon.png", ICON_PX)

    # The welcome image is the logo on a transparent field twice its width, so
    # Calamares' banner area does not stretch a square.
    logo = Image.open(out / "logo.png").convert("RGBA")
    banner = Image.new("RGBA", (LOGO_PX * 2, LOGO_PX), (0, 0, 0, 0))
    banner.paste(logo, (LOGO_PX // 2, 0), logo)
    banner.save(out / "welcome.png")

    print(f"[*] branding written to {out}")


if __name__ == "__main__":
    main()
