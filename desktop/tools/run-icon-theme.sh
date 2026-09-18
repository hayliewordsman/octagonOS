#!/bin/bash
#
# Build the icon probe, then resolve every icon in the FacetUI theme with Qt's
# own loader, at every size the theme declares -- and validate it for GTK too.
#
#     desktop/tools/run-icon-theme.sh [theme-dir]
#
# WHAT THIS PROVES
#
# A freedesktop icon theme is a directory whose index.theme must agree with
# what is on disk, and nothing in the format checks that. Worse, the spec says
# an unresolvable name falls back -- so a theme with a broken index.theme
# resolves every icon perfectly, to somebody else's.
#
# So each icon is fetched by name and compared against the PNG this theme
# ships. That is the only thing that distinguishes "Qt used our icon" from "Qt
# used Breeze's", and it catches a declared Size that does not match the
# directory it names, because Qt would then resolve the name from a different
# size and the comparison fails.
#
# Needs Qt 6 and, for the GTK check, gtk-update-icon-cache:
#
#   apt install -y --no-install-recommends qt6-base-dev gtk-update-icon-cache

set -u
# A pipeline's exit status is its LAST command's, so piping the probe through
# sed for indentation threw its result away and this script reported success on
# a theme where every icon failed. Found by a mutation suite that scored 0/4
# while printing four correct failures.
set -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
THEME_SRC="${1:-$HERE/../icons/FacetUI}"
THEME_ROOT="$(cd "$(dirname "$THEME_SRC")" && pwd)"
THEME_NAME="$(basename "$THEME_SRC")"
BUILD="${BUILD_DIR:-/tmp/facetui-icon-build}"

echo "[*] building the icon probe"
rm -rf "$BUILD"
if ! cmake -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -S "$HERE/icon-probe" \
        > "$BUILD.cmake.log" 2>&1; then
    echo "[FAIL] cmake could not configure the probe:"
    tail -20 "$BUILD.cmake.log"
    exit 1
fi
if ! cmake --build "$BUILD" > "$BUILD.build.log" 2>&1; then
    echo "[FAIL] the probe does not compile:"
    tail -30 "$BUILD.build.log"
    exit 1
fi
PROBE="$(find "$BUILD" -name icon-probe -type f | head -1)"
[ -n "$PROBE" ] || { echo "[FAIL] the build produced no probe"; exit 1; }

# Every name the theme ships, and every size it declares. Read off the theme
# itself rather than listed here, so a name added to the generator is checked
# without anyone remembering to add it twice.
SIZES="$(sed -n 's/^Size=\([0-9]*\)$/\1/p' "$THEME_SRC/index.theme" | sort -n -u)"
[ -n "$SIZES" ] || { echo "[FAIL] index.theme declares no sizes"; exit 1; }

FIRST_SIZE="$(echo "$SIZES" | head -1)"
NAMES="$(cd "$THEME_SRC/apps/$FIRST_SIZE" && ls *.png | sed 's/\.png$//')"
COUNT="$(echo "$NAMES" | wc -l)"
echo "[*] $COUNT icons, sizes: $(echo $SIZES | tr '\n' ' ')"

fail=0
for size in $SIZES; do
    if ! "$PROBE" "$THEME_ROOT" "$THEME_NAME" "$size" $NAMES | sed 's/^/    /'; then
        fail=1
    fi
done

# GTK reads the same theme through a different loader, and its cache builder is
# a validator: it refuses a theme whose index.theme does not describe what is
# on disk.
if command -v gtk-update-icon-cache >/dev/null; then
    echo "[*] gtk-update-icon-cache"
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    cp -r "$THEME_SRC" "$TMP/$THEME_NAME"
    if gtk-update-icon-cache --quiet --force "$TMP/$THEME_NAME" 2>"$TMP/err"; then
        echo "    [ok]   GTK accepts the theme"
    else
        echo "    [FAIL] GTK rejects the theme:"
        sed 's/^/           /' "$TMP/err"
        fail=1
    fi
else
    echo "[note] gtk-update-icon-cache is not installed; GTK not checked"
fi

echo
if [ "$fail" -ne 0 ]; then
    echo "FAILED"
    exit 1
fi
echo "Every icon resolves to the file this theme ships, at every size it declares."
