# octagonOS desktop — beta 2

A live image of octagonOS's desktop edition: **Plasma 6 on Wayland, themed
throughout by FacetUI**. Ubuntu 24.04 as the base, with a pinned KDE neon
snapshot for KWin 6.

**Beta 1 could not be installed.** This one can.

## What's new

**Two installers.** [Calamares](https://calamares.io) is the graphical one —
*Install System*, on the live desktop and in the application menu. There is
also `octagonos-install`, a terminal installer, for when the desktop does not
come up on unfamiliar graphics, which is exactly when you still want to
install.

**An installed machine has been booted and checked.** Not just "the installer
ran": a virtual disk was installed to, then booted on its own bootloader with
no image attached, and KWin was asked what it was running. It answered
`facetui-glass is loaded and running`.

**The image now contains a kernel.** Beta 1's filesystem excluded `/boot`,
since the live image boots from the ISO's own copy. Anything installed from
it would have had no kernel: the install would report success, GRUB would
write a menu with nothing in it, and the machine would not boot. This is the
single most important fix in this release, and it is the reason the image
grew from 1.7G to 1.8G.

## Changelog since beta 1

### Added
- Calamares, with an octagonOS module sequence, sixteen module configs and
  branding. No `calamares-settings` package exists for this distribution, so
  all of it is written from scratch. Its logo is generated from the same
  renderer as the boot splash and the icon theme, so the installer's octagon
  cannot drift from everything else's.
- `octagonos-install`, a terminal installer: partitions, copies the system
  from the squashfs, writes fstab, installs GRUB for UEFI or BIOS, removes
  the live-image configuration and creates a real user. `--unattended` makes
  it scriptable.
- GRUB, and the partitioning and filesystem tools, inside the image. An
  installer that needs the network to make a disk bootable fails on the
  machine that most needs installing.
- `test-install.sh`: installs to a virtual disk, then boots that disk and
  asks KWin what is running on it.
- `verify-calamares-config.py`, which checks the installer configuration
  names modules, files and images that exist.

### Fixed
- **`/boot` was excluded from the filesystem**, so nothing installed from
  beta 1 could boot.
- **The unattended installer died silently** under systemd, always at the
  same point. Its output went straight to the serial console; when a write
  there failed, `echo` returned non-zero, `set -e` ended the script, and the
  message explaining it could not be printed because printing was what had
  failed. It now traces to a file and replays it.
- The installer reports the line and command when it exits, rather than
  stopping without a word.
- systemd's 90-second start timeout would have killed an unattended install
  partway through copying.
- `plasma-workspace` was in the documented build dependencies and cannot be
  installed on an ordinary Ubuntu machine: it pulls `drkonqi`, which requires
  `systemd-coredump`, which conflicts with the `apport` every Ubuntu install
  has. It was never needed to build anything.

### Changed
- The live user is `octagon` for casper too, so the live session and the
  autologin agree on one account instead of creating two at the same uid.

## Read this before you boot it

**It logs in automatically** as `octagon`, password `octagon`. That is a
published default on a published image; treat any live session as untrusted
accordingly. Installing removes that account unless you choose to keep it.

**It is a beta.** The compositor effect has been seen running on a booted
machine, twice — live, and installed. It has not been through sustained use
on varied hardware.

## Installing

Boot the image, then either:

- **Graphical:** open *Install System*. It asks for the live password
  (`octagon`) to get root.
- **Terminal:** `sudo octagonos-install --disk /dev/sda`. It asks for a
  username and password, shows what it will erase, and makes you type the
  disk path again before touching anything.

Both remove the live configuration on the way out — the `octagon` autologin,
`casper`, and the test scaffolding. A machine that still logged itself in as
`octagon` after being installed would be the bug.

## What is verified, and what is not

On a booted machine — both from the live image and from an installed disk —
KWin reported:

```
OK   render node: /dev/dri/renderD128
OK   compositing: gl2
OK   facetui-glass is loaded and running
INFO kwin blur loaded: true
```

That last line is the control, and it is what makes the one above it mean
anything: KWin's own blur is an OpenGL effect maintained by people with no
stake in this project. Had it failed to load too, the FacetUI line would say
nothing about FacetUI and everything about the machine.

**Three things that did not prove.**

*The test machine had no GPU*, so OpenGL compositing had to be forced — Mesa's
software rasteriser tells KWin not to use OpenGL, and KWin then loads no
OpenGL effect at all. Every frame was drawn by the CPU. Nothing here is a
claim about performance on real hardware.

*It proves the effect runs, not that the glass looks right.* The host could
not photograph the guest's Wayland output. Appearance is checked offline
instead — the shader against NumPy, the Plasma surfaces rendered and
measured.

*Calamares has not been run to completion by anybody.* Its configuration is
checked offline, which catches the failure where a typo means the installer
does not start at all. It does not tell you the installer works. If you
install with it, that is the first time it has been done, and reports are
welcome.

## Known limitations

- **No UEFI install has been tested.** The installer detects firmware and
  writes an EFI bootloader when it finds one, but the automated test runs in
  BIOS mode. UEFI is the code path most machines will take and it is the
  least exercised.
- **The terminal installer in this image lacks its live-session guard.** It
  refuses to run anywhere that does not look like a live session — but that
  check landed one commit after this image was built. Since the installer
  stays on installed systems, running `octagonos-install` on a machine
  installed from beta 2 will repartition whatever disk you name it, without
  the refusal a later image gives you. Treat it as the destructive command it
  is.
- No disk encryption, no OEM mode, no upgrade path from beta 1.

## Building it yourself

The image is not reproducible byte for byte — squashfs and ISO9660 record
timestamps — but it is reproducible in content: the archives are pinned,
including the neon snapshot `facetui-kwin-effect` is compiled against. See
[`desktop/iso/BUILDING.md`](desktop/iso/BUILDING.md).
