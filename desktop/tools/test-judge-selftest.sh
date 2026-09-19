#!/bin/bash
#
# Check that judge-selftest.sh reaches the right verdict.
#
#     desktop/tools/test-judge-selftest.sh
#
# WHY THESE EXIST
#
# The verdict logic used to live at the bottom of boot-iso-check.sh, where
# the only way to run it was to boot a virtual machine for half an hour. It
# was wrong in a way nobody would choose: asked to explain a failed boot, it
# announced that OpenGL compositing was working and that KWin's own blur had
# loaded, on a boot where the self-test had exited before either was checked
# and no such line existed. It tested for blur reporting FALSE and read
# silence as confirmation.
#
# Every case below takes a fraction of a second. The one that matters most is
# `no-blur-line`: an absent line is not a passing line.

set -u
set -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
JUDGE="$HERE/judge-selftest.sh"
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

pass=0; total=0

# Verdicts are wrapped prose, so the output is flattened before matching: a
# phrase that spans a line break is invisible to a per-line grep, which once
# made this suite report a failure against entirely correct output.
check() {
    local name="$1" want_rc="$2" want_text="$3"; shift 3
    printf '%s\n' "$@" > "$D/log"
    total=$((total + 1))
    local out rc flat
    out="$("$JUDGE" "$D/log" 2>&1)"; rc=$?
    flat="$(printf '%s' "$out" | tr '\n' ' ' | tr -s ' ')"
    if [ "$rc" -eq "$want_rc" ] && printf '%s' "$flat" | grep -qi -- "$want_text"; then
        printf "  ok    %-30s exit=%d\n" "$name" "$rc"
        pass=$((pass + 1))
    else
        printf "  FAIL  %-30s exit=%d (wanted %d, matching '%s')\n" \
            "$name" "$rc" "$want_rc" "$want_text"
        printf '%s\n' "$out" | sed 's/^/          /'
    fi
}

S="OCTAGONOS-SELFTEST:"

check "no self-test ran" 2 "never ran" \
    "[  OK  ] Reached target graphical.target" "ubuntu login:"

check "no session appeared" 2 "NO SESSION" \
    "$S FAIL no session bus after 900s; the desktop did not start" "$S END"

check "no OpenGL, blur out too" 2 "INCONCLUSIVE" \
    "$S OK   render node: /dev/dri/renderD128" \
    "$S FAIL compositing is 'QPainter', not OpenGL" \
    "$S FAIL facetui-glass is NOT loaded" \
    "$S INFO kwin blur loaded: false" "$S END"

check "no render node" 2 "INCONCLUSIVE" \
    "$S FAIL no /dev/dri render node; KWin cannot use OpenGL" \
    "$S FAIL facetui-glass is NOT loaded" "$S END"

# The case the old code got backwards, and the reason for this file.
check "no-blur-line" 1 "UNATTRIBUTED" \
    "$S FAIL facetui-glass is NOT loaded" "$S END"

check "blur loaded, ours did not" 1 "a real failure in FacetUI" \
    "$S OK   compositing: OpenGL" \
    "$S FAIL facetui-glass is NOT loaded" \
    "$S INFO kwin blur loaded: true" "$S END"

check "theme wrong, blur fine" 1 "a real failure in FacetUI" \
    "$S OK   compositing: OpenGL" \
    "$S OK   facetui-glass is loaded and running" \
    "$S INFO kwin blur loaded: true" \
    "$S FAIL kdeglobals [Icons] Theme = 'Breeze', wanted FacetUI" "$S END"

check "silence is not success" 2 "NO VERDICT" \
    "$S INFO kwin blur loaded: true" "$S END"

check "the success case" 0 "FacetUI is running" \
    "$S OK   render node: /dev/dri/renderD128" \
    "$S OK   compositing: OpenGL" \
    "$S OK   facetui-glass is loaded and running" \
    "$S INFO kwin blur loaded: true" \
    "$S OK   kdeglobals [Icons] Theme = FacetUI" "$S END"

echo
echo "  $pass/$total"
[ "$pass" -eq "$total" ]
