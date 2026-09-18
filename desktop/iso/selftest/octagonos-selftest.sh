#!/bin/bash
#
# Report whether FacetUI is actually running, over the serial console.
#
# Enabled by `octagonos.selftest` on the kernel command line, and inert
# otherwise. It is a feature of the image rather than something a test harness
# injects: a user with a machine that looks wrong can boot with the same flag
# and get the same answers, which is the whole reason it is shipped instead of
# stitched in from outside.
#
# WHY THIS EXISTS AT ALL
#
# Every other check in this project proves FacetUI is installed, correct and
# selected. None of them can prove it is VISIBLE, because that needs a GPU:
# without a DRM render node KWin falls back to its QPainter scene, where
# OpenGL effects -- KWin's own blur included -- report themselves unsupported
# and are never loaded. This runs in a booted session, on real graphics, and
# is the first thing that can answer it.

set -u
OUT=/dev/ttyS0
say() { echo "OCTAGONOS-SELFTEST: $*" > "$OUT"; }

exec 2>/dev/null

# The session bus belongs to the user Plasma is running as, and Plasma takes a
# while to come up on a live image. Wait, rather than racing it and reporting
# a failure that is really impatience.
UID_N=1000
BUS="/run/user/$UID_N/bus"
for _ in $(seq 1 180); do
    [ -S "$BUS" ] && break
    sleep 1
done
if [ ! -S "$BUS" ]; then
    say "FAIL no session bus after 180s; the desktop did not start"
    say "END"
    exit 1
fi

run_as() {
    setpriv --reuid="$UID_N" --regid="$UID_N" --clear-groups \
        env DBUS_SESSION_BUS_ADDRESS="unix:path=$BUS" \
            XDG_RUNTIME_DIR="/run/user/$UID_N" "$@"
}

# Wait for KWin itself, not just the bus.
for _ in $(seq 1 120); do
    run_as busctl --user status org.kde.KWin >/dev/null 2>&1 && break
    sleep 1
done

# 1. A render node. Without one nothing below can be true.
if ls /dev/dri/renderD* >/dev/null 2>&1; then
    say "OK   render node: $(ls /dev/dri/renderD* | tr '\n' ' ')"
else
    say "FAIL no /dev/dri render node; KWin cannot use OpenGL"
fi

# 2. What KWin is actually compositing with.
TYPE="$(run_as busctl --user get-property org.kde.KWin /Compositor \
        org.kde.kwin.Compositing compositingType 2>/dev/null \
        | sed 's/^s //; s/"//g')"
case "$TYPE" in
    *gl*|*GL*|*OpenGL*) say "OK   compositing: $TYPE" ;;
    "")                 say "FAIL KWin did not answer; it may not be running" ;;
    *)                  say "FAIL compositing is '$TYPE', not OpenGL -- every"
                        say "FAIL OpenGL effect is unsupported in this state" ;;
esac

# 3. The effect itself. This is the line the whole image exists to print.
LOADED="$(run_as busctl --user call org.kde.KWin /Effects org.kde.kwin.Effects \
          isEffectLoaded s facetui-glass 2>/dev/null | awk '{print $2}')"
case "$LOADED" in
    true)  say "OK   facetui-glass is loaded and running" ;;
    false) say "FAIL facetui-glass is NOT loaded" ;;
    *)     say "FAIL could not ask KWin whether facetui-glass is loaded" ;;
esac

# 4. KWin's own blur, as the control. If this is out too, the machine has no
#    OpenGL and the FacetUI result above says nothing about FacetUI.
BLUR="$(run_as busctl --user call org.kde.KWin /Effects org.kde.kwin.Effects \
        isEffectLoaded s blur 2>/dev/null | awk '{print $2}')"
say "INFO kwin blur loaded: ${BLUR:-unknown}"

# 5. And that the theme the session is using is ours.
for spec in "kdeglobals:Icons:Theme" "plasmarc:Theme:name" "kdeglobals:General:ColorScheme"; do
    f="${spec%%:*}"; rest="${spec#*:}"; g="${rest%%:*}"; k="${rest##*:}"
    v="$(run_as kreadconfig6 --file "$f" --group "$g" --key "$k" 2>/dev/null)"
    if [ "$v" = "FacetUI" ]; then
        say "OK   $f [$g] $k = $v"
    else
        say "FAIL $f [$g] $k = '${v:-unset}', wanted FacetUI"
    fi
done

say "END"
