#!/bin/bash
#
# Run octagonos-install without a human, for the build's acceptance test.
#
# Enabled by `octagonos.autoinstall=/dev/vda` on the kernel command line and
# inert otherwise, exactly like the self-test: it is a feature of the image
# rather than something a harness injects, so what the test exercises is the
# installer people actually get.
#
# It reports over the serial console and then powers the machine off, which
# is the signal to the host that phase one is finished and the disk can be
# booted on its own.

set -u
OUT=/dev/ttyS0
say() { echo "OCTAGONOS-INSTALL: $*" > "$OUT"; }

TARGET_DISK=""
for arg in $(cat /proc/cmdline 2>/dev/null); do
    case "$arg" in
        octagonos.autoinstall=*) TARGET_DISK="${arg#*=}" ;;
    esac
done
[ -n "$TARGET_DISK" ] || exit 0

say "installing to $TARGET_DISK"

if /usr/bin/octagonos-install --unattended --disk "$TARGET_DISK" \
        --hostname octagonos --user octagon --password octagon > "$OUT" 2>&1; then
    say "OK   the installer finished"
else
    say "FAIL the installer exited non-zero"
fi

say "END"
sync
systemctl poweroff -i
