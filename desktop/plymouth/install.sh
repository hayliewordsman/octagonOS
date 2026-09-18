#!/bin/bash
#
# Install the octagonOS Plymouth theme on this machine.
#
#     sudo ./install.sh              install, set as default, rebuild initramfs
#     sudo ./install.sh --no-initrd  install and set default, skip the rebuild
#
# THE INITRAMFS REBUILD IS NOT OPTIONAL
#
# Plymouth runs from the initramfs, not from the root filesystem. Copying the
# theme into /usr/share and setting it as the default changes nothing on the
# next boot until the initramfs is rebuilt to carry it. Skipping that is the
# most common way a Plymouth theme appears not to work at all.
#
# It also has to carry the label plugin. Image.Text needs label.so, and without
# it the passphrase prompt renders as nothing. This theme falls back to a
# pre-rendered "Enter passphrase" image in that case -- so the machine is
# usable either way -- but the real prompt, naming the device being unlocked,
# needs the plugin present.

set -euo pipefail

THEME=octagonos
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/$THEME"
DEST="/usr/share/plymouth/themes/$THEME"

[ "${EUID:-$(id -u)}" -eq 0 ] || { echo "install.sh needs root."; exit 1; }
[ -d "$SRC" ] || { echo "No theme at $SRC. Run ./make-plymouth-theme.py first."; exit 1; }

if [ -x "$HERE/../tools/verify-plymouth-theme.py" ]; then
    echo "[*] verifying the theme before installing it"
    "$HERE/../tools/verify-plymouth-theme.py" "$SRC"
fi

echo "[*] installing to $DEST"
rm -rf "$DEST"
install -d -m 755 "$DEST"
install -m 644 "$SRC"/* "$DEST/"

# A stale second .script is not merely untidy: it is the shape of a bug that
# already happened here. Plymouth reads only the ScriptFile named in the
# .plymouth config, so a leftover file looks live and is not.
find "$DEST" -name '*.script' ! -name "$THEME.script" -print -delete

if ! compgen -G "/usr/lib/*/plymouth/label*.so" >/dev/null; then
    echo "[!] No Plymouth label plugin found (label-pango.so / label-freetype.so)."
    echo "    The passphrase prompt will fall back to a pre-rendered image."
    echo "    Install it with:  apt install plymouth-label"
fi

echo "[*] setting $THEME as the default theme"
if command -v plymouth-set-default-theme >/dev/null; then
    plymouth-set-default-theme "$THEME"
else
    # Debian/Ubuntu without the helper: the alternatives system owns the link.
    update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
        default.plymouth "$DEST/$THEME.plymouth" 200
    update-alternatives --set default.plymouth "$DEST/$THEME.plymouth"
fi

if [ "${1:-}" = "--no-initrd" ]; then
    echo "[!] Skipping the initramfs rebuild, as asked."
    echo "    The theme will NOT appear at boot until you run:"
    echo "      update-initramfs -u   (or: dracut -f)"
    exit 0
fi

echo "[*] rebuilding the initramfs so the boot path carries the theme"
if command -v update-initramfs >/dev/null; then
    update-initramfs -u
elif command -v dracut >/dev/null; then
    dracut -f
else
    echo "[!] No update-initramfs or dracut found. Rebuild the initramfs by"
    echo "    hand, or the theme will not appear at boot."
    exit 1
fi

echo
echo "[ok] Installed. To see it without rebooting:"
echo "       plymouthd --mode=boot --tty=/dev/tty1 && plymouth show-splash"
echo "     To see the passphrase screen:"
echo "       plymouth ask-for-password --prompt='Unlock disk'"
