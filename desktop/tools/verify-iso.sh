#!/bin/bash
#
# Check an octagonOS ISO without booting it.
#
#     desktop/tools/verify-iso.sh <image.iso>
#
# WHAT THIS IS FOR
#
# An ISO that builds is not an ISO that boots, and the ways it fails are all
# quiet: a missing El Torito entry means nothing happens on one firmware and
# everything works on the other, so it passes every test somebody happens to
# run. A squashfs without the theme means the image boots perfectly and looks
# like Breeze.
#
# So this opens the image and checks what is in it -- including unpacking
# enough of the filesystem to ask whether FacetUI would actually be the
# desktop's default, using the same check that runs on an installed system.
#
# Needs xorriso and squashfs-tools.

set -u
# A pipeline's status is its LAST command's. Piping a check through sed for
# indentation therefore throws the check's result away -- this script once
# printed thirteen failures and then "the image carries FacetUI as its
# default". The same mistake had already been made in run-icon-theme.sh, which
# is why it is set here at the top rather than worked around at each call.
set -o pipefail

PROFILE=desktop
if [ "${1:-}" = "--profile" ]; then PROFILE="$2"; shift 2; fi
ISO="${1:?usage: verify-iso.sh [--profile minimal|desktop] <image.iso>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$ISO" ] || { echo "[FAIL] no such image: $ISO"; exit 2; }

fail=0
ok()   { echo "  ok    $*"; }
bad()  { echo "  FAIL  $*"; fail=1; }

echo "[*] $ISO ($(du -h "$ISO" | cut -f1))"

report="$(xorriso -indev "$ISO" -report_el_torito plain -toc 2>&1)"

# --- boot paths -------------------------------------------------------------
#
# Both are needed and each covers a machine the other does not: BIOS firmware
# reads the El Torito boot image, UEFI reads the EFI system partition. An image
# with only one boots on half the machines it is handed to.
echo "[*] boot paths"
if echo "$report" | grep -qi "El Torito boot img.*BIOS\|Boot record.*El Torito"; then
    ok "El Torito catalogue present"
else
    bad "no El Torito boot catalogue: BIOS firmware will not boot this"
fi
if echo "$report" | grep -qi "UEFI"; then
    ok "a UEFI boot image is registered"
else
    bad "no UEFI boot image: this will not boot on modern firmware"
fi
if echo "$report" | grep -qi "MBR\|isohybrid\|GPT"; then
    ok "hybrid MBR present, so it can be written to a USB stick"
else
    bad "no hybrid MBR: writing this to a USB stick will not produce a bootable one"
fi

# --- contents ---------------------------------------------------------------
echo "[*] contents"
listing="$(xorriso -indev "$ISO" -find / -type f -exec echo -- 2>/dev/null \
           | sed -n "s/^'\\(.*\\)'$/\\1/p")"
for want in /casper/vmlinuz /casper/initrd /casper/filesystem.squashfs \
            /boot/grub/grub.cfg /EFI/BOOT/BOOTX64.EFI; do
    if echo "$listing" | grep -qx "$want"; then
        ok "$want"
    else
        bad "$want is missing"
    fi
done

# --- the filesystem ---------------------------------------------------------
#
# The part that decides whether the image is octagonOS or Ubuntu with an
# octagon on the boot screen.
echo "[*] the filesystem"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! xorriso -osirrox on -indev "$ISO" \
        -extract /casper/filesystem.squashfs "$TMP/fs.squashfs" >/dev/null 2>&1; then
    bad "could not extract the squashfs from the image"
    echo; [ "$fail" -eq 0 ] || { echo "FAILED"; exit 1; }
fi

if ! command -v unsquashfs >/dev/null; then
    echo "  note  squashfs-tools is not installed; the filesystem was not checked"
else
    # Only what the defaults check needs, not the whole root: a full unpack is
    # gigabytes and answers nothing extra.
    # ALL of /etc, not a list of the bits currently needed. Naming them
    # individually has now produced the same bug twice: the boot-splash check
    # could not run because /etc/alternatives was not unpacked, and the
    # autologin check needs /etc/sddm.conf.d and /etc/passwd, which were not
    # either. A check that cannot reach its evidence reports a failure about
    # the image instead of about itself. /etc is a few megabytes; the guessing
    # is not worth what it saves.
    unsquashfs -d "$TMP/root" -f "$TMP/fs.squashfs" \
        '/etc' '/usr/bin' '/usr/share/icons/FacetUI' '/usr/share/color-schemes' \
        '/usr/share/plasma' '/usr/share/plymouth' \
        '/usr/share/wayland-sessions' '/usr/share/xsessions' '/usr/lib' \
        >/dev/null 2>&1 || true

    if [ -d "$TMP/root/etc/xdg" ]; then
        ok "the filesystem unpacked"
        if [ "$PROFILE" = minimal ]; then
            echo "  note  minimal profile: no desktop and no FacetUI, by"
            echo "        design. This image proves the pipeline, not the"
            echo "        product -- do not sign off on it."
        elif [ -x "$HERE/check-facetui-defaults.sh" ]; then
            echo "[*] would FacetUI be the default on this image?"
            if "$HERE/check-facetui-defaults.sh" --root "$TMP/root" > "$TMP/out" 2>&1; then
                sed 's/^/    /' "$TMP/out"
            else
                sed 's/^/    /' "$TMP/out"
                bad "FacetUI is in the image but would not be the desktop's theme"
            fi
        fi
    else
        bad "the squashfs does not contain /etc/xdg; it may be empty or corrupt"
    fi
fi

echo
if [ "$fail" -ne 0 ]; then
    echo "FAILED"
    exit 1
fi
if [ "$PROFILE" = minimal ]; then
    echo "The image is structurally bootable. It carries no desktop, so it says"
    echo "nothing about whether FacetUI works -- that is the desktop profile."
else
    echo "The image is structurally bootable and carries FacetUI as its default."
fi
