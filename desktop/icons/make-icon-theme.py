#!/usr/bin/env python3
"""
Build the FacetUI freedesktop icon theme.

    ./make-icon-theme.py

Produces, under FacetUI/:

    index.theme            the theme, its sizes and what it inherits
    apps/<size>/<name>.png the glass octagon with a glyph on it

The glass tile comes from `shared/facetui/tile.py` -- the same code the Android
icon pack renders its adaptive-icon background from -- so an icon here and an
icon on the phone are the same surface, lit from the same angle, by the same
maths.

WHY PNG AND NOT SVG

The glass is exponential falloffs: an edge highlight, a rim darkening, a
specular term over eight facets. A vector has no way to express them, which is
the same reason the Android pack ships the tile as a raster and the glyphs as
vectors. Here the whole icon is composited and rendered at each size a
freedesktop theme ships, so each one is drawn at the resolution it is used at
rather than resampled from one.

WHAT IT COVERS, AND WHAT IT DOES NOT

The standard freedesktop names, plus the application ids of programs a desktop
is likely to have. Everything else falls through `Inherits`, which is the
mechanism the format provides and the honest answer: an icon theme that claimed
to have drawn every icon in existence would be lying about roughly all of them.

Requires Pillow, NumPy and cairosvg.
"""

import argparse
import math
import os
import pathlib
import sys

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "shared"))

from facetui.glyphs import GLYPHS  # noqa: E402
from facetui.palette import ACCENT_A, ACCENT_B  # noqa: E402
from facetui.tile import TABLE_FRAC, render_tile, table_radius  # noqa: E402

THEME = "FacetUI"

#: The sizes a freedesktop theme is expected to carry. Each is rendered, not
#: resampled: the glass has a specular edge whose width does not scale linearly,
#: so a 16px icon downsampled from 256 is a grey smudge with a bright rim.
SIZES = [16, 22, 24, 32, 48, 64, 128, 256]

#: How much of the icon box the octagon fills, as a fraction of the box width.
#:
#: Larger than the Android pack's 1/3, because that reserves the outer edge of
#: an adaptive icon for parallax bleed and a desktop icon has no such reserve.
#: 0.47 leaves a small margin so neighbouring icons in a grid do not touch.
APOTHEM_FRAC = 0.47

#: The clearance the Android pack ships: its widest glyph reaches 27.9 against
#: a table edge of 30.24. Matched here rather than re-chosen, so a glyph sits
#: the same distance inside the calm centre on both editions.
GLYPH_CLEARANCE = 27.9 / 30.24

#: Resolution the glyph extents are measured at. High enough that a curve's
#: true extremum is found rather than the nearest of a few sampled points.
MEASURE_PX = 512

#: What the theme falls back to. Breeze first because this is a Plasma desktop;
#: hicolor last because the spec requires it to be reachable.
INHERITS = "breeze,hicolor"

