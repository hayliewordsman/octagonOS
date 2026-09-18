#!/usr/bin/env python3
"""
Check the octagonOS Plymouth theme without booting a machine.

    desktop/tools/verify-plymouth-theme.py [theme-dir]

WHAT THIS IS FOR

A Plymouth theme fails silently. The script language has no error output a
theme author will ever see: a callback that never runs, a sprite that is thrown
away, an image that does not exist -- each one draws nothing and logs nothing,
and the first symptom is a machine sitting at a black screen asking for a
passphrase it never displayed.

Every check below exists because the corresponding mistake was made here and
cost a debugging session. They are static: they read the script, they do not
run it. Running it is what the Xvfb harness is for, and that is in the README.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "..", "plymouth", "octagonos")

#: Callbacks a theme must register to be usable on a machine with an encrypted
#: disk. Missing display_password is the one that ruins a machine; missing
#: display_normal leaves the prompt on screen for the rest of the boot.
REQUIRED_CALLBACKS = [
    ("SetRefreshFunction", "the animation never advances"),
    ("SetDisplayPasswordFunction",
     "a machine with an encrypted disk shows no passphrase prompt"),
    ("SetDisplayQuestionFunction", "non-secret prompts show nothing"),
    ("SetDisplayNormalFunction",
     "the prompt and bullets stay on screen after the disk unlocks"),
    ("SetMessageFunction", "boot messages are never shown"),
    ("SetQuitFunction", "the animation is cut off mid-frame at handover"),
]

fails, warns = [], []


def fail(msg):
    fails.append(msg)


def warn(msg):
    warns.append(msg)


def find_functions(src):
    """Yield (name, params, body) for every `fun name(a, b) { ... }`.

    Brace-matched rather than regexed to the closing brace, because the bodies
    contain braces.
    """
    for m in re.finditer(r"\bfun\s+(\w+)\s*\(([^)]*)\)\s*\{", src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        params = [p.strip() for p in m.group(2).split(",") if p.strip()]
        yield m.group(1), params, src[m.end():i - 1]


def strip_comments(src):
    return re.sub(r"#[^\n]*", "", src)


def assigned_names(body):
    """Names this chunk assigns to, and names it assigns to *as a hash*.

    `a = 1` and `a[0] = 1` both assign `a`; the second also makes it a hash.
    `==` is excluded, and so is anything inside a string.
    """
    body = re.sub(r'"[^"]*"', '""', body)
    plain = set(re.findall(r"^\s*(\w+)\s*=(?!=)", body, re.M))
    hashed = set(re.findall(r"^\s*(\w+)\s*\[[^\]]*\]\s*=(?!=)", body, re.M))
    return plain | hashed, hashed


def check_script(theme_dir, script_path):
    src = open(script_path).read()
    code = strip_comments(src)

    # --- callbacks ----------------------------------------------------------
    for name, consequence in REQUIRED_CALLBACKS:
        if f"Plymouth.{name}" not in code:
            fail(f"{name} is not registered -- {consequence}")

    if "Plymouth.SetHideMessageFunction" in code:
        # Registering it is right; relying on it is not. Plymouth 24.004 logs
        # "hiding message" in the daemon and never calls the theme back.
        if not re.search(r"message_ticks|message_lifetime|message_timeout", code):
            warn("SetHideMessageFunction is registered but nothing expires a "
                 "message on its own; on plymouth 24.004 the callback never "
                 "fires and the message stays up for the rest of the boot")

    # --- the scoping trap ---------------------------------------------------
    #
    # Plymouth script scopes assignment by function. Writing to a name that
    # already exists globally updates the global; writing to one that does not
    # creates a function-local that dies on return. `bullets[0] = Sprite()`
    # inside display_password therefore builds a sprite, draws nothing, and
    # discards it -- silently. This is the check that would have caught it.
    funcs = list(find_functions(code))
    top = code
    for name, _params, body in funcs:
        top = top.replace(body, "")
    top_names, _ = assigned_names(top)

    fn_names = {n for n, _, _ in funcs}
    for name, params, body in funcs:
        used, hashed = assigned_names(body)
        for v in sorted(used):
            if v in top_names or v in params or v in fn_names:
                continue
            if v in hashed:
                fail(f"{name}() assigns to {v}[...] but {v} is never created "
                     f"at top level -- the assignment makes a function-local "
                     f"that is destroyed on return, so nothing is drawn")
            else:
                # A scalar written and read only inside one call is fine.
                reads = len(re.findall(rf"\b{re.escape(v)}\b", code))
                if reads > len(re.findall(rf"\b{re.escape(v)}\b", body)):
                    fail(f"{name}() assigns to {v}, which is read outside it "
                         f"but never created at top level -- the write goes to "
                         f"a function-local and the outside never sees it")

    # --- declaration order --------------------------------------------------
    #
    # A global has to exist before the function that writes to it runs. For
    # state the refresh function touches that means before the script finishes
    # loading, which is easy to get wrong when the declaration drifts down
    # beside the code that uses it.
    for name, _params, body in funcs:
        if name != "refresh":
            continue
        for v in sorted(assigned_names(body)[0]):
            if v not in top_names:
                continue
            decl = re.search(rf"^\s*{re.escape(v)}\s*=(?!=)", top, re.M)
            fun_at = code.index(f"fun {name}")
            if decl and decl.start() > fun_at:
                warn(f"refresh() writes {v}, which is not declared until after "
                     f"refresh is defined -- it works only because refresh is "
                     f"called later; move the declaration up")

    # --- images -------------------------------------------------------------
    have = set(os.listdir(theme_dir))

    for lit in re.findall(r'Image\(\s*"([^"]+)"\s*\)', code):
        if lit not in have:
            fail(f'Image("{lit}") does not exist in {theme_dir}')

    # Frames are addressed by concatenation, so check the ranges the generated
    # counts claim rather than the literal.
    counts = {}
    for key in ("intro_count", "loop_count", "outro_count"):
        m = re.search(rf"^{key}\s*=\s*(\d+)\s*;", code, re.M)
        if not m:
            fail(f"{key} is not defined -- make-plymouth-theme.py prepends it; "
                 f"a separate .script file is never read, because Plymouth "
                 f"loads only the one ScriptFile named in the .plymouth config")
        else:
            counts[key[:-6]] = int(m.group(1))

    for prefix, n in counts.items():
        missing = [f"{prefix}-{i}.png" for i in range(n)
                   if f"{prefix}-{i}.png" not in have]
        if missing:
            fail(f"{prefix}_count is {n} but {len(missing)} frames are missing "
                 f"(first: {missing[0]})")
        extra = [f for f in have
                 if re.fullmatch(rf"{prefix}-(\d+)\.png", f)
                 and int(re.fullmatch(rf"{prefix}-(\d+)\.png", f).group(1)) >= n]
        if extra:
            warn(f"{len(extra)} {prefix} frames past {prefix}_count={n} are "
                 f"shipped but never shown (e.g. {sorted(extra)[0]})")

    # --- one script ---------------------------------------------------------
    others = [f for f in have if f.endswith(".script")
              and f != os.path.basename(script_path)]
    if others:
        fail(f"more than one .script in the theme: {', '.join(sorted(others))} "
             f"-- Plymouth loads only the ScriptFile named in the .plymouth "
             f"config, so these are dead files that look live")

    return code


def check_conf(theme_dir):
    confs = [f for f in os.listdir(theme_dir) if f.endswith(".plymouth")]
    if not confs:
        fail(f"no .plymouth config in {theme_dir}")
        return None
    if len(confs) > 1:
        fail(f"several .plymouth configs: {', '.join(sorted(confs))}")
    path = os.path.join(theme_dir, confs[0])
    text = open(path).read()

    keys = dict(re.findall(r"^(\w+)\s*=\s*(.*)$", text, re.M))
    if keys.get("ModuleName") != "script":
        fail(f"ModuleName is {keys.get('ModuleName')!r}, expected 'script'")
    for key in ("ImageDir", "ScriptFile"):
        if key not in keys:
            fail(f"{key} is missing from {confs[0]}")

    script = keys.get("ScriptFile", "")
    local = os.path.join(theme_dir, os.path.basename(script))
    if not os.path.exists(local):
        fail(f"ScriptFile points at {script}, and {os.path.basename(script)} "
             f"is not in the theme directory")
        return None
    return local


def main():
    theme_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    if not os.path.isdir(theme_dir):
        print(f"[!!] no such theme directory: {theme_dir}")
        return 2

    script = check_conf(theme_dir)
    if script:
        check_script(theme_dir, script)

    for m in warns:
        print(f"[warn] {m}")
    for m in fails:
        print(f"[FAIL] {m}")

    n = len(os.listdir(theme_dir))
    if fails:
        print(f"\nFAILED: {len(fails)} problem(s) in {theme_dir}")
        return 1
    print(f"[ok] {theme_dir}: {n} files, "
          f"{len(REQUIRED_CALLBACKS)} required callbacks, images resolve"
          + (f", {len(warns)} warning(s)" if warns else ""))
    print("     Static only. It does not run the script -- see the README for")
    print("     the Xvfb harness that does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
