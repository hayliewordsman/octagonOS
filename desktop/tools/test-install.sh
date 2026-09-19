#!/bin/bash
#
# Install octagonOS to a virtual disk, then boot that disk and check it.
#
#     desktop/tools/test-install.sh <image.iso> [--uefi]
#
# WHY TWO PHASES
#
# verify-iso.sh proves the image contains the right things. boot-iso-check.sh
# proves the LIVE session runs FacetUI. Neither says anything about an
# installed system, which is a different artefact: a different filesystem, a
# different bootloader, a different user, and a pile of live-image
# configuration that has to be undone correctly or the machine boots into
# somebody else's autologin.
#
#   phase 1  boot the ISO with octagonos.autoinstall=/dev/vda, which runs
#            octagonos-install unattended and powers off
#   phase 2  boot the DISK, and ask KWin whether FacetUI is running on it
#
# WHY THE DISK IS INSTRUMENTED BETWEEN THEM
#
# The installer removes the self-test, the OpenGL override and the unattended
# installer from anything it installs -- they are test scaffolding and have no
# business on somebody's computer. That is correct, and it means the installed
# system cannot report on itself.
#
# Rather than weaken the installer so the test is easier, the harness mounts
# the finished disk and adds the self-test back from outside. What gets
# installed is exactly what a user gets; the instrumentation is visibly the
# test's, not the product's.
#
# Needs qemu-system-x86, xorriso, socat, and loop devices.

set -u
set -o pipefail

ISO="${1:?usage: test-install.sh <image.iso> [--uefi]}"
shift || true
FIRMWARE=bios
[ "${1:-}" = "--uefi" ] && FIRMWARE=uefi

INSTALL_TIMEOUT="${INSTALL_TIMEOUT:-5400}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-5400}"
DISK_SIZE="${DISK_SIZE:-20G}"

[ -f "$ISO" ] || { echo "[FAIL] no such image: $ISO"; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "[FAIL] this needs root: it uses loop devices"; exit 2; }

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
DISK="$WORK/disk.raw"
LOOP=""
MNT="$WORK/mnt"

cleanup() {
    [ -n "${QPID:-}" ] && kill "$QPID" 2>/dev/null
    mountpoint -q "$MNT/boot/efi" && umount "$MNT/boot/efi" 2>/dev/null
    mountpoint -q "$MNT" && umount "$MNT" 2>/dev/null
    [ -n "$LOOP" ] && losetup -d "$LOOP" 2>/dev/null
    rm -rf "$WORK"
}
trap cleanup EXIT

echo "[*] a blank $DISK_SIZE disk, and firmware: $FIRMWARE"
truncate -s "$DISK_SIZE" "$DISK"

echo "[*] extracting the kernel and initrd"
xorriso -osirrox on -indev "$ISO" \
    -extract /casper/vmlinuz "$WORK/vmlinuz" \
    -extract /casper/initrd  "$WORK/initrd" >/dev/null 2>&1 \
    || { echo "[FAIL] could not extract the kernel and initrd"; exit 1; }

ACCEL=tcg
[ -w /dev/kvm ] && ACCEL=kvm

firmware_args() {
    if [ "$FIRMWARE" = uefi ]; then
        cp /usr/share/OVMF/OVMF_VARS_4M.fd "$WORK/vars.fd"
        printf '%s\n' \
            "-drive" "if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd" \
            "-drive" "if=pflash,format=raw,unit=1,file=$WORK/vars.fd"
    fi
}
mapfile -t FW < <(firmware_args)

# --- phase 1: install --------------------------------------------------------

SERIAL1="$WORK/install.log"
echo "[*] phase 1: installing to the virtual disk (accel: $ACCEL)"

qemu-system-x86_64 \
    -machine q35 -accel "$ACCEL" -m 4096 -smp 2 \
    "${FW[@]}" \
    -device virtio-vga -display none \
    -drive file="$ISO",media=cdrom,readonly=on \
    -drive file="$DISK",format=raw,if=virtio,cache=unsafe \
    -kernel "$WORK/vmlinuz" -initrd "$WORK/initrd" \
    -append "boot=casper quiet octagonos.autoinstall=/dev/vda \
             systemd.unit=multi-user.target console=ttyS0,115200" \
    -serial "file:$SERIAL1" -rtc base=utc &
QPID=$!

