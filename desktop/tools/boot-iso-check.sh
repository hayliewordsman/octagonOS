#!/bin/bash
#
# Boot an octagonOS image and ask it whether FacetUI is actually drawing.
#
#     desktop/tools/boot-iso-check.sh <image.iso> [out-dir]
#
# WHY THIS IS THE ACCEPTANCE TEST
#
# Everything else in this repository proves FacetUI is installed, correct and
# selected. None of it proves the compositor effect is VISIBLE, because that
# needs a GPU: without a DRM render node KWin falls back to its QPainter scene,
# where every OpenGL effect -- KWin's own blur included -- reports itself
# unsupported and is never loaded. That is the exact state the development
# container is in, and it is why the effect has been "loads and is accepted"
# rather than "works" until now.
#
# A QEMU guest with virtio-gpu HAS a render node. So this boots the image, asks
# the running session over its own D-Bus, and takes a picture of the screen
# from outside the guest.
#
# HOW IT TALKS TO THE GUEST
#
# The kernel and initrd are pulled out of the ISO and booted directly, with the
# image attached as the live medium. That is only so the kernel command line
# can carry `octagonos.selftest` -- the image's GRUB menu has no entry for it,
# and it should not: the self-test is a thing you ask for, not a thing that
# happens. The guest reports over the serial console; the screenshot is taken
# through QEMU's monitor, so it needs no cooperation from the guest at all.
#
# Needs qemu-system-x86, ovmf and xorriso. KVM is used when /dev/kvm exists and
# TCG when it does not -- slow, but the effect does not care how long a frame
# took.

set -u
set -o pipefail

ISO="${1:?usage: boot-iso-check.sh <image.iso> [out-dir]}"
OUTDIR="${2:-$(dirname "$ISO")}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-1800}"

[ -f "$ISO" ] || { echo "[FAIL] no such image: $ISO"; exit 2; }
command -v qemu-system-x86_64 >/dev/null || { echo "[FAIL] qemu-system-x86 is not installed"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; [ -n "${QPID:-}" ] && kill "$QPID" 2>/dev/null' EXIT

echo "[*] extracting the kernel and initrd from the image"
xorriso -osirrox on -indev "$ISO" \
    -extract /casper/vmlinuz "$WORK/vmlinuz" \
    -extract /casper/initrd  "$WORK/initrd" >/dev/null 2>&1 \
    || { echo "[FAIL] could not extract /casper/vmlinuz and /casper/initrd"; exit 1; }

SERIAL="$WORK/serial.log"
MONITOR="$WORK/monitor.sock"

ACCEL=tcg
[ -w /dev/kvm ] && ACCEL=kvm
echo "[*] booting under $ACCEL (timeout ${BOOT_TIMEOUT}s)"
[ "$ACCEL" = tcg ] && echo "    no /dev/kvm, so this is software emulation and will be slow"

# virtio-vga is the point of the exercise: it gives the guest a DRM render
# node, which is what KWin needs to choose its OpenGL scene at all.
qemu-system-x86_64 \
    -machine q35 -accel "$ACCEL" -m 4096 -smp 2 \
    -device virtio-vga -display none \
    -drive file="$ISO",media=cdrom,readonly=on \
    -kernel "$WORK/vmlinuz" -initrd "$WORK/initrd" \
    -append "boot=casper quiet splash octagonos.selftest console=ttyS0,115200" \
    -serial "file:$SERIAL" \
    -monitor "unix:$MONITOR,server,nowait" \
    -rtc base=utc &
QPID=$!

echo "[*] waiting for the session to report"
deadline=$(( $(date +%s) + BOOT_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    kill -0 "$QPID" 2>/dev/null || { echo "[FAIL] QEMU exited before the guest reported"; break; }
    grep -q "OCTAGONOS-SELFTEST: END" "$SERIAL" 2>/dev/null && break
    sleep 5
done

# A picture of the screen, taken from outside the guest, so it is evidence
# even when the guest is too broken to answer.
SHOT="$OUTDIR/$(basename "${ISO%.iso}")-screen.ppm"
if [ -S "$MONITOR" ]; then
    printf 'screendump %s\nquit\n' "$SHOT" \
        | timeout 60 socat - "UNIX-CONNECT:$MONITOR" >/dev/null 2>&1 || true
fi
kill "$QPID" 2>/dev/null; wait "$QPID" 2>/dev/null

if [ -f "$SHOT" ] && command -v pnmtopng >/dev/null; then
    pnmtopng < "$SHOT" > "${SHOT%.ppm}.png" 2>/dev/null && rm -f "$SHOT" \
        && SHOT="${SHOT%.ppm}.png"
fi

echo
if ! grep -q "OCTAGONOS-SELFTEST:" "$SERIAL" 2>/dev/null; then
    echo "[FAIL] the guest never reported. Either it did not reach a desktop"
    echo "       session within ${BOOT_TIMEOUT}s, or the self-test is not in"
    echo "       this image. Last serial output:"
    tail -20 "$SERIAL" 2>/dev/null | sed 's/^/       /'
    cp "$SERIAL" "$OUTDIR/$(basename "${ISO%.iso}")-serial.log" 2>/dev/null
    exit 1
fi

grep "OCTAGONOS-SELFTEST:" "$SERIAL" | sed 's/OCTAGONOS-SELFTEST: /  /'
cp "$SERIAL" "$OUTDIR/$(basename "${ISO%.iso}")-serial.log"
[ -f "$SHOT" ] && echo && echo "[*] screenshot: $SHOT"

echo
if grep -q "OCTAGONOS-SELFTEST: FAIL" "$SERIAL"; then
    echo "FAILED: the image booted, and FacetUI is not running on it."
    exit 1
fi
echo "FacetUI is running on a booted machine, with OpenGL compositing and the"
echo "glass effect loaded. That is the one thing no offline check could settle."
