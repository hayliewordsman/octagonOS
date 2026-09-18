#
# octagonOS product definitions.
#
# Include from a GSI target so a source build carries the same pieces the
# image-injection path adds to a prebuilt:
#
#     $(call inherit-product, vendor/octagonos/product/octagonos/octagonos.mk)
#
# This is the Tier 3 path. The Tier 2 path -- injecting into a prebuilt GSI --
# needs none of this; see docs/building.md.

PRODUCT_NAME_OCTAGONOS := octagonOS

# --- branding ---------------------------------------------------------------
# No spaces in either name: octagonOS and FacetUI are single tokens everywhere
# they appear, including here.
PRODUCT_PRODUCT_PROPERTIES += \
    ro.octagonos.version=1.0-beta \
    ro.octagonos.ui=FacetUI \
    ro.octagonos.build.type=beta

# --- the blur gate ----------------------------------------------------------
# Without this SurfaceFlinger performs no cross-window blur at all and the
# whole glass design collapses to flat translucency. It is a property, not a
# resource, so no overlay can deliver it.
#
# surfaceflinger ships inside the GSI, so this is the system image's call to
# make. What the device still controls is the GPU driver: setting this makes
# SurfaceFlinger attempt blur, and whether it renders at an acceptable cost is
# a performance question to measure per device, not a permission the device
# grants.
PRODUCT_VENDOR_PROPERTIES += \
    ro.surface_flinger.supports_background_blur=1

# --- FacetUI overlays -------------------------------------------------------
PRODUCT_PACKAGES += \
    FacetUISystemUI \
    FacetUIFramework \
    FacetUILauncher \
    FacetUIIME \
    FacetUISettings \
    FacetUIDocumentsUI \
    FacetUIEtar \
    FacetUIDeskClock

# --- FacetUI icons ----------------------------------------------------------
# The curated icon pack. Not an overlay: an RRO can only override resources a
# target already defines and cannot add new ones, and every drawable in here is
# new.
#
# The icon engine in patches/iconloader/0001 also loads its glass tile out of
# this package, so with the pack absent every icon is left stock. It is a hard
# dependency of the icon theming, not an optional extra.
PRODUCT_PACKAGES += \
    FacetUIIcons

# --- boot animation ---------------------------------------------------------
PRODUCT_COPY_FILES += \
    vendor/octagonos/mobile/bootanimation/out/bootanimation.zip:$(TARGET_COPY_OUT_SYSTEM)/media/bootanimation.zip

# --- overlay enablement -----------------------------------------------------
# Enables the FacetUI overlays declaratively, before the first frame, with no
# runtime command and therefore no SELinux policy. This replaced a first-boot
# service that called `cmd overlay enable`; see the note at the top of
# mobile/tools/octagonos-formfactor.sh for why that service no longer exists.
#
# It also settles whether the overlays come up enabled at all, which
# `android:isStatic` being deprecated had left unverified.
PRODUCT_COPY_FILES += \
    vendor/octagonos/mobile/product/octagonos/overlay/config/config.xml:$(TARGET_COPY_OUT_PRODUCT)/overlay/config/config.xml

# --- hardening --------------------------------------------------------------
# GSIs commonly ship ro.adb.secure=0, which disables ADB authorisation
# outright: any USB host attaches without a prompt. A beta people will actually
# carry should not.
PRODUCT_SYSTEM_PROPERTIES += \
    ro.adb.secure=1 \
    ro.debuggable=0
