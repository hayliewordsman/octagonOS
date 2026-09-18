/*
    SPDX-FileCopyrightText: 2026 The octagonOS Project
    SPDX-License-Identifier: Apache-2.0
*/

#include "facetuiglasseffect.h"

namespace KWin
{

KWIN_EFFECT_FACTORY_SUPPORTED(FacetUIGlassEffect,
                              "metadata.json",
                              return FacetUIGlassEffect::supported();)

} // namespace KWin

#include "main.moc"
