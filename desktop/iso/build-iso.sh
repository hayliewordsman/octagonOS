#!/bin/bash
#
# Build the octagonOS live ISO.
#
#     sudo desktop/iso/build-iso.sh [--profile minimal|desktop] [out.iso]
#
# WHY NOT livecd-rootfs OR live-build
#
# livecd-rootfs is what Ubuntu's own flavours use and it really wants
# Launchpad. live-build carries a large amount of configuration that mostly
# exists to be overridden. This is debootstrap, a chroot, mksquashfs and
# xorriso, which is what both of those do underneath -- written out, so every
# step is visible and the image can be rebuilt anywhere with those four tools.
#
# THE BASE, AND WHY IT IS PINNED
#
# Ubuntu 24.04's own archive ships KWin 5.27. Everything FacetUI's desktop
# edition needs is KWin 6, which comes from KDE neon -- Ubuntu 24.04 with
# Plasma 6 on top. So the base is Ubuntu plus a pinned neon snapshot, not neon
# tracked live: KWin's effect API is not binary compatible between versions,
# and facetui-kwin-effect is built against exactly one of them.
#
# PROFILES
#
#   desktop  the real image: Plasma on Wayland, and FacetUI as its theme
#   minimal  the same pipeline without Plasma. Builds in minutes rather than
#            an hour and proves the pipeline itself -- but it cannot show the
#            compositor effect, which is the thing the image exists to prove.
#            Use it to debug the build, never to sign off on it.

set -euo pipefail

# RUN FROM A SNAPSHOT OF THIS FILE.
#
# Bash does not read a script into memory. It reads it incrementally, by byte
# offset, as it executes. Edit the file while it is running and the offsets
# stop meaning what they meant: the interpreter resumes in the middle of a
# token and dies with a syntax error at a line it had not reached and which is
# not wrong. A build that takes an hour is exactly long enough for someone --
# me, on 2026-09-18 -- to improve the script it is still executing.
#
# So re-exec from a copy. The copy is unlinked immediately: on Linux the open
# file descriptor keeps the inode alive, so bash reads on happily from a file
# with no name, which is the point. Nothing on disk can be edited any more.
if [ -z "${OCTAGONOS_ISO_PINNED:-}" ]; then
    _snapshot="$(mktemp "${TMPDIR:-/tmp}/build-iso.XXXXXXXX.sh")"
    cat "$0" > "$_snapshot"
    OCTAGONOS_ISO_PINNED="$_snapshot" \
    OCTAGONOS_ISO_HERE="$(cd "$(dirname "$0")" && pwd)" \
        exec bash "$_snapshot" "$@"
fi

# Unlink the snapshot BY NAME, never as "$0": if this variable ever arrived
# from the environment rather than from the block above, "$0" is the real
# script in the repository and deleting it would be the worst kind of tidy-up.
if [ -f "$OCTAGONOS_ISO_PINNED" ]; then rm -f "$OCTAGONOS_ISO_PINNED"; fi

HERE="${OCTAGONOS_ISO_HERE:-$(cd "$(dirname "$0")" && pwd)}"
ROOT="$(cd "$HERE/../.." && pwd)"

PROFILE=desktop
if [ "${1:-}" = "--profile" ]; then PROFILE="$2"; shift 2; fi
OUT="${1:-$ROOT/desktop/iso/out/octagonos-${PROFILE}.iso}"

WORK="${WORK_DIR:-/var/tmp/octagonos-iso}"
CHROOT="$WORK/chroot"
IMAGE="$WORK/image"

SUITE=noble
MIRROR=http://archive.ubuntu.com/ubuntu
NEON=http://archive.neon.kde.org/user

[ "$(id -u)" -eq 0 ] || { echo "This needs root: debootstrap and chroot do."; exit 1; }

say() { echo "[*] $*"; }

# --- the base ---------------------------------------------------------------

if [ ! -d "$CHROOT/etc" ]; then
    say "debootstrapping $SUITE"
    mkdir -p "$CHROOT"
    debootstrap --arch=amd64 --variant=minbase "$SUITE" "$CHROOT" "$MIRROR"
else
    say "reusing the existing chroot at $CHROOT"
fi

# Mounts the chroot needs, and a trap so a failed build does not leave them
# behind holding the directory hostage.
cleanup() {
    for m in dev/pts dev proc sys; do
        mountpoint -q "$CHROOT/$m" && umount -l "$CHROOT/$m" || true
    done
}
trap cleanup EXIT
# Guarded, so a run that died before its trap fired does not leave this one
# stacking a second layer of mounts on top of the first.
mountpoint -q "$CHROOT/dev"     || mount --bind /dev     "$CHROOT/dev"
mountpoint -q "$CHROOT/dev/pts" || mount --bind /dev/pts "$CHROOT/dev/pts"
mountpoint -q "$CHROOT/proc"    || mount -t proc  proc  "$CHROOT/proc"
mountpoint -q "$CHROOT/sys"     || mount -t sysfs sysfs "$CHROOT/sys"

