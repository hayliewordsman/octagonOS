#!/bin/bash
#
# Build the octagonOS FacetUI packages.
#
#     desktop/packaging/build-debs.sh [out-dir]
#
# WHY A STAGING TREE
#
# Debian builds from the root of a source tree, and this repository's root is
# two products. So the desktop edition and the shared FacetUI core are staged
# into one directory with debian/ at its top, and the package is built there.
# The alternative -- a debian/ at the repository root -- would claim the
# Android half is part of this source package, which it is not.
#
# The generators run during the build (see debian/rules), so a .deb cannot
# disagree with the source it was built from, and the static verifiers run as
# the build's test step: a package that installs a theme its own verifier
# rejects is worse than a build failure, because it reaches a machine.
#
# Needs: debhelper, cmake, and the KWin/KF6/Qt6 development packages. See
# desktop/kwin/README.md for where to get Plasma 6 on a distribution that has
# no Plasma 6.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:-$ROOT/desktop/packaging/out}"
STAGE="${STAGE_DIR:-/tmp/octagonos-facetui-build}"

echo "[*] staging the source tree"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# The staged tree MIRRORS the repository, minus the Android half. It has to:
# every generator and verifier resolves shared/ as its own directory's
# grandparent, so flattening desktop/ away puts shared/ one level too high and
# the first generator fails with ModuleNotFoundError.
mkdir -p "$STAGE/desktop"
for d in plasma icons plymouth kwin tools; do
    cp -r "$ROOT/desktop/$d" "$STAGE/desktop/$d"
done
cp -r "$ROOT/shared"      "$STAGE/shared"
cp -r "$HERE/debian"      "$STAGE/debian"
cp -r "$HERE/defaults"    "$STAGE/defaults"
cp -r "$HERE/lookandfeel" "$STAGE/lookandfeel"

# Proof the layout is the one the tools expect, rather than a hope.
python3 - "$STAGE" <<'PYCHECK'
import pathlib, sys
stage = pathlib.Path(sys.argv[1])
here = stage / "desktop" / "plasma"
resolved = here.parent.parent / "shared" / "facetui"
if not resolved.is_dir():
    raise SystemExit(f"[FAIL] a generator in {here} would look for shared/ at "
                     f"{resolved}, which does not exist")
PYCHECK

echo "[*] building"
cd "$STAGE"
dpkg-buildpackage -b -us -uc --no-sign

mkdir -p "$OUT"
mv /tmp/*.deb "$OUT"/ 2>/dev/null || mv "$STAGE/../"*.deb "$OUT"/ 2>/dev/null || true
echo
echo "[*] packages in $OUT"
ls -1 "$OUT"/*.deb 2>/dev/null || { echo "[FAIL] no .deb was produced"; exit 1; }
