#!/bin/sh
#
# Force KWin to composite with OpenGL, for test machines with no GPU.
#
# WHY THIS IS NEEDED, AND WHY IT IS NOT THE DEFAULT
#
# KWin asks the driver whether it recommends OpenGL compositing. Mesa's
# software rasteriser (llvmpipe) says no -- reasonably, since every frame is
# drawn by the CPU -- and KWin honours that by using its QPainter scene. In
# the QPainter scene no OpenGL effect is loaded at all: not facetui-glass, and
# not KWin's own blur. A virtual machine without virgl is exactly that case,
# so the acceptance test would be permanently unable to reach the thing it
# exists to test.
#
# KWIN_COMPOSE=O2ES overrides the recommendation. What that buys is real: the
# effect is compiled by Mesa's GLSL compiler, loaded into a real KWin OpenGL
# scene and run over real windows. What it does not buy is any claim about a
# GPU -- the pixels here are drawn by the CPU.
#
# It is deliberately NOT the image's default. Overriding a driver that says
# "do not use OpenGL" is right for a test and wrong for a user, whose driver
# may be saying it for a reason this script cannot see. It happens only when
# octagonos.forcegl is on the kernel command line.
#
# /etc/environment is the mechanism because pam_env reads it for every login
# session, including SDDM's autologin, so the variable reaches the session
# KWin is started in.

set -eu

grep -qw octagonos.forcegl /proc/cmdline || exit 0

if ! grep -q '^KWIN_COMPOSE=' /etc/environment 2>/dev/null; then
    echo 'KWIN_COMPOSE=O2ES' >> /etc/environment
fi
