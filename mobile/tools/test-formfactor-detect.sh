#!/usr/bin/env bash
#
# Test the physical-keyboard detection in octagonos-formfactor.sh.
#
#     tools/test-formfactor-detect.sh
#
# The detection reads a KEY capability bitmask out of /proc/bus/input/devices
# and decides whether a device is a real alphabetic keyboard. The bit
# arithmetic is fiddly enough to be worth testing rather than trusting: it
# reads the last of several hex groups, and that group routinely has its top
# bit set, which wraps negative in 64-bit shell arithmetic.
#
# It no longer decides anything at boot - see the note at the top of
# octagonos-formfactor.sh - but it is what a support report says about a device,
# and a wrong answer there sends someone looking in the wrong place.
#
# The fixtures are SYNTHETIC. The bitmasks are constructed from the Linux input
# event codes (uapi/linux/input-event-codes.h) rather than captured from
# hardware -- there is no device here to capture from. They exercise the
# arithmetic, not the question of what a particular phone actually reports.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/octagonos-formfactor.sh"

pass=0
fail=0

# Extract has_alpha_keyboard from the real script, so the test cannot drift away
# from the code it is testing.
extract_function() {
    sed -n '/^has_alpha_keyboard()/,/^}/p' "$TARGET"
}

# Build a KEY= bitmask with the given bit numbers set, printed the way the
# kernel prints it: 64-bit hex groups, most significant first.
make_mask() {
    python3 -c '
import sys
bits = [int(b) for b in sys.argv[1:]]
v = 0
for b in bits:
    v |= 1 << b
groups = []
while True:
    groups.append(v & 0xFFFFFFFFFFFFFFFF)
    v >>= 64
    if v == 0:
        break
print(" ".join("%x" % g for g in reversed(groups)))
' "$@"
}

# The full alphabet, as three keyboard rows.
ALPHA_BITS="16 17 18 19 20 21 22 23 24 25 30 31 32 33 34 35 36 37 38 44 45 46 47 48 49 50"

check() {
    local name="$1" expect="$2" devices_file="$3"
    local out
    out=$(
        # shellcheck disable=SC2016
        {
            extract_function
            echo "has_alpha_keyboard && echo KEYBOARD || echo SLAB"
        } | sed "s#/proc/bus/input/devices#$devices_file#g" | bash
    )
    if [ "$out" = "$expect" ]; then
        printf '  ok    %-46s -> %s\n' "$name" "$out"
        pass=$((pass + 1))
    else
        printf '  FAIL  %-46s -> %s (expected %s)\n' "$name" "$out" "$expect"
        fail=$((fail + 1))
    fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# --- a physical-keyboard phone ----------------------------------------------
cat > "$tmp/keyboard" <<EOF
I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="gpio-keys"
B: KEY=$(make_mask 114 115)
I: Bus=0018 Vendor=0000 Product=0000 Version=0000
N: Name="synthetic-alpha-keypad"
B: KEY=$(make_mask $ALPHA_BITS)
EOF
check "alphabetic keypad present" KEYBOARD "$tmp/keyboard"

# --- an ordinary slab --------------------------------------------------------
# Volume rocker and power only. Both are above bit 64, which is exactly the case
# that would read as a full alphabet if the code looked at the wrong group.
cat > "$tmp/slab" <<EOF
I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="gpio-keys"
B: KEY=$(make_mask 114 115 116)
EOF
check "volume rocker and power only" SLAB "$tmp/slab"

# --- a partial keypad --------------------------------------------------------
# A numeric keypad or a d-pad has some KEY bits in the low group but not three
# full letter rows. This is the misdetection the three-row test exists to stop.
cat > "$tmp/partial" <<EOF
I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="synthetic-numeric-keypad"
B: KEY=$(make_mask 2 3 4 5 6 7 8 9 10 11 114 115)
EOF
check "numeric keypad, no letter rows" SLAB "$tmp/partial"

# --- two rows but not three --------------------------------------------------
cat > "$tmp/tworow" <<EOF
I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="synthetic-two-row"
B: KEY=$(make_mask 16 17 18 19 20 21 22 23 24 25 30 31 32 33 34 35 36 37 38)
EOF
check "top and home rows, no bottom row" SLAB "$tmp/tworow"

# --- a mask with the top bit set --------------------------------------------
# The low group wraps negative in 64-bit shell arithmetic. The masks must still
# read correctly; if they did not, every such device would misdetect.
cat > "$tmp/signbit" <<EOF
I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="synthetic-alpha-with-high-bit"
B: KEY=$(make_mask $ALPHA_BITS 63)
EOF
check "alphabet plus bit 63 set (negative wrap)" KEYBOARD "$tmp/signbit"

# --- malformed table ---------------------------------------------------------
cat > "$tmp/junk" <<'EOF'
I: Bus=0019 Vendor=0001 Product=0001 Version=0100
B: KEY=zzzz notahexnumber
EOF
check "malformed bitmask does not crash" SLAB "$tmp/junk"

# --- no table at all ---------------------------------------------------------
check "missing input table" SLAB "$tmp/does-not-exist"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
