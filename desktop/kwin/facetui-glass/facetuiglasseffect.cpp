/*
    SPDX-FileCopyrightText: 2026 The octagonOS Project
    SPDX-License-Identifier: Apache-2.0
*/

#include "facetuiglasseffect.h"

#include "core/renderviewport.h"
#include "effect/effecthandler.h"
#include "effect/effectwindow.h"
#include "opengl/glshader.h"
#include "opengl/glshadermanager.h"

#include <QVector2D>
#include <QVector3D>

Q_LOGGING_CATEGORY(KWIN_FACETUI_GLASS, "kwin_effect_facetui_glass", QtWarningMsg)

namespace KWin
{

/*
 * The FacetUI constants, as the Android edition ships them.
 *
 * These mirror ScrimView.java in mobile/patches/systemui: 12dp of edge
 * falloff, a peak highlight of 0.5, a 48dp rim band and 0.35 of darkening at
 * it. They are in logical pixels here and scaled to device pixels at paint
 * time, because a dp and a logical pixel are the same idea wearing different
 * names.
 */
static constexpr float s_edgeThickness = 12.0f;
static constexpr float s_edgeIntensity = 0.5f;
static constexpr float s_rimWidth = 48.0f;
static constexpr float s_rimAmount = 0.35f;

/*
 * The highlight colour. Near-white with a cool cast, matching the Android
 * shaders' default tint, so a lit edge reads as light rather than as a colour.
 */
static constexpr float s_tint[3] = {0.92f, 0.96f, 1.0f};

FacetUIGlassEffect::FacetUIGlassEffect()
    : OffscreenEffect()
{
    m_shader = ShaderManager::instance()->generateShaderFromFile(
        // MapTexture for the window texture. RoundedCorners is asked for NOT
        // to round any corners -- this effect supplies its own fragment shader
        // and never runs KWin's -- but because it is what makes KWin's
        // base.vert emit the `position0` varying. The shader needs a
        // window-relative position, and texture coordinates cannot supply one:
        // KWin runs them through the offscreen texture's matrix, so they are a
        // position in texture space and may be flipped.
        ShaderTrait::MapTexture | ShaderTrait::RoundedCorners,
        QString(),
        QStringLiteral(":/effects/facetui-glass/shaders/facetui-glass.frag"));

    if (!m_shader) {
        // Loud, deliberately. A shader that fails to compile leaves an effect
        // that loads, reports itself supported, and does nothing at all -- the
        // hardest kind of failure to notice, because everything looks fine.
        qCCritical(KWIN_FACETUI_GLASS,
                   "FacetUI: the glass shader failed to build; the effect is "
                   "loaded but will not draw anything");
        return;
    }
    qCInfo(KWIN_FACETUI_GLASS, "FacetUI: glass shader built");

    ShaderBinder binder{m_shader.get()};
    m_shader->setUniform("facet_tint", QVector3D(s_tint[0], s_tint[1], s_tint[2]));
    // KWin sets `modulation` only for shaders that asked for the Modulate
    // trait. This one does its own modulation so it can run the FacetUI maths
    // on the surface's own values first, which is where the AGSL runs, so the
    // uniform needs a sane value for the frames before drawWindow sets it.
    m_shader->setUniform("modulation", QVector4D(1.0f, 1.0f, 1.0f, 1.0f));

    const auto windows = effects->stackingOrder();
    for (EffectWindow *window : windows) {
        considerWindow(window);
    }

    connect(effects, &EffectsHandler::windowAdded, this, &FacetUIGlassEffect::slotWindowAdded);
    connect(effects, &EffectsHandler::windowDeleted, this, &FacetUIGlassEffect::slotWindowDeleted);
}

FacetUIGlassEffect::~FacetUIGlassEffect() = default;

bool FacetUIGlassEffect::supported()
{
    return effects->isOpenGLCompositing() && OffscreenEffect::supported();
}

FacetUIGlassEffect::Tier FacetUIGlassEffect::tierFor(const EffectWindow *window)
{
    // The order matters: a window can answer yes to more than one of these,
    // and the first match wins. Docks are tested first because the panel is
    // the deepest surface and the only lit one.
    if (window->isDock()) {
        return Tier::L4;
    }
    if (window->isNotification() || window->isCriticalNotification()
        || window->isOnScreenDisplay()) {
        return Tier::L3;
    }
    if (window->isDialog() || window->isMenu() || window->isDropdownMenu()
        || window->isPopupMenu() || window->isTooltip() || window->isComboBox()
        || window->isUtility()) {
        return Tier::L2;
    }
    // Everything else -- normal application windows, the desktop -- is opaque
    // content, and is not ours to touch.
    return Tier::None;
}

void FacetUIGlassEffect::considerWindow(EffectWindow *window)
{
    if (!m_shader || m_windows.contains(window)) {
        return;
    }
    if (tierFor(window) == Tier::None) {
        return;
    }
    redirect(window);
    setShader(window, m_shader.get());
    m_windows.insert(window);
}

void FacetUIGlassEffect::slotWindowAdded(EffectWindow *window)
{
    considerWindow(window);
}

void FacetUIGlassEffect::slotWindowDeleted(EffectWindow *window)
{
    m_windows.remove(window);
}

void FacetUIGlassEffect::drawWindow(const RenderTarget &renderTarget,
                                    const RenderViewport &viewport,
                                    EffectWindow *window, int mask,
                                    const Region &region, WindowPaintData &data)
{
    if (m_shader && m_windows.contains(window)) {
        const Tier tier = tierFor(window);

        // Device pixels, not logical ones. KWin scales the quad's vertices by
        // the viewport scale before they reach the shader, so `position0`
        // arrives in device pixels; a size in logical pixels would halve the
        // effect on a 2x display and look like a tuning problem.
        const qreal scale = viewport.scale();
        const QSizeF size = window->frameGeometry().size() * scale;

        // The specular edge goes on the panel and nothing else.
        //
        // This mirrors the Android edition exactly, where the highlight is
        // drawn by ScrimView and therefore lands on the notification shade's
        // scrim alone. Lighting every panel was tried there, in the offline
        // render, and put a white bar across the top of every notification.
        // A render that overstates an effect is worse than none, because it
        // invites tuning a number that was never the problem.
        const float intensity = (tier == Tier::L4) ? s_edgeIntensity : 0.0f;

        ShaderBinder binder{m_shader.get()};
        m_shader->setUniform("facet_size",
                             QVector2D(float(size.width()), float(size.height())));
        m_shader->setUniform("facet_thickness", float(s_edgeThickness * scale));
        m_shader->setUniform("facet_intensity", intensity);
        m_shader->setUniform("facet_rim", float(s_rimWidth * scale));
        m_shader->setUniform("facet_amount", s_rimAmount);

        // KWin applies opacity and brightness through `modulation` for shaders
        // that asked for the Modulate trait. This one did not, so it carries
        // the same values itself -- see OffscreenData::paint, which is where
        // these two come from.
        const float rgb = float(data.brightness() * data.opacity());
        const float a = float(data.opacity());
        m_shader->setUniform("modulation", QVector4D(rgb, rgb, rgb, a));
    }

    OffscreenEffect::drawWindow(renderTarget, viewport, window, mask, region, data);
}

bool FacetUIGlassEffect::isActive() const
{
    return m_shader && !m_windows.isEmpty();
}

} // namespace KWin
