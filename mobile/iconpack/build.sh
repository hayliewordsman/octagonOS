#!/usr/bin/env bash
# Build the FacetUIIcons pack.
#
# Generation needs only Python (Pillow, NumPy). Packaging into an APK needs
# aapt2 and apksigner from the Android SDK:
#
#   ANDROID_JAR    a platform android.jar (android-37 for Android 17)
#   KEYSTORE       a signing keystore
#   KEYSTORE_PASS  its password
set -euo pipefail
cd "$(dirname "$0")"

# Always regenerate: res/ is output, and a stale tile or appfilter is not
# visible by inspection.
python3 make-icons.py

python3 ../tools/verify-iconpack.py FacetUIIcons

if [ "${SKIP_APK:-}" = "1" ]; then
    echo "[*] SKIP_APK set; stopping after generation"
    exit 0
fi

: "${ANDROID_JAR:?set ANDROID_JAR to a platform android.jar (android-37 for Android 17)}"
: "${KEYSTORE:?set KEYSTORE to a signing keystore}"
: "${KEYSTORE_PASS:?set KEYSTORE_PASS to the keystore password}"

OUT="${OUT:-$(pwd)/out}"
mkdir -p "$OUT"

echo "[*] FacetUIIcons"
aapt2 compile --dir FacetUIIcons/res -o "$OUT/FacetUIIcons-res.zip"
aapt2 link -I "$ANDROID_JAR" \
      --manifest FacetUIIcons/AndroidManifest.xml \
      -o "$OUT/FacetUIIcons-unsigned.apk" "$OUT/FacetUIIcons-res.zip"
apksigner sign --ks "$KEYSTORE" \
      --ks-pass "pass:$KEYSTORE_PASS" --key-pass "pass:$KEYSTORE_PASS" \
      --out "$OUT/FacetUIIcons.apk" "$OUT/FacetUIIcons-unsigned.apk"
echo "    -> $OUT/FacetUIIcons.apk"
# The intermediates only confuse a listing, and apksigner correctly
# reports an unsigned APK as not verifying, which reads like a failure.
rm -f "$OUT/FacetUIIcons-unsigned.apk" "$OUT/FacetUIIcons-res.zip"

cat <<'EOF'

Install to /system/app/FacetUIIcons/ or /product/app/FacetUIIcons/. The engine
finds it by package name; nothing needs to be selected by the user.
EOF