deadline=$(( $(date +%s) + INSTALL_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    kill -0 "$QPID" 2>/dev/null || break          # it powers itself off when done
    grep -q "OCTAGONOS-INSTALL: END" "$SERIAL1" 2>/dev/null && break
    sleep 5
done
sleep 10
kill "$QPID" 2>/dev/null; wait "$QPID" 2>/dev/null; QPID=""

# SAVE THE LOG BEFORE JUDGING IT. The first run of this script failed in
# phase 1 and deleted its own evidence: the serial log lived in $WORK, the
# exit path ran before the copy at the end, and the trap removed it. The
# installer's own output was in there, and the only thing printed was that it
# had exited non-zero.
OUTDIR="$(dirname "$ISO")"
cp "$SERIAL1" "$OUTDIR/install-phase1.log" 2>/dev/null

echo
if ! grep -q "OCTAGONOS-INSTALL:" "$SERIAL1" 2>/dev/null; then
    echo "[FAIL] the installer never reported. Last serial output:"
    tail -30 "$SERIAL1" 2>/dev/null | sed 's/^/       /'
    echo "       full log: $OUTDIR/install-phase1.log"
    exit 1
fi
grep "OCTAGONOS-INSTALL:" "$SERIAL1" | sed 's/OCTAGONOS-INSTALL: /  /'

if grep -q "OCTAGONOS-INSTALL: FAIL" "$SERIAL1"; then
    echo
    echo "[FAIL] the installer reported failure. What it printed before dying:"
    # Its own output is on the same console, untagged, so show the tail rather
    # than only the lines that happen to carry the marker.
    grep -v '^\[  *OK  *\]\|^\[FAILED\]\|Starting \|Started \|Stopping \|Stopped ' \
        "$SERIAL1" 2>/dev/null | tail -30 | sed 's/^/       /'
    echo "       full log: $OUTDIR/install-phase1.log"
    exit 1
fi

# --- between: is there actually a system on this disk? -----------------------

echo
echo "[*] examining the installed disk"
LOOP="$(losetup --find --show -P "$DISK")"

# Wait for the partition nodes, rather than assuming they are there. losetup
# -P asks the kernel to scan, udev creates the nodes, and neither has
# finished when losetup returns -- a race that reads as "the installer made
# no partitions" when the installer made them correctly.
ROOTPART="${LOOP}p2"
for _ in $(seq 1 30); do
    [ -b "$ROOTPART" ] && break
    partx -a "$LOOP" >/dev/null 2>&1 || true
    udevadm settle >/dev/null 2>&1 || true
    sleep 1
done
if [ ! -b "$ROOTPART" ]; then
    echo "[FAIL] no second partition on the disk. What is actually on it:"
    sgdisk -p "$DISK" 2>&1 | sed 's/^/       /'
    ls -la "${LOOP}"* 2>&1 | sed 's/^/       /'
    exit 1
fi

mkdir -p "$MNT"
mount "$ROOTPART" "$MNT" || { echo "[FAIL] the root filesystem will not mount"; exit 1; }

fail=0
ok()  { echo "  ok    $*"; }
bad() { echo "  FAIL  $*"; fail=1; }

[ -f "$MNT/etc/fstab" ] && grep -q ' / ' "$MNT/etc/fstab" && ok "fstab names a root filesystem" \
    || bad "no usable /etc/fstab"
[ -d "$MNT/boot/grub" ] && ok "GRUB is installed" || bad "no /boot/grub"
[ -f "$MNT/boot/grub/grub.cfg" ] && ok "grub.cfg was generated" || bad "no grub.cfg"
ls "$MNT"/boot/vmlinuz-* >/dev/null 2>&1 && ok "a kernel is present" || bad "no kernel in /boot"

# The live-image configuration must be GONE. This is the part a hand-written
# install forgets, and forgetting it ships a machine that logs itself in as a
# published username with a published password.
[ -f "$MNT/etc/sddm.conf.d/octagonos.conf" ] && bad "the live autologin survived the install" \
    || ok "the live autologin is gone"
[ -f "$MNT/etc/casper.conf" ] && bad "/etc/casper.conf survived" || ok "casper.conf is gone"
grep -q '^KWIN_COMPOSE=' "$MNT/etc/environment" 2>/dev/null \
    && bad "the forced-OpenGL override survived" || ok "no forced-OpenGL override"
for u in octagonos-selftest octagonos-forcegl octagonos-autoinstall; do
    [ -f "$MNT/etc/systemd/system/$u.service" ] && bad "$u.service survived the install"
done
ok "the test scaffolding was removed by the installer"

# FacetUI must still be the default on the installed system.
if [ -x "$HERE/check-facetui-defaults.sh" ]; then
    echo "[*] and is FacetUI still the default on it?"
    "$HERE/check-facetui-defaults.sh" --root "$MNT" --installed 2>&1 \
        | sed 's/^/    /' || fail=1
fi

[ "$fail" -eq 0 ] || { echo; echo "FAILED: the installed disk is not right"; exit 1; }

# --- instrument it, visibly, for phase 2 -------------------------------------
#
# Putting back exactly what the installer removed, because the installed
# system is correct precisely in not having it.
echo
echo "[*] adding the self-test back, from outside, so the disk can report"
install -D -m 755 "$HERE/../iso/selftest/octagonos-selftest.sh" \
    "$MNT/usr/lib/octagonos/octagonos-selftest.sh"
install -D -m 644 "$HERE/../iso/selftest/octagonos-selftest.service" \
    "$MNT/etc/systemd/system/octagonos-selftest.service"
install -D -m 755 "$HERE/../iso/selftest/octagonos-forcegl.sh" \
    "$MNT/usr/lib/octagonos/octagonos-forcegl.sh"
install -D -m 644 "$HERE/../iso/selftest/octagonos-forcegl.service" \
    "$MNT/etc/systemd/system/octagonos-forcegl.service"
ln -sf /etc/systemd/system/octagonos-selftest.service \
    "$MNT/etc/systemd/system/graphical.target.wants/octagonos-selftest.service"
ln -sf /etc/systemd/system/octagonos-forcegl.service \
    "$MNT/etc/systemd/system/graphical.target.wants/octagonos-forcegl.service"

# The installed system autologins nobody, by design. Phase 2 needs a session
# to measure, so give it one -- again from outside, and only here.
install -d "$MNT/etc/sddm.conf.d"
cat > "$MNT/etc/sddm.conf.d/zz-test-autologin.conf" <<EOF
[Autologin]
User=octagon
Session=plasma

[General]
DisplayServer=wayland

[Wayland]
CompositorCommand=kwin_wayland --no-lockscreen
EOF

# GRUB decides the kernel command line now, not QEMU: phase 2 boots the disk's
# own bootloader. So the flags go into the generated config.
sed -i 's|^\(\s*linux\s\+/boot/vmlinuz[^ ]*.*\)$|\1 octagonos.selftest octagonos.forcegl console=ttyS0,115200|' \
    "$MNT/boot/grub/grub.cfg"
grep -c 'octagonos.selftest' "$MNT/boot/grub/grub.cfg" | sed 's/^/  menu entries instrumented: /'

sync
umount "$MNT"
losetup -d "$LOOP"; LOOP=""

# --- phase 2: boot the installed disk ----------------------------------------

SERIAL2="$WORK/boot.log"
echo
echo "[*] phase 2: booting the installed disk, with no ISO attached"

qemu-system-x86_64 \
    -machine q35 -accel "$ACCEL" -m 4096 -smp 2 \
    "${FW[@]}" \
    -device virtio-vga -display none \
    -drive file="$DISK",format=raw,if=virtio,cache=unsafe \
    -serial "file:$SERIAL2" -rtc base=utc &
QPID=$!

deadline=$(( $(date +%s) + BOOT_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    kill -0 "$QPID" 2>/dev/null || { echo "[FAIL] the machine died before reporting"; break; }
    grep -q "OCTAGONOS-SELFTEST: END" "$SERIAL2" 2>/dev/null && break
    sleep 5
done
kill "$QPID" 2>/dev/null; wait "$QPID" 2>/dev/null; QPID=""

cp "$SERIAL2" "$OUTDIR/install-phase2.log" 2>/dev/null

echo
grep "OCTAGONOS-SELFTEST:" "$SERIAL2" 2>/dev/null | sed 's/OCTAGONOS-SELFTEST: /  /'
echo
"$HERE/judge-selftest.sh" "$SERIAL2"
rc=$?
if [ "$rc" -eq 0 ]; then
    echo
    echo "That was an INSTALLED system: its own bootloader, its own filesystem,"
    echo "no ISO attached."
fi
exit "$rc"
