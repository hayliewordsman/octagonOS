# The octagonOS live image

```sh
sudo desktop/iso/build-iso.sh                     # -> desktop/iso/out/octagonos-desktop.iso
desktop/tools/verify-iso.sh   desktop/iso/out/octagonos-desktop.iso
sudo desktop/tools/boot-iso-check.sh desktop/iso/out/octagonos-desktop.iso
```

Three steps, and they answer different questions: the image builds, the image
contains what it should, and **the image works when booted**. Only the last one
can settle whether FacetUI is visible.

## The base, and why it is pinned

Ubuntu 24.04's archive ships **KWin 5.27**. Everything the desktop edition
needs is KWin 6, which comes from **KDE neon** — the same Ubuntu 24.04 with
Plasma 6 on top. So the base is Ubuntu plus a **pinned** neon snapshot, not neon
tracked live.

That is not caution. `facetui-kwin-effect` is compiled against exactly one KWin,
because KWin's effect API is not binary compatible across versions — letting the
archive move under it is how the effect silently stops loading after an update.
`dh_shlibdeps` already encodes the constraint in the package; the pin keeps the
archive from fighting it.

## Why not livecd-rootfs or live-build

`livecd-rootfs` is what Ubuntu's own flavours use and it really wants Launchpad.
`live-build` carries a lot of configuration that exists mostly to be overridden.
The script here is `debootstrap`, a chroot, `mksquashfs` and `xorriso` — which
is what both of those do underneath — written out, so every step is visible and
the image can be rebuilt anywhere with those four tools.

## Profiles

| | |
|---|---|
| `desktop` | the real image: Plasma on Wayland, FacetUI as its theme |
| `minimal` | the same pipeline without Plasma — minutes instead of an hour |

`minimal` proves the pipeline, not the product. It cannot show the compositor
effect, which is the thing the image exists to prove, so `verify-iso.sh` refuses
to call it a pass unless you pass `--profile minimal` and say you meant it.

## The self-test is part of the image

`octagonos-selftest.service` is gated on `ConditionKernelCommandLine=octagonos.selftest`,
so it ships without running. It reports over the serial console: whether there
is a DRM render node, what KWin is compositing with, whether `facetui-glass` is
loaded, whether KWin's *own* blur is loaded — as a control — and whether the
session's theme settings are FacetUI's.

It is in the image rather than injected by the harness on purpose: someone
whose machine looks wrong can boot with the same flag and get the same answers.

## What the boot check proves that nothing else could

Without a DRM render node KWin falls back to its QPainter scene, where every
OpenGL effect — **including KWin's own blur** — reports itself unsupported and
is never loaded. That is the state of the container this was developed in, and
it is why the effect has been "builds, loads, and is accepted by KWin" rather
than "works".

A QEMU guest with `virtio-vga` has a render node. `boot-iso-check.sh` pulls the
kernel and initrd out of the ISO and boots them directly — only so the command
line can carry `octagonos.selftest`, since the image's GRUB menu has no entry
for it and should not — then reads the guest's serial output and takes a
screenshot through QEMU's monitor, which needs no cooperation from the guest at
all.

KVM is used when `/dev/kvm` exists and TCG when it does not. TCG is slow; the
effect does not care how long a frame took.

## The control line matters most

`INFO kwin blur loaded:` is not decoration. If FacetUI's effect is absent *and*
KWin's blur is absent, the machine has no OpenGL and the result says nothing
about FacetUI. If blur is loaded and FacetUI's is not, the problem is ours.
Distinguishing those two is the difference between a bug and a wasted day.