#: Freedesktop names, and the application ids of things a desktop tends to
#: have, mapped onto the glyphs in shared/facetui/glyphs.py.
#:
#: The standard names come first in each list and are the ones that matter: a
#: correctly written application asks for `utilities-terminal`, not for its own
#: name. The application ids are there for the ones that do not.
NAMES = {
    "settings": ["preferences-system", "systemsettings", "configure",
                 "preferences-desktop", "gnome-control-center"],
    "phone": ["call-start", "phone", "kde-telephony"],
    "dialer": ["call-start-symbolic", "dialer-app", "org.kde.plasma.dialer"],
    "contacts": ["x-office-address-book", "address-book-new", "contacts",
                 "kaddressbook", "org.kde.kaddressbook"],
    "messaging": ["internet-chat", "user-available", "telegram", "signal-desktop",
                  "org.kde.neochat"],
    "camera": ["camera-photo", "camera-video", "cheese", "org.kde.kamoso"],
    "gallery": ["multimedia-photo-viewer", "image-viewer", "gwenview",
                "org.kde.gwenview", "eog", "shotwell"],
    "music": ["multimedia-audio-player", "audio-x-generic", "rhythmbox",
              "org.kde.elisa", "spotify", "audacious"],
    "video": ["multimedia-video-player", "video-x-generic", "vlc", "mpv",
              "org.kde.haruna", "totem"],
    "browser": ["web-browser", "internet-web-browser", "firefox", "chromium",
                "google-chrome", "org.kde.falkon", "brave-browser"],
    "email": ["internet-mail", "mail-client", "thunderbird", "kmail",
              "org.kde.kmail2", "evolution"],
    "calendar": ["office-calendar", "x-office-calendar", "korganizer",
                 "org.kde.korganizer", "calendar"],
    "clock": ["clock", "alarm", "org.kde.kclock", "gnome-clocks",
              "preferences-system-time"],
    "calculator": ["accessories-calculator", "kcalc", "org.kde.kcalc",
                   "gnome-calculator"],
    "notes": ["accessories-text-editor", "text-editor", "kate", "org.kde.kate",
              "gedit", "org.gnome.TextEditor", "accessories-notes"],
    "files": ["system-file-manager", "folder", "inode-directory", "dolphin",
              "org.kde.dolphin", "nautilus", "thunar"],
    "terminal": ["utilities-terminal", "terminal", "konsole", "org.kde.konsole",
                 "org.gnome.Terminal", "alacritty"],
    "store": ["system-software-install", "software-store", "plasma-discover",
              "org.kde.discover", "gnome-software"],
    "updater": ["system-software-update", "system-upgrade", "update-notifier"],
    "security": ["preferences-desktop-security", "security-high", "changes-prevent",
                 "org.kde.kwalletmanager5", "keepassxc"],
    "storage": ["drive-harddisk", "drive-removable-media", "partitionmanager",
                "org.kde.partitionmanager", "gnome-disks"],
    "search": ["system-search", "edit-find", "search", "krunner",
               "org.kde.krunner"],
    "weather": ["weather-clear", "weather-few-clouds", "org.kde.plasma.weather"],
    "recorder": ["audio-input-microphone", "media-record", "audio-recorder",
                 "org.kde.krecorder"],
    "generic": ["application-x-executable", "applications-other",
                "application-default-icon", "unknown"],
}


def octagon_distance(dx, dy):
    """How far a point is out along the octagon, in whatever units come in."""
    return max(dx * math.cos(k * 2.0 * math.pi / 8)
               + dy * math.sin(k * 2.0 * math.pi / 8) for k in range(8))


def rasterise_glyph(path_data, px):
    """One glyph's path, filled white, as an alpha mask `px` wide.

    The glyph artwork is authored on a 100-unit viewport, so this renders that
    viewport at `px` and hands back the coverage.
    """
    import cairosvg
    import io
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" '
           f'height="{px}" viewBox="0 0 100 100">'
           f'<path d="{path_data}" fill="#ffffff" fill-rule="evenodd"/></svg>')
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode(), write_to=buf,
                     output_width=px, output_height=px)
    buf.seek(0)
    return np.asarray(Image.open(buf).convert("RGBA"))[..., 3]


def measure_extents():
    """The furthest each glyph reaches from its centre, in 100-unit terms.

    Measured from the RENDERED coverage, not from the path's control points: a
    cubic's extremum is usually not one of its control points, and a glyph that
    bulges between them would be measured as smaller than it is.
    """
    out = {}
    ys, xs = np.mgrid[0:MEASURE_PX, 0:MEASURE_PX].astype(np.float32)
    c = MEASURE_PX / 2.0
    dist = np.maximum.reduce([
        (xs - c) * math.cos(k * 2.0 * math.pi / 8)
        + (ys - c) * math.sin(k * 2.0 * math.pi / 8) for k in range(8)])
    for name, data in GLYPHS.items():
        alpha = rasterise_glyph(data, MEASURE_PX)
        ink = alpha > 8
        out[name] = float(dist[ink].max()) / MEASURE_PX * 100.0 if ink.any() else 0.0
    return out


