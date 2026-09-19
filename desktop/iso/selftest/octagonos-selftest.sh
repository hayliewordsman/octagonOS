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
# The uid is looked up from the account autologin actually names, rather
# than assumed to be 1000. On this image they agree, but a hardcoded 1000 is
# a silent wrong answer the day they stop agreeing -- and casper creating a
# second uid-1000 account is exactly how that would happen.
AUTOLOGIN_USER="$(sed -n 's/^User=//p' /etc/sddm.conf.d/*.conf /etc/sddm.conf \
                  2>/dev/null | tail -1)"
UID_N="$(id -u "${AUTOLOGIN_USER:-octagon}" 2>/dev/null || echo 1000)"
BUS="/run/user/$UID_N/bus"

# How long to wait. 180s was the first guess and it was wrong: under QEMU's
# software emulation, with no KVM, SDDM and Plasma take many minutes to reach
# a session, and the self-test was reporting "the desktop did not start" about
# a desktop that was still starting. Overridable from the kernel command line
# so a slow machine can be given longer without rebuilding the image.
WAIT=1800
for arg in $(cat /proc/cmdline 2>/dev/null); do
    case "$arg" in
        octagonos.selftest.wait=*) WAIT="${arg#*=}" ;;
    esac
done

waited=0
while [ "$waited" -lt "$WAIT" ]; do
    [ -S "$BUS" ] && break
    sleep 5
    waited=$((waited + 5))
done

if [ ! -S "$BUS" ]; then
    say "FAIL no session bus after ${WAIT}s; the desktop did not start"
    say "     (waited on $BUS, for user ${AUTOLOGIN_USER:-octagon} uid $UID_N)"

    # SAY WHY, not just that. The first time this fired it reported the
    # symptom and nothing else, and finding the cause -- an autologin session
    # name that matched no session file, so SDDM fell back to its greeter --
    # took another full boot and a screenshot. Everything below was what had
    # to be gathered by hand afterwards, so the next failure carries it.
    say "---- why ----"
    say "display-manager: $(systemctl is-active display-manager.service 2>/dev/null || echo unknown)"
    say "sddm:            $(systemctl is-active sddm.service 2>/dev/null || echo unknown)"
    say "graphical.target:$(systemctl is-active graphical.target 2>/dev/null || echo unknown)"

    au="$(sed -n 's/^User=//p'    /etc/sddm.conf.d/*.conf 2>/dev/null | head -1)"
    as="$(sed -n 's/^Session=//p' /etc/sddm.conf.d/*.conf 2>/dev/null | head -1)"
    say "autologin:       user='${au:-unset}' session='${as:-unset}'"
    if [ -n "$as" ] && [ ! -f "/usr/share/wayland-sessions/${as%.desktop}.desktop" ] \
                    && [ ! -f "/usr/share/xsessions/${as%.desktop}.desktop" ]; then
        say "                 ^ that session file DOES NOT EXIST. SDDM will"
        say "                   show its greeter instead of logging anyone in."
        say "                 available: $(ls /usr/share/wayland-sessions /usr/share/xsessions 2>/dev/null | tr '\n' ' ')"
    fi
    say "sessions:        $(loginctl list-sessions --no-legend 2>/dev/null | wc -l) open"
    say "run/user:        $(ls /run/user 2>/dev/null | tr '\n' ' ')"

    journalctl -u sddm.service -n 40 --no-pager 2>/dev/null \
        | while IFS= read -r l; do say "sddm| $l"; done

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

# 1b. Whether OpenGL was forced. Without this line a reader cannot tell a
#     machine whose driver chose OpenGL from one that was overridden into it,
#     and those support very different claims.
if grep -qw octagonos.forcegl /proc/cmdline 2>/dev/null; then
    say "INFO OpenGL compositing was FORCED (KWIN_COMPOSE=O2ES): this machine"
    say "INFO has no GPU, so frames are drawn by the CPU. The effect running"
    say "INFO here says nothing about how it performs on real hardware."
else
    say "INFO OpenGL was not forced; KWin chose its own scene"
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
