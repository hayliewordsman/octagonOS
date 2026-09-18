#!/usr/bin/env bash
# Build and verify the octagonOS boot animation.
#
# Needs Python with Pillow and NumPy. No Android SDK, no device.
set -euo pipefail
cd "$(dirname "$0")"

OUT="${OUT:-out/bootanimation.zip}"

python3 make-bootanimation.py --out "$OUT" "$@"
python3 ../tools/verify-bootanimation.py "$OUT"

cat <<EOF

Install to /system/media/bootanimation.zip (or /oem/media/bootanimation.zip,
which the player checks second). Inside an image, inject it the same way the
overlays go in:

    --add-file $OUT:system/media/bootanimation.zip
EOF
