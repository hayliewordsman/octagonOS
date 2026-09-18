#!/bin/bash
#
# Is FacetUI the desktop's default, or just one of its options?
#
#     desktop/tools/check-facetui-defaults.sh [--root <dir>]
#
# WHY THIS IS A CHECK AND NOT A README PARAGRAPH
#
# "Installed" and "in use" are different states, and the gap between them is
# invisible. Every piece of FacetUI can be present and correct while the
# desktop draws Breeze, because Plasma reads its settings from kdeglobals and
# plasmarc, and nothing puts them there just because a package landed.
#
# The trap in particular: naming a look-and-feel package does NOT apply its
# contents. Those are written out only when somebody selects the theme in
# System Settings. Tested directly -- with only LookAndFeelPackage set, the
# icon theme read back unset. So the individual keys have to be shipped too,
# and this checks that they are, by resolving them THE WAY A COMPONENT WOULD:
# through the XDG cascade, as a user with an empty home directory.
#
# --root points at a chroot, so the same check runs against an image before it
# is ever booted.

set -u

ROOT=""
if [ "${1:-}" = "--root" ]; then
    ROOT="${2:?--root needs a directory}"
fi

command -v kreadconfig6 >/dev/null || {
    echo "[FAIL] kreadconfig6 is not installed; cannot resolve settings the"
    echo "       way a Plasma component does"
    exit 2
}

HOMEDIR="$(mktemp -d)"
trap 'rm -rf "$HOMEDIR"' EXIT
mkdir -p "$HOMEDIR/.config"

# A user with nothing of their own. On a fresh install or a live session that
# is every user, which is the case this has to be right for.
read_key() {
    HOME="$HOMEDIR" XDG_CONFIG_HOME="$HOMEDIR/.config" \
    ${ROOT:+XDG_CONFIG_DIRS="$ROOT/etc/xdg"} \
        kreadconfig6 --file "$1" --group "$2" --key "$3" --default "<unset>"
}

fail=0
check_key() {
    local file="$1" group="$2" key="$3" want="$4"
    local got
    got="$(read_key "$file" "$group" "$key")"
    if [ "$got" = "$want" ]; then
        printf "  ok    %-10s [%s] %s = %s\n" "$file" "$group" "$key" "$got"
    else
        printf "  FAIL  %-10s [%s] %s = %s, wanted %s\n" \
            "$file" "$group" "$key" "$got" "$want"
        fail=1
    fi
}

echo "[*] what a user with an empty home directory gets"
check_key kdeglobals Icons   Theme                FacetUI
check_key kdeglobals General ColorScheme          FacetUI
check_key kdeglobals KDE     LookAndFeelPackage   dev.octagonos.facetui
check_key plasmarc   Theme   name                 FacetUI
check_key kwinrc     Plugins facetui-glassEnabled true
check_key kwinrc     Plugins blurEnabled          true

# A setting naming a resource that is not installed is worse than no setting:
# the component falls back silently and the desktop looks half-themed.
echo "[*] and the resources those names resolve to"
for p in \
    /usr/share/icons/FacetUI/index.theme \
    /usr/share/color-schemes/FacetUI.colors \
    /usr/share/plasma/desktoptheme/FacetUI/metadata.json \
    /usr/share/plasma/look-and-feel/dev.octagonos.facetui/metadata.json \
    /usr/share/plymouth/themes/octagonos/octagonos.plymouth
do
    if [ -e "$ROOT$p" ]; then
        printf "  ok    %s\n" "$p"
    else
        printf "  FAIL  %s is named by a default but is not installed\n" "$p"
        fail=1
    fi
done

# The effect is architecture-dependent, so its path is not fixed.
if compgen -G "$ROOT/usr/lib/*/qt6/plugins/kwin/effects/plugins/facetui-glass.so" >/dev/null; then
    echo "  ok    the KWin effect plugin is installed"
else
    echo "  FAIL  the KWin effect plugin is not installed, so kwinrc enables"
    echo "        an effect that does not exist"
    fail=1
fi

# Plymouth is not an XDG setting at all: the boot theme is an alternative, and
# it is chosen before any user exists.
echo "[*] the boot splash"
alt="$(chroot ${ROOT:-/} update-alternatives --query default.plymouth 2>/dev/null \
       | sed -n 's/^Value: //p')"
case "$alt" in
    */octagonos/octagonos.plymouth)
        echo "  ok    default.plymouth points at octagonos" ;;
    "")
        echo "  FAIL  no default.plymouth alternative is set"; fail=1 ;;
    *)
        echo "  FAIL  default.plymouth points at $alt, not octagonos"; fail=1 ;;
esac

echo
if [ "$fail" -ne 0 ]; then
    echo "FAILED: FacetUI is installed but not selected. A user would have to"
    echo "pick it in System Settings."
    exit 1
fi
echo "FacetUI is the default: a new user gets it without choosing anything."
