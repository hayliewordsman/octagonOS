#!/bin/bash
#
# Build the FacetUI KWin effect, install it, start a real KWin, and report what
# KWin did with it.
#
#     desktop/tools/run-kwin-effect.sh
#
# WHAT THIS PROVES, AND WHAT IT CANNOT
#
# The effect is a binary plugin for a compositor. Three things can go wrong
# with one, and they fail in very different places:
#
#   1. it does not build            -- caught by any compiler
#   2. it builds but KWin will not load it   (wrong IID, bad metadata,
#      a factory macro that moc never saw)   -- caught here
#   3. it loads but draws the wrong thing    -- needs a GPU
#
# This settles 1 and 2. It cannot settle 3 without a DRM render node: with no
# /dev/dri, KWin falls back to its QPainter renderer, where OpenGL effects --
# including KWin's own blur -- report themselves unsupported and are not
# loaded. That is the effect behaving correctly, and the script says so rather
# than calling it a pass.
#
# Needs KWin's development packages and kwin_wayland. On a distribution without
# Plasma 6 (Ubuntu 24.04 among them) the KDE neon archive provides them, since
# neon is that same Ubuntu with Plasma 6 on top:
#
#   curl -fsSL https://archive.neon.kde.org/public.key | gpg --dearmor \
#       > /usr/share/keyrings/neon.gpg
#   echo "deb [signed-by=/usr/share/keyrings/neon.gpg] \
#         http://archive.neon.kde.org/user noble main" \
#       > /etc/apt/sources.list.d/neon.list
#   apt update && apt install -y --no-install-recommends \
#       kwin-dev kwin-wayland extra-cmake-modules qt6-base-dev \
#       libkf6coreaddons-dev libkf6config-dev

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
EFFECT="$HERE/../kwin/facetui-glass"
BUILD="${BUILD_DIR:-/tmp/facetui-glass-build}"
RUN="${RUN_DIR:-/tmp/facetui-glass-run}"
LOG="$RUN/kwin.log"

fail=0
say_ok()   { echo "[ok]   $1"; }
say_fail() { echo "[FAIL] $1"; fail=1; }
say_note() { echo "[note] $1"; }

# --- build ------------------------------------------------------------------

echo "[*] building"
rm -rf "$BUILD"
if ! cmake -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -S "$EFFECT" > "$RUN.cmake.log" 2>&1; then
    echo "[FAIL] cmake could not configure the effect:"
    tail -20 "$RUN.cmake.log"
    exit 1
fi
if ! cmake --build "$BUILD" > "$RUN.build.log" 2>&1; then
    echo "[FAIL] the effect does not compile:"
    tail -30 "$RUN.build.log"
    exit 1
fi
say_ok "the effect compiles and links against KWin $(pkg-config --modversion kwin 2>/dev/null || echo '(version unknown)')"

# A warning here is not cosmetic: AutoMoc failing to see the factory macro
# means moc may not run, and a plugin with no metadata is one KWin silently
# never loads.
if grep -q "AutoMoc warning" "$RUN.build.log"; then
    say_fail "AutoMoc warned during the build; see $RUN.build.log"
fi

SO="$(find "$BUILD" -name 'facetui-glass.so' | head -1)"
[ -n "$SO" ] || { say_fail "the build produced no facetui-glass.so"; exit 1; }

# --- the plugin is what KWin's loader is looking for ------------------------

if command -v qtplugininfo6 >/dev/null; then
    INFO="$(qtplugininfo6 "$SO" 2>&1)"
    if echo "$INFO" | grep -q "org.kde.kwin.EffectPluginFactory"; then
        say_ok "Qt reads it as $(echo "$INFO" | head -1 | sed 's/.*IID //; s/ Qt.*//')"
    else
        say_fail "Qt does not see a KWin effect factory in the plugin -- moc "
        say_fail "probably never ran on the factory macro, so KWin will ignore it"
    fi
    # KWin derives the plugin id from the file name; stating one in the
    # metadata is ignored and logged about on every start.
    if echo "$INFO" | grep -q '"Id"'; then
        say_fail "metadata.json sets an Id, which KWin ignores and complains about"
    fi
fi

# --- run KWin ---------------------------------------------------------------

echo "[*] installing and starting kwin_wayland"
rm -rf "$RUN"; mkdir -p "$RUN/xdg" "$RUN/.config"
chmod 700 "$RUN/xdg"

