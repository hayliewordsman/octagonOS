#!/bin/bash
#
# Is FacetUI the desktop's default, or just one of its options?
#
#     desktop/tools/check-facetui-defaults.sh [--root <dir>]
#
# WHY THIS IS A CHECK AND NOT A README PARAGRAPH
#
# "Installed" and "in use" are different states, and the gap between them is
# invisible. Every piece of FacetUI can be present and correct while the
# desktop draws Breeze, because Plasma reads its settings from kdeglobals and
# plasmarc, and nothing puts them there just because a package landed.
#
# The trap in particular: naming a look-and-feel package does NOT apply its
# contents. Those are written out only when somebody selects the theme in
# System Settings. Tested directly -- with only LookAndFeelPackage set, the
# icon theme read back unset. So the individual keys have to be shipped too,
# and this checks that they are, by resolving them THE WAY A COMPONENT WOULD:
# through the XDG cascade, as a user with an empty home directory.
#
# --root points at a chroot, so the same check runs against an image before it
# is ever booted.

set -u

ROOT=""
if [ "${1:-}" = "--root" ]; then
    ROOT="${2:?--root needs a directory}"
fi

command -v kreadconfig6 >/dev/null || {
    echo "[FAIL] kreadconfig6 is not installed; cannot resolve settings the"
    echo "       way a Plasma component does"
    exit 2
}

HOMEDIR="$(mktemp -d)"
trap 'rm -rf "$HOMEDIR"' EXIT
mkdir -p "$HOMEDIR/.config"

# A user with nothing of their own. On a fresh install or a live session that
# is every user, which is the case this has to be right for.
#
# Built as an array and handed to `env`, NOT written as a bare assignment
# prefix. Bash recognises assignments SYNTACTICALLY, before expansion, so
# `${ROOT:+XDG_CONFIG_DIRS=...}` is not an assignment at all -- it expands to
# a plain word, which bash then tries to run as the command. That is what it
# did: kreadconfig6 never executed, every value came back empty, and the
# checker reported six confident FAILs about an image it had not looked at.
#
# It only broke with --root. Without it the expansion is empty and the line
# works, which is why the package-install check passed and the ISO check --
# the case this argument exists for -- did not.
read_key() {
    local -a envs=(HOME="$HOMEDIR" XDG_CONFIG_HOME="$HOMEDIR/.config")
    if [ -n "$ROOT" ]; then
        envs+=(XDG_CONFIG_DIRS="$ROOT/etc/xdg")
    fi
    env "${envs[@]}" \
        kreadconfig6 --file "$1" --group "$2" --key "$3" --default "<unset>"
}

fail=0
check_key() {
    local file="$1" group="$2" key="$3" want="$4"
    local got
    got="$(read_key "$file" "$group" "$key")"
    # --default guarantees kreadconfig6 prints SOMETHING. Empty output means
    # it never ran, and the honest response is to stop rather than to blame
    # the image for a value this script failed to read.
    if [ -z "$got" ]; then
        echo "  ERROR kreadconfig6 produced no output for $file [$group] $key;"
        echo "        this is a fault in the checker, not a finding about the"
        echo "        image. Refusing to report a result."
        exit 3
    fi
    if [ "$got" = "$want" ]; then
        printf "  ok    %-10s [%s] %s = %s\n" "$file" "$group" "$key" "$got"
    else
        printf "  FAIL  %-10s [%s] %s = %s, wanted %s\n" \
            "$file" "$group" "$key" "$got" "$want"
        fail=1
    fi
}

echo "[*] what a user with an empty home directory gets"
check_key kdeglobals Icons   Theme                FacetUI
check_key kdeglobals General ColorScheme          FacetUI
check_key kdeglobals KDE     LookAndFeelPackage   dev.octagonos.facetui
check_key plasmarc   Theme   name                 FacetUI
check_key kwinrc     Plugins facetui-glassEnabled true
check_key kwinrc     Plugins blurEnabled          true

# A setting naming a resource that is not installed is worse than no setting:
# the component falls back silently and the desktop looks half-themed.
echo "[*] and the resources those names resolve to"
for p in \
    /usr/share/icons/FacetUI/index.theme \
    /usr/share/color-schemes/FacetUI.colors \
    /usr/share/plasma/desktoptheme/FacetUI/metadata.json \
    /usr/share/plasma/look-and-feel/dev.octagonos.facetui/metadata.json \
    /usr/share/plymouth/themes/octagonos/octagonos.plymouth
do
    if [ -e "$ROOT$p" ]; then
        printf "  ok    %s\n" "$p"
    else
        printf "  FAIL  %s is named by a default but is not installed\n" "$p"
        fail=1
    fi
done

# The effect is architecture-dependent, so its path is not fixed.
if compgen -G "$ROOT/usr/lib/*/qt6/plugins/kwin/effects/plugins/facetui-glass.so" >/dev/null; then
    echo "  ok    the KWin effect plugin is installed"
else
    echo "  FAIL  the KWin effect plugin is not installed, so kwinrc enables"
    echo "        an effect that does not exist"
    fail=1
fi

