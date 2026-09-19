# Building the octagonOS desktop ISO

Start to finish on your own machine. Roughly 45–70 minutes the first time,
most of it `debootstrap` and `mksquashfs`; about 12 minutes on a rebuild,
because the chroot is reused.

## What you need

- **Ubuntu 24.04 amd64**, or a VM/container of it. The build uses
  `debootstrap` and `chroot`, so it wants a Debian-family host and `sudo`.
  On macOS or Windows, run it inside an Ubuntu 24.04 VM.
- **~25 GB free**: a 5.5 GB chroot, a 1.3 GB squashfs and a 1.7 GB ISO,
  plus room to work. The chroot lives in `/var/tmp`, not the repo.
- An internet connection. The build pulls Ubuntu and KDE neon archives.

## 1. Get the source

```bash
git clone https://github.com/hayliewordsman/octagonOS.git
cd octagonOS
git checkout desktop
```

## 2. Add KDE neon, and install the packaging tools

Ubuntu 24.04 ships KWin 5.27. FacetUI's effect needs KWin 6, which comes
from KDE neon — Ubuntu 24.04 with Plasma 6 on top.

```bash
curl -fsSL https://archive.neon.kde.org/public.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/neon.gpg

echo "deb [signed-by=/usr/share/keyrings/neon.gpg] http://archive.neon.kde.org/user noble main" \
  | sudo tee /etc/apt/sources.list.d/neon.list

sudo apt-get update

sudo apt-get install -y --no-install-recommends \
  debhelper fakeroot lintian dpkg-dev cmake \
  kwin-dev extra-cmake-modules qt6-base-dev \
  libkf6coreaddons-dev libkf6config-dev kf6-ksvg-dev \
  kf6-kconfig \
  libegl1-mesa-dev libgles2-mesa-dev libgl1-mesa-dri \
  gtk-update-icon-cache breeze-icon-theme hicolor-icon-theme
```

> **Not `plasma-workspace`.** It is Plasma's *runtime*, nothing in this build
> uses it, and on a normal Ubuntu machine it cannot be installed alongside
> apport:
>
>     plasma-workspace -> drkonqi -> systemd-coredump
>
> `systemd-coredump` and Ubuntu's `apport-core-dump-handler` each *provide
> and conflict* the virtual package `core-dump-handler`, so only one of them
> can exist. apt will not quietly remove apport to make room, and gives up
> with `pkgProblemResolver::Resolve generated breaks`. The build never needed
> it: it is absent from `debian/Build-Depends`, and the test step is four
> Python verifiers. `plymouth` went for the same reason — the theme is
> generated and checked by a Python script, not by Plymouth.

> **This changes your machine.** It adds the neon archive and installs Plasma
> 6 development packages system-wide. On a machine you use as a KDE desktop,
> prefer a VM or container — neon packages can outrank Ubuntu's own.

## 3. Install the image-building tools

```bash
sudo apt-get install -y --no-install-recommends \
  debootstrap squashfs-tools xorriso mtools dosfstools \
  grub-common grub-pc-bin grub-efi-amd64-bin \
  python3-numpy python3-pil python3-cairosvg
```

`grub-pc-bin` and `grub-efi-amd64-bin` are both needed and neither is
optional: one supplies the BIOS boot image, the other the UEFI one, and an
image with only one of them boots on half the machines it is handed to.

The three `python3-*` packages come from apt rather than `pip`, because
Ubuntu 24.04 marks its Python as externally managed and `pip install numpy`
is refused. If you would rather use pip, make a virtualenv first.

## 4. Build the packages

```bash
desktop/packaging/build-debs.sh
```

Five `.deb`s land in `desktop/packaging/out/`. The artwork generators run
during this build, so a package cannot disagree with the source it came
from, and the static verifiers run as the build's test step.

## 5. Build the image

```bash
sudo desktop/iso/build-iso.sh --profile desktop
```

This is the long one. It debootstraps Ubuntu 24.04, installs Plasma on
Wayland and the FacetUI packages, sets FacetUI as the default for every new
user, squashes the filesystem and writes the ISO to
`desktop/iso/out/octagonos-desktop.iso`.

Re-running it reuses the chroot at `/var/tmp/octagonos-iso/chroot`, which is
what makes a rebuild minutes instead of an hour. To start clean:
`sudo rm -rf /var/tmp/octagonos-iso`.

## 6. Check the image

```bash
sudo desktop/tools/verify-iso.sh desktop/iso/out/octagonos-desktop.iso
```

Opens the image without booting it: both boot paths, the files that must be
present, and — by unpacking the filesystem and resolving the settings the
way a Plasma component would — whether FacetUI would actually be the
desktop's theme rather than merely installed. Exit status 0 means yes.

