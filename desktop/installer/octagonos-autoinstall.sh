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

# TRACE TO A FILE, THEN REPLAY IT.
#
# Writing the installer's output straight at the serial console lost it: the
# first three failures showed "partitioning /dev/vda" and then nothing --
# no error, no line number, no exit status -- on a machine that powers itself
# off before anybody can look. Whether that was interleaving with systemd's
# own console writes or output still buffered when the process died, the fix
# is the same: capture to a file that survives, then replay it deliberately.
#
# `bash -x` because a shell script that dies under `set -e` says nothing about
# which command did it, and this one is running where nobody can watch.
LOG=/run/octagonos-install.trace
rc=0
bash -x /usr/bin/octagonos-install --unattended --disk "$TARGET_DISK" \
    --hostname octagonos --user octagon --password octagon > "$LOG" 2>&1 || rc=$?

if [ "$rc" -eq 0 ]; then
    say "OK   the installer finished"
    tail -5 "$LOG" | while IFS= read -r l; do say "log| $l"; done
else
    say "FAIL the installer exited $rc"
    say "---- the last 60 traced commands ----"
    tail -60 "$LOG" | while IFS= read -r l; do say "log| $l"; done
fi

say "END"
sync
systemctl poweroff -i