# Plymouth is not an XDG setting at all: the boot theme is an alternative, and
# it is chosen before any user exists.
# --- the session that is supposed to start ----------------------------------
#
# Added after a boot test found the image sitting on a wallpaper forever.
# SDDM's autologin named Session=plasmawayland, which is the Plasma 5 name;
# Plasma 6 ships plasma.desktop. A session name that does not resolve is not
# an error anybody sees -- autologin silently does not happen and the greeter
# comes up instead, so the image looks like it is still booting.
#
# Neither the packaging checks nor the ISO content checks could see this:
# every file was present and correct, and the fault was a name in a config
# referring to a file that was never looked for. So it is looked for here.
echo "[*] the session autologin asks for"
sddm_conf="$ROOT/etc/sddm.conf.d/octagonos.conf"
if [ ! -f "$sddm_conf" ]; then
    echo "  FAIL  no $sddm_conf; nothing would log in automatically"
    fail=1
else
    au="$(sed -n 's/^User=//p'    "$sddm_conf" | head -1)"
    as="$(sed -n 's/^Session=//p' "$sddm_conf" | head -1)"

    if [ -z "$au" ]; then
        echo "  FAIL  autologin names no user"; fail=1
    elif [ -f "$ROOT/etc/passwd" ] && ! awk -F: -v u="$au" '$1==u{f=1} END{exit !f}' \
            "$ROOT/etc/passwd"; then
        echo "  FAIL  autologin user '$au' does not exist in the image"; fail=1
    else
        echo "  ok    autologin user $au exists"
    fi

    # THE SESSION DIRECTORY MUST MATCH THE DISPLAY SERVER.
    #
    # This check used to accept a session file in either directory, and that
    # is how the second boot failed: DisplayServer=wayland with Session=plasma
    # looked correct and was, but SDDM resolves the autologin session ONLY in
    # the directory belonging to the display server it is actually running.
    # Accepting either is accepting a combination SDDM will not.
    ds="$(sed -n 's/^DisplayServer=//p' "$sddm_conf" | head -1)"
    ds="${ds:-x11}"
    case "$ds" in
        wayland) sdir=wayland-sessions ;;
        *)       sdir=xsessions ;;
    esac

    if [ -z "$as" ]; then
        echo "  FAIL  autologin names no session"; fail=1
    else
        sf="${as%.desktop}.desktop"
        if [ -f "$ROOT/usr/share/$sdir/$sf" ]; then
            echo "  ok    autologin session $as is a $ds session ($sdir/$sf)"
        else
            echo "  FAIL  DisplayServer=$ds, so SDDM looks for '$as' in $sdir"
            echo "        only -- and $sdir/$sf is not there."
            if [ -f "$ROOT/usr/share/wayland-sessions/$sf" ] \
               || [ -f "$ROOT/usr/share/xsessions/$sf" ]; then
                echo "        It exists in the OTHER directory, which SDDM will"
                echo "        not use: it falls back to its greeter instead."
            fi
            echo "        available in $sdir:" \
                 "$(ls "$ROOT/usr/share/$sdir" 2>/dev/null \
                    | grep '\.desktop$' | tr '\n' ' ')"
            fail=1
        fi
    fi

    # NOTHING MAY OVERRIDE THIS CONFIG AT BOOT.
    #
    # sddm.conf(5): the load order is /usr/lib/sddm/sddm.conf.d, then
    # /etc/sddm.conf.d, then /etc/sddm.conf, "with the latter having highest
    # precedence". So a plain /etc/sddm.conf beats everything checked above.
    #
    # casper writes exactly that file, from its initramfs, at every boot --
    # which means an image can be unpacked and inspected and look completely
    # correct while the booted machine does something else. Three boots were
    # spent on that. The file does not exist to be found at build time; the
    # SCRIPT that creates it does, so that is what is checked.
    if [ -f "$ROOT/etc/sddm.conf" ]; then
        echo "  FAIL  /etc/sddm.conf exists and outranks /etc/sddm.conf.d;"
        echo "        whatever it says is what SDDM will do"
        fail=1
    else
        echo "  ok    no /etc/sddm.conf to outrank the settings above"
    fi

    casper_al="$ROOT/usr/share/initramfs-tools/scripts/casper-bottom/15autologin"
    if [ -f "$casper_al" ]; then
        echo "  FAIL  casper's 15autologin is still in this image. It writes"
        echo "        /etc/sddm.conf at boot -- User=\$USERNAME and a session"
        echo "        name it can only find among X11 sessions -- and that file"
        echo "        outranks everything above. On a Wayland image it leaves"
        echo "        Session= empty, and SDDM shows its greeter instead."
        fail=1
    elif [ -d "$ROOT/usr/share/initramfs-tools/scripts/casper-bottom" ]; then
        echo "  ok    casper's 15autologin is not in the image to override this"
    elif [ -n "$ROOT" ]; then
        # Say so out loud. Silently skipping is how this check sat inert on
        # the one path it was written for: the directory was simply not in
        # the unpack, so the `elif` above was false and nothing printed at
        # all -- a check that neither passes nor fails and is easy to read
        # as a pass.
        echo "  ERROR casper-bottom is not in this root, so whether casper"
        echo "        would override the autologin config cannot be seen from"
        echo "        here. A fault in the checker's inputs, not a finding."
        exit 3
    fi

    # casper also creates the live user from /etc/casper.conf. If that name
    # disagrees with the autologin user, the account that gets created and the
    # account that gets logged in are different ones.
    if [ -f "$ROOT/etc/casper.conf" ] && [ -n "$au" ]; then
        cu="$(sed -n 's/^export USERNAME=//p' "$ROOT/etc/casper.conf" \
              | tr -d '"' | head -1)"
        if [ -n "$cu" ] && [ "$cu" != "$au" ]; then
            echo "  FAIL  casper creates the live user '$cu' but autologin logs"
            echo "        in '$au'; they must be the same account"
            fail=1
        elif [ -n "$cu" ]; then
            echo "  ok    casper's live user and the autologin user are both $cu"
        fi
    fi

    # THE WAYLAND COMPOSITOR MUST EXIST.
    #
    # SDDM's default is `weston --shell=kiosk`, and Plasma does not depend on
    # weston. With it missing, DisplayServer=wayland cannot start and SDDM
    # falls back to X11 silently -- which then makes the check above fail for
    # a reason that looks unrelated. This is the actual first domino.
    if [ "$ds" = wayland ]; then
        cc="$(sed -n 's/^CompositorCommand=//p' "$sddm_conf" | head -1)"
        if [ -z "$cc" ]; then
            echo "  FAIL  DisplayServer=wayland but no CompositorCommand is set;"
            echo "        SDDM's default is weston, which Plasma does not install"
            fail=1
        else
            ccbin="${cc%% *}"
            case "$ccbin" in
                /*) ccpath="$ccbin" ;;
                *)  ccpath="/usr/bin/$ccbin" ;;
            esac
            # If the directory itself is absent, this root is incomplete and
            # the honest answer is that the CHECK cannot see the binary --
            # not that the image lacks it. Three separate findings in this
            # file have now turned out to be a partial unpack rather than a
            # fault in the image, and each one cost a rebuild to disbelieve.
            if [ -n "$ROOT" ] && [ ! -d "$ROOT$(dirname "$ccpath")" ]; then
                echo "  ERROR $ROOT$(dirname "$ccpath") is not in this root, so"
                echo "        whether '$ccbin' is installed cannot be seen from"
                echo "        here. This is a fault in the checker's inputs, not"
                echo "        a finding about the image. Refusing to report one."
                exit 3
            fi
            if [ -x "$ROOT$ccpath" ]; then
                echo "  ok    wayland compositor $ccbin is present"
            else
                echo "  FAIL  CompositorCommand '$ccbin' is not in the image at"
                echo "        $ccpath; the wayland display server cannot start"
                fail=1
            fi
        fi
    fi
fi

echo "[*] the boot splash"
# Resolved by following the symlink chain, NOT by asking update-alternatives.
#
# Two reasons, and the second is the one that bit. Plymouth does not consult
# the alternatives database at boot -- it opens
# /usr/share/plymouth/themes/default.plymouth and follows wherever it leads,
# so that chain is the thing worth checking. And `chroot $ROOT
# update-alternatives` needs a shell, perl and the dpkg admin directory inside
# $ROOT; the image verifier unpacks only /usr/share and /etc, so the command
# could never run there. It returned nothing, and nothing was read as "no
# alternative is set" -- a FAIL reported against an image that was correct.
#
# Absolute link targets are resolved against $ROOT, because inside the image
# that is what they mean. `readlink -f` on the host would follow them to the
# host's own filesystem and answer a question about this machine instead.
resolve_in_root() {
    local p="$1" n=0 t
    while [ -L "$ROOT$p" ] && [ "$n" -lt 20 ]; do
        t="$(readlink "$ROOT$p")"
        case "$t" in
            /*) p="$t" ;;
            *)  p="$(dirname "$p")/$t" ;;
        esac
        n=$((n + 1))
    done
    printf '%s' "$p"
}

alt="$(resolve_in_root /usr/share/plymouth/themes/default.plymouth)"
if [ "$alt" = /usr/share/plymouth/themes/default.plymouth ]; then
    alt=""                      # nothing followed: the link is not there
elif [ ! -e "$ROOT$alt" ]; then
    echo "  FAIL  default.plymouth resolves to $alt, which does not exist"
    fail=1
    alt="__dangling__"
fi
case "$alt" in
    __dangling__) ;;
    */octagonos/octagonos.plymouth)
        echo "  ok    default.plymouth points at octagonos" ;;
    "")
        echo "  FAIL  no default.plymouth alternative is set"; fail=1 ;;
    *)
        echo "  FAIL  default.plymouth points at $alt, not octagonos"; fail=1 ;;
esac

echo
if [ "$fail" -ne 0 ]; then
    echo "FAILED: FacetUI is installed but not selected. A user would have to"
    echo "pick it in System Settings."
    exit 1
fi
echo "FacetUI is the default: a new user gets it without choosing anything."