def glyph_colour():
    """The glyph fill: near-white, with a trace of the accent.

    Flat and light, because it sits ON the glass. A glyph tinted as strongly as
    the surface competes with it, and a dark one disappears into the table's
    own shading.
    """
    c = np.clip((ACCENT_A * 0.5 + ACCENT_B * 0.5) * 0.22 + 0.86, 0.0, 1.0)
    return tuple(int(round(v * 255)) for v in c)


def compose(px, path_data, scale, colour):
    """One icon: the glass tile, with the glyph laid on the table."""
    apothem = px * APOTHEM_FRAC
    # The seams scale with the octagon, not with the canvas. Android's tile is
    # a third of a 108-unit drawable, so its seam width is the apothem over 36;
    # keeping that ratio makes a desktop icon read as the same object rather
    # than a coarser one.
    tile = render_tile(px, apothem, seam_scale=apothem / 36.0)

    # The glyph is rendered at the size it will occupy, not rendered large and
    # shrunk: a single-weight outline resampled down loses its weight.
    inner = max(int(round(px * scale)), 1)
    alpha = rasterise_glyph(path_data, inner)
    glyph = Image.new("RGBA", (inner, inner), colour + (0,))
    glyph.putalpha(Image.fromarray(alpha))

    off = (px - inner) // 2
    tile.alpha_composite(glyph, (off, off))
    return tile


INDEX_HEADER = """[Icon Theme]
Name={name}
Comment=Glass octagons, from FacetUI
Inherits={inherits}
Directories={dirs}

"""

INDEX_SECTION = """[apps/{size}]
Size={size}
Context=Applications
Type=Fixed

"""


def main():
    ap = argparse.ArgumentParser(description="Build the FacetUI icon theme.")
    ap.add_argument("--out", default=str(HERE / THEME))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out)

    def note(m):
        if not args.quiet:
            print(m, file=sys.stderr)

    note("[*] measuring glyph extents")
    extents = measure_extents()
    worst_name = max(extents, key=extents.get)
    worst = extents[worst_name]

    # One scale for every glyph, set by the widest of them, exactly as the
    # Android pack does. Deriving it rather than choosing it means a new glyph
    # that is wider than the rest tightens the whole set instead of quietly
    # overhanging the table on its own.
    table_r = table_radius(APOTHEM_FRAC)          # as a fraction of the box
    scale = GLYPH_CLEARANCE * table_r / (worst / 100.0)
    note(f"    widest is '{worst_name}' at {worst:.1f}/100; "
         f"table edge at {table_r * 100:.1f}/100 of the box")
    note(f"    glyph scale {scale:.4f} -> it lands at "
         f"{worst / 100.0 * scale * 100:.1f}, clearance "
         f"{worst / 100.0 * scale / table_r:.3f}")

    colour = glyph_colour()

    names = {}
    for glyph, aliases in NAMES.items():
        if glyph not in GLYPHS:
            raise SystemExit(f"NAMES maps to unknown glyph {glyph!r}")
        for alias in aliases:
            if alias in names:
                raise SystemExit(f"icon name {alias!r} is claimed twice")
            names[alias] = glyph

    written = 0
    for size in SIZES:
        d = out / "apps" / str(size)
        d.mkdir(parents=True, exist_ok=True)
        rendered = {}
        for glyph in NAMES:
            rendered[glyph] = compose(size, GLYPHS[glyph], scale, colour)
        for alias, glyph in names.items():
            rendered[glyph].save(d / f"{alias}.png")
            written += 1
        note(f"    {size:>3}px  {len(names)} icons")

    dirs = ",".join(f"apps/{s}" for s in SIZES)
    text = INDEX_HEADER.format(name=THEME, inherits=INHERITS, dirs=dirs)
    for size in SIZES:
        text += INDEX_SECTION.format(size=size)
    (out / "index.theme").write_text(text)

    note(f"[*] {out}")
    note(f"    {written} icons: {len(names)} names over {len(SIZES)} sizes, "
         f"from {len(NAMES)} glyphs")
    note(f"    everything else inherits from {INHERITS}")


if __name__ == "__main__":
    main()