install -d "$CHROOT/etc/apt/sources.list.d" "$CHROOT/etc/apt/preferences.d" \
           "$CHROOT/usr/share/keyrings"

cat > "$CHROOT/etc/apt/sources.list" <<EOF
deb $MIRROR $SUITE main universe multiverse restricted
deb $MIRROR $SUITE-updates main universe multiverse restricted
deb $MIRROR $SUITE-security main universe multiverse restricted
EOF

# Keep the installer from starting services in a chroot that has no init.
cat > "$CHROOT/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
chmod +x "$CHROOT/usr/sbin/policy-rc.d"

in_chroot() { chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
                  LC_ALL=C.UTF-8 "$@"; }

if [ "$PROFILE" = desktop ]; then
    say "adding the pinned Plasma 6 archive"
    cp /usr/share/keyrings/neon.gpg "$CHROOT/usr/share/keyrings/neon.gpg" 2>/dev/null || {
        in_chroot apt-get update >/dev/null
        in_chroot apt-get install -y --no-install-recommends ca-certificates curl gnupg >/dev/null
        in_chroot sh -c "curl -fsSL $NEON/../public.key | gpg --dearmor -o /usr/share/keyrings/neon.gpg"
    }
    echo "deb [signed-by=/usr/share/keyrings/neon.gpg] $NEON $SUITE main" \
        > "$CHROOT/etc/apt/sources.list.d/neon.list"

    # PINNED, not tracked. facetui-kwin-effect is compiled against one KWin;
    # letting the archive move under it is how the effect silently stops
    # loading after an update.
    cat > "$CHROOT/etc/apt/preferences.d/neon-pin" <<'EOF'
Package: *
Pin: origin archive.neon.kde.org
Pin-Priority: 1001
EOF
fi

say "installing the base system"
in_chroot apt-get update
# zstd is not optional-looking but is: without it initramfs-tools falls back
# to gzip with a warning, and the image ends up with a slower, larger initrd
# than a real Ubuntu one. A minbase chroot does not have it.
in_chroot apt-get install -y --no-install-recommends \
    linux-image-generic casper initramfs-tools zstd \
    systemd-sysv sudo locales ca-certificates