## 7. Boot it (optional, and the only step that proves anything runs)

```bash
sudo apt-get install -y --no-install-recommends qemu-system-x86 socat netpbm ovmf
sudo desktop/tools/boot-iso-check.sh desktop/iso/out/octagonos-desktop.iso
```

Boots the image and asks the running session, over its own D-Bus, whether
the compositor effect is loaded. On a machine with `/dev/kvm` this takes a
couple of minutes; without it, QEMU falls back to software emulation and it
takes considerably longer.

A pass looks like:

```
OK   render node: /dev/dri/renderD128
OK   compositing: gl2
OK   facetui-glass is loaded and running
INFO kwin blur loaded: true
```

Read `INFO kwin blur loaded:` before anything else. KWin's own blur is the
control. If FacetUI's effect is missing *and* blur is missing, the machine
has no working OpenGL and the result says nothing about FacetUI. If blur
loaded and FacetUI's did not, the problem is ours. See
[`evidence/`](evidence/).

## 7b. Test an install (optional, and slow)

```bash
sudo desktop/tools/test-install.sh desktop/iso/out/octagonos-desktop.iso
```

Two phases. It boots the ISO with a blank virtual disk and
`octagonos.autoinstall=/dev/vda`, which runs the terminal installer
unattended and powers off; then it boots **that disk**, with no ISO attached,
and asks KWin what is running on it. In between it checks the things a
hand-written install forgets -- that the live autologin, `casper.conf` and
the forced-OpenGL override are gone, and that a kernel is actually in
`/boot`.

The self-test is added back to the finished disk **from outside**, by the
harness, because the installer removes it from anything it installs. What
gets installed is what you would get; the instrumentation is visibly the
test's.

## 8. Installing it

The image ships two installers.

**Calamares**, the graphical one, is on the live desktop as *Install System*
and on the desktop of the live session. It asks for the live password
(`octagon`) through pkexec, because it needs root.

**`octagonos-install`**, from a terminal, for when the desktop does not come
up or you want it scripted:

```bash
sudo octagonos-install --disk /dev/sda
```

It asks for a username and password, shows you what it will erase, and makes
you type the disk path again before it touches anything. `--unattended` skips
all of that and is what the test uses.

Both remove the live-image configuration on the way out: the `octagon`
autologin, `casper`, and the test scaffolding. An installed system that still
logged itself in as `octagon` would be the bug.

### What is proven, and what is not

`octagonos-install` has been run end to end and the machine it produced was
booted and checked: see
[`evidence/installed-selftest-2026-09-19.log`](evidence/installed-selftest-2026-09-19.log).

**Calamares has not.** Its configuration is checked offline --
`desktop/tools/verify-calamares-config.py` confirms every module in the
sequence exists, every instance is declared and used, every config file
parses and the branding names images that are there -- but nobody has clicked
through it to a finished install. Driving a GUI to completion headlessly is a
much larger problem than running a script, and I would rather say that than
imply a wizard has been tested because a script has.

## 9. Write it to a USB stick

```bash
lsblk                      # find the stick. Get this wrong and you lose a disk.
sudo dd if=desktop/iso/out/octagonos-desktop.iso of=/dev/sdX bs=4M status=progress conv=fsync
```

`/dev/sdX` is the **whole device**, not a partition — `/dev/sdb`, not
`/dev/sdb1`. Check it twice: `dd` will overwrite whatever you name, without
asking, including your system disk.

The image is a hybrid ISO, so it boots from BIOS and UEFI alike, and it
carries `/EFI/BOOT/BOOTX64.EFI` as a real directory as well as inside the
embedded FAT image — which is what makes a stick prepared by *copying* the
files boot on UEFI, rather than only one made with `dd`.

## Checksums

A rebuild will **not** reproduce a previous build's checksum, because
squashfs and ISO9660 record timestamps. It does reproduce the same content:
the archives are pinned, including the neon snapshot `facetui-kwin-effect`
is compiled against.

The image built on 2026-09-19, the one whose boot is recorded in
[`evidence/`](evidence/), was:

```
fe4a822566e176a7420ad1b48b7d034c6857a72e2d70d05891105c6bc210c9e6  octagonos-desktop.iso
1771100160 bytes
```

## What has actually been tested

The build, verify and boot steps were all run end to end, repeatedly, on
Ubuntu 24.04 — that is where the image in `evidence/` came from.

The dependency lists in steps 2 and 3 are the ones CI installs from scratch
on a clean `ubuntu-24.04` runner, and every package name in step 3 was
confirmed to resolve with `apt-get --simulate` before being written here.
What has *not* been done is running this exact page top to bottom on a fresh
machine, so if step 2 or 3 turns out to want one more package on yours,
that is the likeliest place for it.
