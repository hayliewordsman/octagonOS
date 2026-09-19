# octagonOS desktop — beta 1

A live image of octagonOS's desktop edition: **Plasma 6 on Wayland, themed
throughout by FacetUI**. Ubuntu 24.04 as the base, with a pinned KDE neon
snapshot for KWin 6.

## What's in it

- **`facetui-glass`**, a KWin effect that draws FacetUI's rim darkening and
  specular edge on composited surfaces. It is the same maths as the Android
  edition's AGSL shaders — one renderer, checked against NumPy to 1.7e-07.
- **A Plasma style and colour scheme**, so panels, dialogs and popups carry
  the translucency and hairline the effect's light needs. Blur, translucency
  and a boundary have to be true together; any one missing wastes the others.
- **An icon theme** — 124 names across 8 sizes, each a glass octagon.
- **A Plymouth boot splash** carrying the octagonOS mark, including the
  encrypted-disk passphrase prompt.

FacetUI is the **default**, not an option: a user with an empty home
directory gets it without choosing anything.

## Read this before you boot it

**There is no installer.** This is a live image only — no Ubiquity, no
Calamares. It runs from the USB stick or in a VM and installs nothing. If you
want it on disk, that is not yet a thing this image does.

**It logs in automatically** as `octagon`, password `octagon`. That is a
published default on a live image, which is normal for one, but treat any
session you start as untrusted accordingly.

**It is a beta.** The compositor effect has been seen loading and running in
a booted session; it has not been through sustained use on varied hardware.

## Writing it to a USB stick

```bash
lsblk    # find the stick. Get this wrong and you lose a disk.
sudo dd if=octagonos-desktop.iso of=/dev/sdX bs=4M status=progress conv=fsync
```

`/dev/sdX` is the **whole device** (`/dev/sdb`, not `/dev/sdb1`). `dd`
overwrites whatever you name it, without asking.

It is a hybrid image: it boots under BIOS and UEFI, and it carries
`/EFI/BOOT/BOOTX64.EFI` as a real directory as well as inside the embedded
FAT image — so a stick prepared by *copying* the files boots on UEFI too,
not only one made with `dd`.

## What has been verified, and what has not

On a booted machine, KWin itself reported:

```
OK   render node: /dev/dri/renderD128
OK   compositing: gl2
OK   facetui-glass is loaded and running
INFO kwin blur loaded: true
```

That last line is the control, and it is why the one above it means
anything: KWin's own blur is an OpenGL effect maintained by people with no
stake in this project. If it had failed to load too, the FacetUI line would
say nothing about FacetUI and everything about the machine.

**Two things that run did not prove.** The test machine had no GPU, so
OpenGL compositing had to be *forced* — Mesa's software rasteriser tells KWin
not to use OpenGL, and KWin then loads no OpenGL effect at all. Every frame
was drawn by the CPU, so nothing there is a claim about performance on real
hardware. And it proves the effect **runs**, not that the glass **looks
right**: the host could not photograph the guest's Wayland output, so no
picture was taken. Appearance is checked offline instead — the shader against
NumPy, and the Plasma surfaces rendered by KSvg and measured.

If you boot this on a real GPU, you should see `compositing: gl2` without
anything being forced. That is a stronger result than the one above, and it
has not been recorded yet.

## Checksum

```
PASTE_SHA256_HERE  octagonos-desktop.iso
```

A rebuild will not reproduce this checksum — squashfs and ISO9660 record
timestamps — but it reproduces the same content, because the archives are
pinned, including the neon snapshot `facetui-kwin-effect` is compiled
against. Build it yourself with
[`desktop/iso/BUILDING.md`](desktop/iso/BUILDING.md).
