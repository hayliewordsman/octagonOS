#!/usr/bin/env python3
"""
Check the FacetUI KWin effect against KWin's real headers.

    desktop/tools/check-kwin-api.py --kwin ../kwin

THE REAL BUILD IS THE STRONGER CHECK

`desktop/tools/run-kwin-effect.sh` compiles the effect against a real KWin and
starts KWin with it. Where that can run, it settles everything this checks and
more. This is the fast version, for a machine without KWin's development
packages -- and for one job the build cannot do.

WHAT THE BUILD CANNOT DO: SEE BREAKAGE COMING

A build tells you about the KWin you have. Pointed at KWin's master branch,
this tells you about the KWin you are about to get, which matters because
KWin's effect API is explicitly not binary compatible between versions.

That is not hypothetical. This effect was first written from master's headers,
where `OffscreenEffect::drawWindow` returns `bool`. In the 6.7 release it
returns `void`. The effect compiled against neither until the signature matched
the one being targeted, and the compiler was the only thing that said so --
which is the argument for running this against BOTH: the release you ship on,
and master, to find out what the next release will break.

So it checks that every symbol the effect uses exists, and that every
`override` matches a virtual it can really override.

It has the same ceiling as `mobile/tools/validate-overlays.py`, worth stating
rather than discovering: A NAME EXISTING IS NOT A REFERENCE RESOLVING. On the
Android side two real bugs survived exactly this check and were caught only by
running aapt2.

    desktop/tools/check-kwin-api.py                 # the installed headers
    desktop/tools/check-kwin-api.py --kwin ../kwin  # a source tree, e.g. master
"""

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
EFFECT = HERE.parent / "kwin" / "facetui-glass"

fails, notes = [], []


def fail(msg):
    fails.append(msg)


def find_headers(kwin):
    """KWin's headers, whether that is a source tree or an installed one."""
    roots = [kwin / "src", kwin / "include" / "kwin", kwin]
    for root in roots:
        if (root / "effect" / "offscreeneffect.h").exists():
            return root
    return None


def read(root, rel):
    p = root / rel
    return p.read_text() if p.exists() else None


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def normalise(sig):
    """A signature, reduced to what the compiler actually matches on."""
    sig = re.sub(r"\s+", " ", sig).strip()
    sig = sig.replace("virtual ", "").replace("override", "")
    sig = re.sub(r"\[\[nodiscard\]\]", "", sig)
    # Parameter NAMES are not part of the signature; the types are.
    def drop_names(m):
        parts = []
        for param in m.group(1).split(","):
            param = param.strip()
            if not param:
                continue
            # "const RenderTarget &renderTarget" -> "const RenderTarget &"
            param = re.sub(r"(\*|&)\s*\w+$", r"\1", param)
            param = re.sub(r"\b(\w+)\s+(\w+)$", r"\1", param)
            parts.append(re.sub(r"\s+", " ", param).strip())
        return "(" + ",".join(parts) + ")"
    sig = re.sub(r"\(([^)]*)\)", drop_names, sig)
    return re.sub(r"\s+", " ", sig).strip()


