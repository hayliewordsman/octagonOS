#!/bin/bash
#
# Build the KSvg probe, install the FacetUI Plasma style, and check that
# Plasma's own SVG engine can use it.
#
#     desktop/tools/run-plasma-theme.sh [theme-dir]
#
# WHAT THIS PROVES
#
# A Plasma theme is a directory of SVGs whose element ids matter and whose
# alpha is the whole design. Nothing in the format checks either. A misspelled
# `bottomright` is not an error -- KSvg draws nothing there and the frame comes
# out with a bite missing. An opaque surface is not an error either; it just
# stops being glass.
#
# So this renders each surface twice, over black and over white, and measures:
# the difference gives the real alpha, and a row inside the top edge gives the
# hairline. Both are properties FacetUI requires and neither is visible to a
# parser.
#
# Needs KSvg's development package and Qt 6. On a distribution without Plasma 6
# (Ubuntu 24.04 among them) the KDE neon archive provides them:
#
#   apt install -y --no-install-recommends \
#       kf6-ksvg-dev extra-cmake-modules qt6-base-dev \
#       libkf6coreaddons-dev libkf6config-dev
#
# Set PROBE_DEBUG_ROW=1 to print the sampled hairline row and the corner
# coverages. That is how the seam below was found.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
THEME_SRC="${1:-$HERE/../plasma/FacetUI}"
BUILD="${BUILD_DIR:-/tmp/facetui-plasma-build}"
RUN="${RUN_DIR:-/tmp/facetui-plasma-run}"

echo "[*] building the KSvg probe"
rm -rf "$BUILD"
if ! cmake -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -S "$HERE/plasma-probe" \
        > "$RUN.cmake.log" 2>&1; then
    echo "[FAIL] cmake could not configure the probe:"
    tail -20 "$RUN.cmake.log"
    exit 1
fi
if ! cmake --build "$BUILD" > "$RUN.build.log" 2>&1; then
    echo "[FAIL] the probe does not compile:"
    tail -30 "$RUN.build.log"
    exit 1
fi

PROBE="$(find "$BUILD" -name plasma-probe -type f | head -1)"
[ -n "$PROBE" ] || { echo "[FAIL] the build produced no probe"; exit 1; }

echo "[*] installing $THEME_SRC"
DEST="$RUN/.local/share/plasma/desktoptheme"
rm -rf "$RUN"; mkdir -p "$DEST"
cp -r "$THEME_SRC" "$DEST/FacetUI"

# The alphas come from shared/facetui/palette.py, not from this script. The
# point of the check is that the theme agrees with the one definition; reading
# them from anywhere else would make it agree with itself.
ALPHAS="$(cd "$HERE/../.." && python3 -c "
import sys; sys.path.insert(0, 'shared')
from facetui.palette import SURFACE_ALPHA as A
print(' '.join([
    f'widgets/panel-background={A[\"shade\"]}',
    f'dialogs/background={A[\"dialog\"]}',
    f'widgets/background={A[\"dialog\"]}',
    f'widgets/tooltip={A[\"tooltip\"]}',
]))")"

# A FRESH CACHE EVERY RUN.
#
# KSvg caches rendered elements on disk, keyed by the theme's NAME. Every
# variant of a theme under test installs as "FacetUI", so without this a run
# happily serves pixmaps rendered from a previous one -- which made a mutation
# suite report 8/8 while two of the mutants were never rendered at all, and the
# failure printed was the one before it.
CACHE="$(mktemp -d)"
trap 'rm -rf "$CACHE"' EXIT

XDG_DATA_HOME="$RUN/.local/share" HOME="$RUN" XDG_CACHE_HOME="$CACHE" \
    "$PROBE" FacetUI "$HERE/plasma-surfaces.png" $ALPHAS
