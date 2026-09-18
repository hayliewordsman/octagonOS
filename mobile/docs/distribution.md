# Distributing a build

**Read this before publishing an image.** Most of what octagonOS ships is
Apache 2.0, but not all of it, and the parts that are not carry obligations
that attach the moment you hand someone a binary.

Nothing here is legal advice. It is the list of things to get right, and where
the traps are.

## What licence applies to what

| Part | Licence | Source |
|---|---|---|
| This repository | Apache 2.0 | [`../../LICENSE`](../../LICENSE) |
| AOSP, LineageOS | Apache 2.0 | upstream |
| **The Linux kernel** | **GPLv2** | the device's kernel source |
| Some device firmware | proprietary, redistribution often prohibited | the vendor |

The Apache 2.0 parts want attribution and a copy of the licence. The kernel
does not: **GPLv2 requires that you offer the corresponding source** to anyone
you give a binary to, for at least three years, and that offer has to be
written down somewhere they will see it.

## What a GSI changes about that

A GSI is a *system* image. It does not contain a kernel, so shipping one does
not by itself trigger the kernel's obligations. Shipping a **flashable
package**, a factory image, or anything that includes boot.img does.

That distinction is easy to lose once a release has an installer, so decide
which one you are publishing before you write the release notes.

## The trap worth naming

**Do not redistribute vendor blobs you have not been licensed to
redistribute.** A GSI does not normally contain them, which is much of why the
GSI route is attractive here — but an image assembled from a device dump can
pick them up without anyone intending it. If your build process involved
extracting anything from a stock device image, check what ended up in the
artefact before publishing it.

## Before a public release

- [ ] Publish or offer the kernel source for any package that includes a kernel
- [ ] Include the Apache 2.0 licence text and a NOTICE listing upstreams
- [ ] State clearly which upstream tags the build came from, so the source
      offer is actually actionable
- [ ] Confirm no proprietary blobs are in the artefact
- [ ] Say plainly that this is a beta, unbuilt and untested on hardware — see
      [status.md](status.md)

## Signing, and what a user can verify

The overlays and the icon pack in this repository are signed with a
**self-generated key**, which is enough for resources on a trusted partition
and is not a security claim. Two things follow.

**Publish the signing certificate's fingerprint** alongside releases, so
someone can check that an APK they have is one you built.

**Verified boot is a separate problem.** Locking a bootloader onto a custom
build needs an AVB key pair, the public key embedded where the bootloader can
find it, and a device whose bootloader supports it — many do not. Until that is
done, a device running octagonOS boots unlocked, and the lock screen protects
data at rest but nothing protects the boot chain. That is the honest state; do
not describe a build as secure on the strength of the ADB hardening alone.

See [status.md](status.md) for what is actually verified.