def declared_methods(src):
    """Every method declaration in a header, as normalised signatures."""
    src = strip_comments(src)
    out = {}
    for m in re.finditer(
            r"^[ \t]*((?:\[\[nodiscard\]\]\s*)?(?:virtual\s+|static\s+)?"
            r"[\w:<>,\s\*&]+?\s+(\w+)\s*\(([^;{]*?)\)\s*(?:const)?\s*"
            r"(?:override)?\s*)[;{]", src, re.M):
        out.setdefault(m.group(2), []).append(normalise(m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser(description="Check the effect against KWin's headers.")
    ap.add_argument("--kwin", default="/usr/include/kwin",
                    help="a KWin source tree, or an installed header tree "
                         "(default: /usr/include/kwin, the version installed)")
    args = ap.parse_args()

    root = find_headers(pathlib.Path(args.kwin).resolve())
    if not root:
        print(f"[FAIL] no KWin headers under {args.kwin} "
              f"(looked for effect/offscreeneffect.h)")
        return 2
    print(f"[*] KWin headers: {root}")

    headers = {}
    for rel in ("effect/effect.h", "effect/effecthandler.h", "effect/effectwindow.h",
                "effect/offscreeneffect.h", "opengl/glshadermanager.h",
                "opengl/glshader.h"):
        text = read(root, rel)
        if text is None:
            fail(f"KWin header {rel} is missing from {root}")
        else:
            headers[rel] = text
    if fails:
        for m in fails:
            print(f"[FAIL] {m}")
        return 1

    hdr = (EFFECT / "facetuiglasseffect.h").read_text()
    cpp = (EFFECT / "facetuiglasseffect.cpp").read_text()
    code = strip_comments(hdr) + "\n" + strip_comments(cpp)

    # --- 1. the base class exists ------------------------------------------
    base = re.search(r"class\s+\w+\s*:\s*public\s+(\w+)", hdr)
    if not base:
        fail("could not find the effect's base class")
    elif not re.search(rf"class\s+KWIN_EXPORT\s+{base.group(1)}\b",
                       headers["effect/offscreeneffect.h"] + headers["effect/effect.h"]):
        fail(f"the effect derives from {base.group(1)}, which KWin does not declare")
    else:
        print(f"[ok]   base class {base.group(1)} exists")

    # --- 2. every override really overrides --------------------------------
    #
    # The check that matters most. An override whose signature has drifted does
    # not override anything: with the keyword it fails to compile, and the
    # compiler is not here to say so.
    base_methods = {}
    for rel in ("effect/effect.h", "effect/offscreeneffect.h"):
        for name, sigs in declared_methods(headers[rel]).items():
            base_methods.setdefault(name, []).extend(sigs)

    overrides = re.findall(
        r"^[ \t]*([\w:<>,\s\*&]+?\s+(\w+)\s*\([^;{]*?\)\s*(?:const)?\s*)override",
        strip_comments(hdr), re.M)
    if not overrides:
        fail("the effect declares no overrides at all -- this check is not "
             "running, whatever else it prints")
    for raw, name in overrides:
        want = normalise(raw)
        have = base_methods.get(name, [])
        if not have:
            fail(f"{name}() is marked override, but KWin declares no virtual "
                 f"of that name")
        elif want not in have:
            fail(f"{name}() is marked override but its signature does not "
                 f"match any KWin virtual:\n"
                 f"         effect: {want}\n"
                 f"         kwin:   " +
                 "\n                 ".join(have))
    if not fails:
        print(f"[ok]   all {len(overrides)} overrides match a KWin virtual "
              f"({', '.join(sorted(n for _, n in overrides))})")

    # --- 3. EffectWindow predicates exist ----------------------------------
    win_methods = declared_methods(headers["effect/effectwindow.h"])
    used = sorted(set(re.findall(r"window->(\w+)\(", code)))
    missing = [m for m in used if m not in win_methods]
    if missing:
        fail(f"EffectWindow has no {', '.join(missing)} -- "
             f"the effect calls {'it' if len(missing) == 1 else 'them'}")
    else:
        print(f"[ok]   all {len(used)} EffectWindow methods exist "
              f"({', '.join(used)})")

    # --- 4. ShaderTrait enumerators exist ----------------------------------
    traits_block = re.search(r"enum class ShaderTrait\s*\{(.*?)\}",
                             headers["opengl/glshadermanager.h"], re.S)
    known = set(re.findall(r"(\w+)\s*=", traits_block.group(1))) if traits_block else set()
    used_traits = sorted(set(re.findall(r"ShaderTrait::(\w+)", code)))
    if not known:
        fail("could not read KWin's ShaderTrait enum; check 4 is not running")
    else:
        bad = [t for t in used_traits if t not in known]
        if bad:
            fail(f"ShaderTrait has no {', '.join(bad)}")
        else:
            print(f"[ok]   ShaderTraits used exist ({', '.join(used_traits)})")

    # --- 5. ShaderManager and OffscreenEffect methods ----------------------
    sm = declared_methods(headers["opengl/glshadermanager.h"])
    for name in sorted(set(re.findall(r"ShaderManager::instance\(\)->(\w+)\(", code))):
        if name not in sm:
            fail(f"ShaderManager has no {name}()")
    off = declared_methods(headers["effect/offscreeneffect.h"])
    for name in ("redirect", "setShader"):
        if re.search(rf"\b{name}\(", code) and name not in off:
            fail(f"OffscreenEffect has no {name}()")
    if not fails:
        print("[ok]   ShaderManager and OffscreenEffect calls exist")

    # --- 6. the shader the effect loads is the one that is packaged --------
    qrc = (EFFECT / "facetui-glass.qrc").read_text()
    prefix = re.search(r'qresource prefix="([^"]+)"', qrc)
    files = re.findall(r"<file>([^<]+)</file>", qrc)
    for path in re.findall(r'QStringLiteral\("(:[^"]+)"\)', code):
        want = path[1:]
        got = [f"{prefix.group(1)}/{f}" for f in files] if prefix else []
        if want not in got:
            fail(f"the effect loads {path}, which the .qrc does not provide "
                 f"(it has: {', '.join(got) or 'nothing'}) -- KWin would log "
                 f"'Failed to read shader' and the effect would do nothing")
        else:
            for f in files:
                if not (EFFECT / f).exists():
                    fail(f"the .qrc lists {f}, which does not exist")
    if not fails:
        print("[ok]   the shader the effect loads is the one the .qrc packages")

    for m in fails:
        print(f"[FAIL] {m}")
    if fails:
        print(f"\nFAILED: {len(fails)} problem(s)")
        return 1
    print("\nEvery KWin symbol the effect uses exists, and every override "
          "matches.\nThis is NOT a build: a name existing is not a reference "
          "resolving, and only\ncompiling against a real KWin settles it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
