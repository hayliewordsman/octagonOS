#!/bin/bash
#
# Turn an octagonOS self-test serial log into a verdict.
#
#     desktop/tools/judge-selftest.sh <serial.log>
#
# WHY THIS IS ITS OWN SCRIPT
#
# It used to be the last twenty lines of boot-iso-check.sh, which meant the
# only way to exercise it was to boot a virtual machine for half an hour. It
# was wrong, and the way I found out was by reading a verdict that said
# "OpenGL compositing working (KWin's own blur loaded), and FacetUI is still
# not running" about a boot where the self-test had never reached the blur
# check and no such line existed. The code asked whether blur had reported
# FALSE and treated everything else -- including silence -- as a pass.
#
# Separated out, it takes a text file and prints a verdict, so every branch
# can be checked in a second against a log written by hand. A judgement that
# cannot be tested is a judgement nobody has checked.
#
# EXIT CODES
#   0  FacetUI is running
#   1  a real failure, attributed
#   2  inconclusive: the environment, not FacetUI

set -u
set -o pipefail

SERIAL="${1:?usage: judge-selftest.sh <serial.log>}"
[ -f "$SERIAL" ] || { echo "no such log: $SERIAL"; exit 2; }

if ! grep -q "OCTAGONOS-SELFTEST:" "$SERIAL" 2>/dev/null; then
    echo "NO REPORT: the guest never ran the self-test. Either it did not"
    echo "reach a desktop session, or the self-test is not in this image."
    exit 2
fi

if ! grep -q "OCTAGONOS-SELFTEST: FAIL" "$SERIAL"; then
    if grep -q "facetui-glass is loaded and running" "$SERIAL"; then
        echo "FacetUI is running on a booted machine, with OpenGL compositing"
        echo "and the glass effect loaded. That is the one thing no offline"
        echo "check could settle."
        exit 0
    fi
    # No FAIL lines, but no confirmation either. Silence is not success.
    echo "NO VERDICT: nothing failed, but the self-test never reported that"
    echo "facetui-glass is loaded. Do not read this as a pass."
    exit 2
fi

# --- a failure. Attribute it, and only on evidence that is present. ---------

# The session never came up, so nothing was measured about anything.
if grep -q "FAIL no session bus" "$SERIAL"; then
    echo "NO SESSION: the image booted, but no desktop session appeared within"
    echo "the self-test's patience. Nothing here is evidence about FacetUI --"
    echo "the session it would have been measured in does not exist. Check the"
    echo "autologin user and session name, and whether sddm started."
    exit 2
fi

# No usable graphics. KWin's own blur is the control: an OpenGL effect
# maintained by people who are not me. If it is out too, this guest has no
# working OpenGL and the facetui-glass line says nothing about facetui-glass.
if grep -q "INFO kwin blur loaded: false" "$SERIAL" \
   || grep -q "FAIL no /dev/dri render node" "$SERIAL" \
   || grep -q "FAIL compositing is" "$SERIAL"; then
    echo "INCONCLUSIVE: this guest has no working OpenGL compositing -- KWin's"
    echo "own blur did not load either. Nothing here is evidence about"
    echo "facetui-glass; fix the guest's graphics, then re-run."
    exit 2
fi

# Only with blur POSITIVELY reported loaded is the effect itself implicated.
if grep -q "INFO kwin blur loaded: true" "$SERIAL"; then
    echo "FAILED: the image booted with OpenGL compositing working (KWin's own"
    echo "blur loaded), and FacetUI is still not running on it. That is a real"
    echo "failure in FacetUI, not in the test environment."
    exit 1
fi

echo "FAILED, CAUSE UNATTRIBUTED: the self-test reported a failure but did not"
echo "get far enough to say whether this guest has working OpenGL. Read the"
echo "lines above before concluding anything about FacetUI."
exit 1
