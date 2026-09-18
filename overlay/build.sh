#!/usr/bin/env bash
# Build the FacetUI RRO overlays.
#
# Needs aapt2 and apksigner from the Android SDK, plus a signing key. Set:
#
#   ANDROID_JAR    a platform android.jar, e.g.
#                  $ANDROID_HOME/platforms/android-37/android.jar
#   KEYSTORE       a signing keystore
#   KEYSTORE_PASS  its password
#
# Validate the overlay sources first -- an overlay naming a resource its target
# does not define links and installs perfectly, then does nothing:
#
#   tools/validate-overlays.py --systemui <frameworks/base> \
#                              --launcher <Launcher3> --ime <LatinIME>
set -euo pipefail

: "${ANDROID_JAR:?set ANDROID_JAR to a platform android.jar (android-37 for Android 17)}"
: "${KEYSTORE:?set KEYSTORE to a signing keystore}"
: "${KEYSTORE_PASS:?set KEYSTORE_PASS to the keystore password}"

# cd first: OUT must resolve against this script's directory, not the caller's,
# or running it from the repo root silently writes output somewhere else.
cd "$(dirname "$0")"
OUT="${OUT:-$(pwd)/out}"
mkdir -p "$OUT"

for ov in FacetUISystemUI FacetUIFramework FacetUILauncher FacetUIIME; do
  echo "[*] $ov"
  aapt2 compile --dir "$ov/res" -o "$OUT/$ov-res.zip"
  aapt2 link -I "$ANDROID_JAR" \
        --manifest "$ov/AndroidManifest.xml" \
        -o "$OUT/$ov-unsigned.apk" "$OUT/$ov-res.zip"
  # Pass the password explicitly: apksigner otherwise blocks reading stdin,
  # which fails in any non-interactive context such as CI.
  apksigner sign --ks "$KEYSTORE" \
      --ks-pass "pass:$KEYSTORE_PASS" --key-pass "pass:$KEYSTORE_PASS" \
      --out "$OUT/$ov.apk" "$OUT/$ov-unsigned.apk"
  echo "    -> $OUT/$ov.apk"
done

cat <<'EOF'

Built. Inject into /system/product/overlay/ with the same SELinux labelling
inject-ime.sh applies, then confirm they took effect on the device:

    adb shell cmd overlay list | grep -i facetui
EOF
