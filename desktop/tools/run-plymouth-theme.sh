#!/bin/bash
#
# Run the installed Plymouth theme for real, drive it, and screenshot it.
#
#   desktop/tools/run-plymouth-theme.sh <shot-prefix> [step ...]
#
# Example -- the whole encrypted-disk path, end to end:
#
#   run-plymouth-theme.sh pw \
#       "plymouth ask-for-password --prompt='Unlock disk (sda3_crypt)' &" \
#       KEYS:hunter2 ENTER
#
# WHY THIS EXISTS
#
# The static verifier reads the script; this runs it. Plymouth themes fail
# silently -- a callback that never fires, a sprite that is discarded, a
# message that never clears all draw nothing and log nothing -- so the only
# way to know a theme works is to put it on a screen and look.
#
# It needs: plymouth, plymouth-x11 (for the x11 renderer), Xvfb, xdotool, and
# netpbm + x11-apps for the screenshot. On Debian/Ubuntu:
#
#   apt install plymouth plymouth-x11 plymouth-label xvfb xdotool netpbm x11-apps
#
# Four real bugs in this theme were found with it and by nothing else. Each is
# noted where the workaround for it lives.
#
# Screenshots land beside this script, one per step plus a final one.
#
# A step is a shell command, or "KEYS:<text>" to type <text>, or "ENTER".
# Every step is followed by a screenshot.
#
# The keystrokes go through XTEST, not through the tty. With the x11 renderer
# plymouth logs "Watching for keyboard input from renderer" and reads keys from
# its X window; writing to the pty it was given with --tty reaches nothing. The
# first attempt did exactly that, drew a prompt with no bullets, and looked like
# a theme bug.
set -u
SP="$(cd "$(dirname "$0")" && pwd)"
SHOT="$1"; shift

pkill -x Xvfb 2>/dev/null
pkill plymouthd 2>/dev/null
rm -rf /run/plymouth
sleep 1

Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 &
XVFB=$!
sleep 2
export DISPLAY=:99

# plymouthd aborts if --tty is not a terminal, so it gets a pty. The container
# boots with console=ttyS0, which makes plymouth force details mode and never
# load a theme at all, and its cmdline has no "splash"; --kernel-command-line
# overrides both. Both were silent: the first run drew a black screen and
# reported success.
python3 - <<'PY' &
import os, pty, subprocess, threading, time
m, s = pty.openpty()
p = subprocess.Popen(
    ["/usr/sbin/plymouthd", "--debug", "--no-daemon", "--mode=boot",
     "--debug-file=/tmp/plymouthd-debug.log",
     "--kernel-command-line=splash plymouth.ignore-serial-consoles",
     "--tty=" + os.ttyname(s)],
    stdin=s, stdout=open("/tmp/plymouthd.log", "wb"),
    stderr=subprocess.STDOUT)

# plymouthd redirects its debug output to the tty it was given. Nothing here
# reads the pty master, so its buffer fills and plymouthd BLOCKS on write --
# the animation stops mid-frame and every later screenshot is identical. It
# looks exactly like a script error in whatever callback ran last.
def drain():
    while True:
        try:
            if not os.read(m, 65536):
                return
        except OSError:
            return

threading.Thread(target=drain, daemon=True).start()
time.sleep(90)
p.terminate()
PY
PLYPY=$!
sleep 3

# plymouthd makes three X windows -- a 1x1, a 10x10 and the real full-screen
# one, all named "plymouthd" -- and there is no window manager to set focus, so
# XTEST would otherwise deliver keys to whichever happens to be under the
# pointer. Pick the full-screen one by area and focus it explicitly.
focus_plymouth() {
    local best="" area=0
    for w in $(xdotool search --name '^plymouthd$' 2>/dev/null); do
        eval "$(xdotool getwindowgeometry --shell "$w" 2>/dev/null)"
        if [ $((WIDTH * HEIGHT)) -gt $area ]; then area=$((WIDTH * HEIGHT)); best=$w; fi
    done
    [ -n "$best" ] || { echo "[!!] no plymouthd window"; return 1; }
    xdotool windowfocus --sync "$best" 2>/dev/null
    xdotool mousemove --window "$best" 40 40 2>/dev/null
}

plymouth --ping >/dev/null && echo "[ok] daemon answering" || { echo "[!!] no daemon"; exit 1; }
plymouth show-splash
sleep 2

n=0
for step in "$@"; do
    n=$((n + 1))
    case "$step" in
        KEYS:*) focus_plymouth; xdotool type --delay 60 --clearmodifiers "${step#KEYS:}" ;;
        ENTER)  focus_plymouth; xdotool key --clearmodifiers Return ;;
        *)      echo "[*] $step"; eval "$step" ;;
    esac
    sleep 2
    xwd -root -display :99 -silent > /tmp/shot.xwd 2>/dev/null
    xwdtopnm < /tmp/shot.xwd 2>/dev/null | pnmtopng > "$SP/$SHOT-$n.png" 2>/dev/null
done

xwd -root -display :99 -silent > /tmp/shot.xwd 2>/dev/null
xwdtopnm < /tmp/shot.xwd 2>/dev/null | pnmtopng > "$SP/$SHOT-final.png" 2>/dev/null
ls -la "$SP/$SHOT"-*.png

plymouth quit 2>/dev/null
sleep 1
kill $PLYPY 2>/dev/null; pkill plymouthd 2>/dev/null; kill $XVFB 2>/dev/null
