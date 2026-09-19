#!/usr/bin/env python3
"""
Check that the Calamares configuration names things that exist.

    desktop/tools/verify-calamares-config.py [--modules-dir DIR]

WHY THIS IS WORTH HAVING

Calamares reads its sequence at startup and needs a display to get that far,
so a typo in a module name is not discovered until somebody launches the
installer on a live machine -- and then it is discovered as a failure to
start, with no obvious cause. This is the part that can be checked offline:
every module in the sequence exists, every module with a config file has one,
every instance is declared, and the branding names images that are present.

It cannot tell you the installer WORKS. Nothing offline can.
"""

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONF = HERE.parent / "installer" / "calamares"
MODULES_DIR = Path("/usr/lib/x86_64-linux-gnu/calamares/modules")

for i, a in enumerate(sys.argv):
    if a == "--modules-dir":
        MODULES_DIR = Path(sys.argv[i + 1])

fail = 0


def ok(m):
    print(f"  ok    {m}")


def bad(m):
    global fail
    print(f"  FAIL  {m}")
    fail = 1


settings = yaml.safe_load((CONF / "settings.conf").read_text())

# Instances first: a sequence entry of the form module@id must be declared.
instances = {f"{i['module']}@{i['id']}": i for i in settings.get("instances", [])}

available = set()
if MODULES_DIR.is_dir():
    available = {p.name for p in MODULES_DIR.iterdir() if p.is_dir()}
    print(f"[*] {len(available)} modules installed in {MODULES_DIR}")
else:
    print(f"[*] {MODULES_DIR} is not here; module existence cannot be checked")

print("[*] every module in the sequence")
seen = []
for phase in settings["sequence"]:
    for kind, mods in phase.items():
        for m in mods:
            seen.append(m)
            base = m.split("@")[0]
            if "@" in m and m not in instances:
                bad(f"{m} is used but no instance declares it")
                continue
            if available and base not in available:
                bad(f"{m} names no installed module ({base})")
            else:
                ok(f"{m}")

print("[*] every declared instance is used")
for name in instances:
    ok(name) if name in seen else bad(f"instance {name} is declared and never used")

print("[*] config files the sequence needs")
for m in set(seen):
    base = m.split("@")[0]
    cfg = instances[m]["config"] if "@" in m else f"{base}.conf"
    p = CONF / "modules" / cfg
    if p.exists():
        try:
            yaml.safe_load(p.read_text())
            ok(f"{cfg}")
        except Exception as e:
            bad(f"{cfg} is not valid YAML: {e}")
    elif "@" in m:
        bad(f"{cfg} is named by instance {m} and is missing")
    # Modules without a config file use built-in defaults, which is fine.

print("[*] branding")
b = CONF / "branding" / settings["branding"]
desc = b / "branding.desc"
if not desc.exists():
    bad(f"no branding.desc for '{settings['branding']}'")
else:
    d = yaml.safe_load(desc.read_text())
    ok(f"branding.desc for {d.get('componentName')}")
    for key, name in (d.get("images") or {}).items():
        (ok if (b / name).exists() else bad)(f"images.{key} -> {name}")
    slideshow = d.get("slideshow")
    if slideshow:
        (ok if (b / slideshow).exists() else bad)(f"slideshow -> {slideshow}")

print()
if fail:
    print("FAILED: the Calamares configuration names something that is not there.")
    sys.exit(1)
print("The Calamares configuration is internally consistent. Whether the")
print("installer WORKS is a different question, and needs a person to run it.")