if [ "$PROFILE" = desktop ]; then
    say "installing Plasma on Wayland"
    in_chroot apt-get install -y --no-install-recommends \
        plasma-desktop plasma-workspace-wayland kwin-wayland sddm \
        systemsettings dolphin konsole breeze-icon-theme hicolor-icon-theme \
        plymouth plymouth-themes xserver-xorg-core xwayland \
        mesa-vulkan-drivers libgl1-mesa-dri

    say "installing FacetUI"
    install -d "$CHROOT/tmp/debs"
    cp "$ROOT"/desktop/packaging/out/*.deb "$CHROOT/tmp/debs/"
    # --reinstall, and it matters. The FacetUI packages carry a fixed version
    # (0.1) while their contents change every time a generator is edited. On a
    # reused chroot plain `apt-get install` compares versions, finds 0.1 already
    # present, prints "already the newest version" and installs NOTHING -- so
    # the image ships the previous build's theme while the log reads clean.
    # That is the worst shape a bug can take here: a green build that proves
    # the old artefact.
    in_chroot sh -c \
        'apt-get install -y --reinstall --no-install-recommends /tmp/debs/*.deb'
    rm -rf "$CHROOT/tmp/debs"

    # Autologin, so the image proves itself without anyone typing a password.
    install -d "$CHROOT/etc/sddm.conf.d"
    cat > "$CHROOT/etc/sddm.conf.d/octagonos.conf" <<'EOF'
[Autologin]
User=octagon
Session=plasmawayland

[General]
DisplayServer=wayland
EOF
    # Idempotent, because the chroot is deliberately reused between runs and
    # useradd on an existing user exits non-zero -- which under `set -e` ends
    # the build an hour in, on the one path that was supposed to be the fast
    # one. Every other step here is already re-runnable; this was the gap.
    if ! in_chroot id -u octagon >/dev/null 2>&1; then
        in_chroot useradd -m -s /bin/bash -G sudo octagon
    fi
    in_chroot sh -c 'echo "octagon:octagon" | chpasswd'

    # The self-test. Inert unless octagonos.selftest is on the kernel command
    # line, so it ships without running: a user whose machine looks wrong can
    # boot with the flag and get the same answers the build does.
    say "installing the self-test"
    install -D -m 755 "$HERE/selftest/octagonos-selftest.sh" \
        "$CHROOT/usr/lib/octagonos/octagonos-selftest.sh"
    install -D -m 644 "$HERE/selftest/octagonos-selftest.service" \
        "$CHROOT/etc/systemd/system/octagonos-selftest.service"
    in_chroot systemctl enable octagonos-selftest.service
    # busctl, kreadconfig6 and setpriv are what it reports with. kreadconfig6
    # lives in kf6-kconfig -- there is no kf6-kconfig-bin, whatever the split
    # in other frameworks would suggest. Plasma pulls kf6-kconfig in anyway,
    # so naming it here changes nothing about the image; it states the
    # dependency instead of inheriting it by luck, which is what keeps the
    # self-test working if the desktop set is ever trimmed.
    in_chroot apt-get install -y --no-install-recommends \
        kf6-kconfig util-linux
fi

say "cleaning up"
in_chroot apt-get clean
rm -f "$CHROOT/usr/sbin/policy-rc.d"
rm -rf "$CHROOT/tmp/"* "$CHROOT/var/lib/apt/lists/"*

cleanup
trap - EXIT

# --- the image --------------------------------------------------------------

say "assembling the image tree"
rm -rf "$IMAGE"
mkdir -p "$IMAGE/casper" "$IMAGE/boot/grub"

cp "$CHROOT"/boot/vmlinuz-*  "$IMAGE/casper/vmlinuz"
cp "$CHROOT"/boot/initrd.img-* "$IMAGE/casper/initrd"

say "squashing the filesystem (this is the slow part)"
mksquashfs "$CHROOT" "$IMAGE/casper/filesystem.squashfs" \
    -noappend -comp xz -e boot
printf '%s' "$(du -sx --block-size=1 "$CHROOT" | cut -f1)" \
    > "$IMAGE/casper/filesystem.size"

cat > "$IMAGE/boot/grub/grub.cfg" <<'EOF'
set timeout=3
set default=0

menuentry "octagonOS (live)" {
    linux /casper/vmlinuz boot=casper quiet splash ---
    initrd /casper/initrd
}
menuentry "octagonOS (live, no splash)" {
    linux /casper/vmlinuz boot=casper ---
    initrd /casper/initrd
}
EOF
touch "$IMAGE/octagonos"

say "building the ISO"
mkdir -p "$(dirname "$OUT")"
grub-mkstandalone --format=x86_64-efi --output="$WORK/bootx64.efi" \
    --locales="" --fonts="" "boot/grub/grub.cfg=$IMAGE/boot/grub/grub.cfg"

# A FAT image holding the EFI binary: firmware will not read it from ISO9660.
(cd "$WORK" && dd if=/dev/zero of=efiboot.img bs=1M count=10 status=none \
    && mkfs.vfat efiboot.img >/dev/null \
    && mmd -i efiboot.img ::/EFI ::/EFI/BOOT \
    && mcopy -i efiboot.img "$WORK/bootx64.efi" ::/EFI/BOOT/BOOTX64.EFI)
cp "$WORK/efiboot.img" "$IMAGE/boot/grub/efiboot.img"

# The same binary again, as a real directory in the ISO9660 filesystem.
# Firmware boots from the FAT image above, but preparing a USB stick by
# copying the ISO's contents -- which is what most Windows tools do -- only
# carries files that exist as files. Without this the stick boots on BIOS and
# not on UEFI, and xorriso warns about exactly that.
install -d "$IMAGE/EFI/BOOT"
cp "$WORK/bootx64.efi" "$IMAGE/EFI/BOOT/BOOTX64.EFI"

grub-mkstandalone --format=i386-pc \
    --output="$WORK/core.img" --install-modules="linux normal iso9660 biosdisk memdisk search tar ls" \
    --modules="linux normal iso9660 biosdisk search" --locales="" --fonts="" \
    "boot/grub/grub.cfg=$IMAGE/boot/grub/grub.cfg"
cat /usr/lib/grub/i386-pc/cdboot.img "$WORK/core.img" > "$IMAGE/boot/grub/bios.img"

xorriso -as mkisofs -iso-level 3 -volid "OCTAGONOS" \
    -full-iso9660-filenames \
    -eltorito-boot boot/grub/bios.img -no-emul-boot -boot-load-size 4 \
    -boot-info-table --eltorito-catalog boot/grub/boot.cat \
    --grub2-boot-info --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
    -eltorito-alt-boot -e boot/grub/efiboot.img -no-emul-boot \
    -append_partition 2 0xef "$IMAGE/boot/grub/efiboot.img" \
    -output "$OUT" "$IMAGE"

say "done: $OUT ($(du -h "$OUT" | cut -f1))"
