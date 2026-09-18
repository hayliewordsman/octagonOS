# Packaging FacetUI

One Debian source package, five binaries. Four of them carry an artifact; the
fifth makes them the desktop's defaults rather than its options.

```sh
desktop/packaging/build-debs.sh          # -> desktop/packaging/out/*.deb
sudo dpkg -i desktop/packaging/out/*.deb
desktop/tools/check-facetui-defaults.sh  # did it actually take effect?
```

| Package | Contents |
|---|---|
| `facetui-kwin-effect` | the glass effect plugin — **compiled** |
| `facetui-plasma-style` | the Plasma style, and the colour scheme |
| `facetui-icon-theme` | the icon theme |
| `facetui-plymouth-theme` | the boot splash, plus the alternative and initramfs rebuild |
| `octagonos-facetui` | `/etc/xdg` defaults and the Global Theme entry; depends on the other four |

## Installed is not in use

Every piece of FacetUI can be present and correct while the desktop draws
Breeze. Plasma reads its settings from `kdeglobals` and `plasmarc`, and nothing
puts them there just because a package landed.

**Naming a look-and-feel package does not apply its contents.** Those are
written out only when somebody selects the theme in System Settings. Tested
directly: with only `LookAndFeelPackage` set, the icon theme read back
`<unset>`. So `octagonos-facetui` ships the individual keys as system
configuration, and the look-and-feel package alongside them — deliberately
redundant. The first makes FacetUI the default; the second makes it something a
user can come back to after changing one of the pieces.

These are *defaults*, not locks: a user's own `~/.config` still wins. On a fresh
install or a live session every user is new, so every user gets them.

`desktop/tools/check-facetui-defaults.sh` resolves each setting the way a Plasma
component would — through the XDG cascade, as a user with an empty home
directory — and checks that the resources those settings name are actually
installed. It takes `--root` so the same check runs against an image's chroot
before it is ever booted.

## The effect is the only thing that compiles, and that matters

KWin's effect API is **not binary compatible** across versions; its own header
says so. `dh_shlibdeps` turns that into a real constraint automatically — the
built package came out with:

```
Depends: kwin-common (>= 4:6.7.5), kf6-kcoreaddons (>= 6.30.0), qt6-base (>= 6.11.1)
```

So the package manager refuses to install it against a KWin it was not built
for. That is the right outcome, and it is the reason the effect is built in the
image pipeline rather than shipped as a prebuilt binary.

## Why a staging tree

Debian builds from the root of a source tree, and this repository's root is two
products. `build-debs.sh` stages the desktop edition and the shared FacetUI core
into one directory with `debian/` on top. A `debian/` at the repository root
would claim the Android half is part of this source package, which it is not.

The staged tree **mirrors the repository** rather than flattening it: every
generator and verifier resolves `shared/` as its own directory's grandparent, so
dropping the `desktop/` level puts `shared/` one directory too high and the
first generator fails. The script asserts that layout before building rather
than hoping for it.

## What runs during the build

The generators run in `override_dh_auto_configure`, so a `.deb` cannot disagree
with the source it was built from. The static verifiers run as the build's test
step: a package that installs a theme its own verifier rejects is worse than a
build failure, because it reaches a machine.

One check stands down there on purpose. `validate-kwin-shaders.py` compares the
GLSL against the Android AGSL, which a source package of the desktop edition
does not carry — so it prints a `[skip]` naming the reason rather than crashing
on a missing file or, worse, passing quietly with nothing to compare. It runs in
full on the repository, which is where cross-platform drift can happen.

## Notes

- `/etc/xdg/kdeglobals`, `kwinrc` and `plasmarc` are unowned on Ubuntu + neon —
  checked with `dpkg -S`. On a Kubuntu base, `kubuntu-settings-desktop` owns
  them and this would need a `Conflicts`/`Replaces` or a higher-priority
  `XDG_CONFIG_DIRS` drop-in.
- The Plymouth postinst rebuilds the initramfs, because Plymouth runs from
  there and a theme only in `/usr/share` changes nothing about the next boot.
  Where no initramfs tool exists it warns loudly instead of failing silently.
