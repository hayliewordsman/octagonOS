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
    FacetUIIME

# --- boot animation ---------------------------------------------------------
PRODUCT_COPY_FILES += \
    vendor/octagonos/bootanimation/out/bootanimation.zip:$(TARGET_COPY_OUT_SYSTEM)/media/bootanimation.zip

# --- form-factor setup ------------------------------------------------------
# One GSI serves both physical-keyboard phones and slabs; which one it is gets
# resolved on first boot. See product/octagonos/bin/octagonos-formfactor.sh.
PRODUCT_COPY_FILES += \
    vendor/octagonos/product/octagonos/bin/octagonos-formfactor.sh:$(TARGET_COPY_OUT_SYSTEM)/bin/octagonos-formfactor.sh \
    vendor/octagonos/product/octagonos/etc/init/octagonos-formfactor.rc:$(TARGET_COPY_OUT_SYSTEM)/etc/init/octagonos-formfactor.rc

# --- hardening --------------------------------------------------------------
# GSIs commonly ship ro.adb.secure=0, which disables ADB authorisation
# outright: any USB host attaches without a prompt. A beta people will actually
# carry should not.
PRODUCT_SYSTEM_PROPERTIES += \
    ro.adb.secure=1 \
    ro.debuggable=0
