#!/system/bin/sh
#
# Report what octagonOS sees on this device.
#
#     adb push mobile/tools/octagonos-formfactor.sh /data/local/tmp/
#     adb shell sh /data/local/tmp/octagonos-formfactor.sh
#
# A DIAGNOSTIC, NOT A BOOT SERVICE, AND THAT IS THE POINT
#
# This began as a first-boot init service. It detected the form factor, set a
# property, enabled the FacetUI overlays with `cmd overlay enable`, and set the
# default IME. Each of those needed privilege, so it needed an SELinux domain
# of its own - and a Tier 2 image cannot grant one, because policy is compiled
# into the image and cannot be injected into a prebuilt one.
#
# Removing the need turned out to be easier than meeting it, because on a
# closer look the service was doing less than it appeared:
#
#   The overlays are now enabled declaratively by
#   product/octagonos/overlay/config/config.xml, which OverlayConfigParser
#   reads at boot. No command, no service, no policy. That also settles whether
#   they come up enabled at all, which `android:isStatic` being deprecated had
#   left in doubt.
#
#   The overlays were never form-factor dependent. All of them were enabled
#   unconditionally; the branch only ever chose the IME.
#
#   The default IME belongs to whatever injects the IME. titan2e-eos's
#   inject-ime.sh already writes its own first-boot hook for exactly this, and
#   two of them would have raced.
#
#   Nothing read the property. It had no consumer anywhere in the tree.
#
# So the service was deleted. What is worth keeping is the detection itself,
# which is careful and tested, and is genuinely useful when a device is not
# behaving as expected. It runs unprivileged from the shell and changes nothing.

echo "octagonOS device report"
echo

# --- form factor ------------------------------------------------------------
#
# Read the input device table rather than asking the framework, so this works
# on a device that is not fully up. Each device advertises a KEY capability
# bitmask, printed as whitespace-separated 64-bit hex groups, most significant
# first. Every key that matters is below bit 64, so only the LAST group counts:
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

    grep '^B: KEY=' /proc/bus/input/devices 2>/dev/null | while read -r line; do
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
        [ $(( (val >> 16) & 0x3ff )) -eq 1023 ] && rows=$((rows + 1))
        [ $(( (val >> 30) & 0x1ff )) -eq 511 ]  && rows=$((rows + 1))
        [ $(( (val >> 44) & 0x7f )) -eq 127 ]   && rows=$((rows + 1))

        if [ "$rows" -eq 3 ]; then
            echo found
            break
        fi
    done | grep -q found
}

if has_alpha_keyboard; then
    echo "  form factor      keyboard (a full alphabetic keypad is present)"
else
    echo "  form factor      slab (no alphabetic keypad)"
fi

# --- is FacetUI actually on? ------------------------------------------------
#
# The most common reason a device looks stock is that the overlays were never
# enabled, which this answers directly.

echo
echo "  FacetUI overlays"
if command -v cmd >/dev/null 2>&1; then
    found=$(cmd overlay list 2>/dev/null | grep -i 'facetui')
    if [ -n "$found" ]; then
        echo "$found" | sed 's/^/    /'
    else
        echo "    none installed. Check /product/overlay and that"
        echo "    /product/overlay/config/config.xml shipped alongside them."
    fi
else
    echo "    cannot query; no cmd binary"
fi

# --- the properties the design depends on -----------------------------------
echo
echo "  properties"
for p in ro.surface_flinger.supports_background_blur \
         ro.octagonos.version ro.octagonos.ui \
         ro.adb.secure ro.debuggable; do
    printf '    %-48s %s\n' "$p" "$(getprop "$p" 2>/dev/null)"
done

echo
echo "  Without supports_background_blur=1 SurfaceFlinger performs no"
echo "  cross-window blur at all and the whole design collapses to flat"
echo "  translucency. It is a property, not a resource, so no overlay can"
echo "  deliver it - it is set in the image."
