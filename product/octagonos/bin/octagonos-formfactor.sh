#!/system/bin/sh
#
# octagonOS form-factor setup. Runs once, on first boot.
#
# octagonOS ships one GSI for two quite different phones:
#
#   keyboard  a physical-keyboard slider or candybar (Titan-class). Often a
#             near-square display. The virtual keyboard is suppressed by the
#             framework whenever the hardware one is open, so the IME that
#             matters is the physical-keyboard one.
#   slab      an ordinary touchscreen phone. Tall display, virtual keyboard.
#
# A GSI cannot be built per device, and the difference is not knowable at build
# time, so it is resolved here at first boot instead: detect the keyboard,
# record it as a property, and enable the matching overlay set.
#
# Everything this script does is idempotent and guarded by a stamp file, so a
# re-run after an OTA is harmless.

STAMP=/data/misc/octagonos/.formfactor-applied
LOG_TAG=octagonOS-formfactor

log() { log -t "$LOG_TAG" "$@" 2>/dev/null || echo "$LOG_TAG: $*"; }

[ -f "$STAMP" ] && exit 0

# --- detect a physical keyboard ---------------------------------------------
#
# Read the input device table rather than asking the framework: this runs early,
# and /proc/bus/input/devices is populated by the kernel before any of Android
# is up. Each device advertises a KEY capability bitmask, printed as
# whitespace-separated 64-bit hex groups, most significant group first. Every
# key we care about is below bit 64, so only the LAST group matters:
#
#   KEY_Q 16 .. KEY_P 25      the top letter row
#   KEY_A 30 .. KEY_L 38      the home row
#   KEY_Z 44 .. KEY_M 50      the bottom row
#
# Requiring all three rows is what separates a real alphabetic keyboard from a
# volume rocker or a headset button, both of which also advertise EV_KEY and
# would otherwise be mistaken for one.

has_alpha_keyboard() {
    [ -r /proc/bus/input/devices ] || return 1

    # Each "B: KEY=..." line belongs to the device block above it; we only need
    # to know whether ANY device has a full alphabet.
    grep '^B: KEY=' /proc/bus/input/devices 2>/dev/null | while read -r line; do
        # Strip the prefix, then take the last whitespace-separated group.
        bits=${line#B: KEY=}
        last=${bits##* }
        [ -n "$last" ] || continue

        # Guard the arithmetic: a malformed table would otherwise abort the
        # shell rather than skip the line.
        case "$last" in
            "" | *[!0-9a-fA-F]*) continue ;;
        esac

        # 64-bit shell arithmetic. A group with the top bit set wraps negative,
        # but every bit tested here is below 51 and the masks below discard the
        # sign extension, so the comparisons stay correct either way.
        val=$((0x$last))

        rows=0
        # KEY_Q..KEY_P  = bits 16-25
        [ $(( (val >> 16) & 0x3ff )) -eq 1023 ] && rows=$((rows + 1))
        # KEY_A..KEY_L  = bits 30-38
        [ $(( (val >> 30) & 0x1ff )) -eq 511 ]  && rows=$((rows + 1))
        # KEY_Z..KEY_M  = bits 44-50
        [ $(( (val >> 44) & 0x7f )) -eq 127 ]   && rows=$((rows + 1))

        if [ "$rows" -eq 3 ]; then
            echo found
            break
        fi
    done | grep -q found
}

if has_alpha_keyboard; then
    FORM=keyboard
else
    FORM=slab
fi
log "detected form factor: $FORM"
setprop persist.octagonos.formfactor "$FORM"

# --- overlays ---------------------------------------------------------------
#
# android:isStatic is deprecated, so an overlay dropped into /product/overlay
# is not necessarily enabled just by being there. Enable explicitly and do not
# treat a failure as fatal: a static overlay that is already enabled reports an
# error, and that is the good case.

enable_overlay() {
    cmd overlay enable "$1" >/dev/null 2>&1 \
        && log "enabled $1" \
        || log "could not enable $1 (may already be static/enabled)"
}

# The glass layer is the same on both form factors: a shade is a shade.
enable_overlay dev.octagonos.facetui.systemui
enable_overlay dev.octagonos.facetui.framework
enable_overlay dev.octagonos.facetui.launcher

# The keyboard overlay only makes sense where a virtual keyboard is actually
# used. On a physical-keyboard phone the IME window is suppressed whenever the
# hardware keyboard is open, so blurring it would cost fill rate for a surface
# that is usually not on screen. It is still enabled there, because the virtual
# keyboard does appear when the slider is closed -- but it is the one piece
# that is genuinely form-factor dependent, so it is called out rather than
# lumped in above.
enable_overlay dev.octagonos.facetui.ime

# --- default input method ---------------------------------------------------
#
# Only set a default if one was built in. The IME package is injected by
# tools/inject-ime.sh, which writes the component here; if no keyboard was
# injected this block is absent and the framework's own default stands.

PHYSICAL_IME=""   # replaced by inject-ime.sh when --ime-id is given

if [ "$FORM" = "keyboard" ] && [ -n "$PHYSICAL_IME" ]; then
    # Wait for the package manager to have scanned the system app. Without this
    # the enable call lands before the package exists and silently does nothing,
    # which is the failure mode that makes a keyboard "install but never
    # activate".
    i=0
    while [ $i -lt 60 ]; do
        if pm list packages 2>/dev/null | grep -q "${PHYSICAL_IME%%/*}"; then
            break
        fi
        sleep 2
        i=$((i + 1))
    done

    ime enable "$PHYSICAL_IME"  >/dev/null 2>&1 && log "enabled IME $PHYSICAL_IME"
    ime set    "$PHYSICAL_IME"  >/dev/null 2>&1 && log "set default IME $PHYSICAL_IME"
fi

mkdir -p "$(dirname "$STAMP")" 2>/dev/null
touch "$STAMP"
log "done"
exit 0