if ! cmake --install "$BUILD" > "$RUN.install.log" 2>&1; then
    say_fail "cmake --install failed; see $RUN.install.log"
    exit 1
fi

cat > "$RUN/.config/kwinrc" <<'RC'
[Plugins]
facetui-glassEnabled=true
blurEnabled=true

[Compositing]
Enabled=true
RC

export HOME="$RUN"
export XDG_RUNTIME_DIR="$RUN/xdg"
export XDG_CONFIG_HOME="$RUN/.config"
export XDG_DATA_HOME="$RUN/.local/share"
export QT_QPA_PLATFORM=offscreen
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
# The virtual backend defaults to QPainter; ask for OpenGL so the effect has a
# chance of being supported at all.
export KWIN_COMPOSE=O2ES
# Without this KWin's own messages go to the journal and this script reads an
# empty log, which looks exactly like KWin never starting.
export QT_FORCE_STDERR_LOGGING=1
export QT_LOGGING_RULES="kwin_effect_facetui_glass.info=true;kwin_core.debug=true"

dbus-run-session -- bash -c '
  kwin_wayland --virtual --width 1280 --height 800 --no-lockscreen \
               --no-global-shortcuts > "'"$LOG"'" 2>&1 &
  KWIN=$!
  for _ in $(seq 1 40); do
      busctl --user list 2>/dev/null | grep -q org.kde.KWin && break
      sleep 0.5
  done
  sleep 2
  busctl --user get-property org.kde.KWin /Compositor \
      org.kde.kwin.Compositing compositingType > "'"$RUN"'/type" 2>&1
  busctl --user call org.kde.KWin /Effects org.kde.kwin.Effects \
      isEffectLoaded s facetui-glass > "'"$RUN"'/loaded" 2>&1
  kill $KWIN 2>/dev/null; wait $KWIN 2>/dev/null
' >/dev/null 2>&1

[ -s "$LOG" ] || { say_fail "kwin_wayland produced no log; it did not start"; exit 1; }
say_ok "kwin_wayland started and answered on D-Bus"

# --- what did KWin do with it? ----------------------------------------------

if ! grep -q "facetui-glass" "$LOG"; then
    say_fail "KWin never mentions facetui-glass: the plugin was not even found "
    say_fail "in ${XDG_DATA_HOME:-}$(qtpaths6 --plugin-dir 2>/dev/null)/kwin/effects/plugins"
else
    say_ok "KWin found the plugin and acted on it"
fi

TYPE="$(sed 's/^s //; s/"//g' "$RUN/type" 2>/dev/null)"
LOADED="$(cat "$RUN/loaded" 2>/dev/null)"

if grep -q 'Successfully loaded plugin effect:  "facetui-glass"' "$LOG"; then
    say_ok "KWin loaded the effect"
    if grep -q "glass shader built" "$LOG"; then
        say_ok "the shader compiled inside KWin's own GL context"
    else
        say_fail "the effect loaded but never reported building its shader"
    fi
    if grep -q "failed to build" "$LOG"; then
        say_fail "the shader failed to build inside KWin"
    fi
    echo "$LOADED" | grep -q "b true" \
        && say_ok "isEffectLoaded says yes" \
        || say_fail "KWin logged a successful load but isEffectLoaded says no"
elif grep -q 'Effect is not supported:  "facetui-glass"' "$LOG"; then
    # Is this our problem or the machine's? KWin's own blur is the control: it
    # needs OpenGL for the same reason, so if blur is out too, so is everything.
    if grep -q 'Effect is not supported:  "blur"' "$LOG"; then
        say_note "KWin is compositing with '$TYPE', not OpenGL -- there is no"
        say_note "DRM render node here (/dev/dri is absent), so KWin's own blur"
        say_note "effect is unsupported on this machine too. The effect"
        say_note "declining is correct behaviour, not a failure."
        say_note "NOT PROVEN HERE: that the effect draws the right thing. That"
        say_note "needs a GPU. The shader's arithmetic is settled separately by"
        say_note "desktop/tools/validate-kwin-shaders.py, against a real driver."
    else
        say_fail "KWin reports the effect unsupported while its own blur effect"
        say_fail "loaded -- compositing is '$TYPE', so this one is ours"
    fi
else
    say_fail "KWin neither loaded nor rejected the effect; see $LOG"
fi

echo
if [ "$fail" -ne 0 ]; then
    echo "FAILED"
    exit 1
fi
echo "Everything checkable without a GPU checks out."
exit 0
