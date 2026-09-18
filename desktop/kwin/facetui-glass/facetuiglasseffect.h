/*
    SPDX-FileCopyrightText: 2026 The octagonOS Project
    SPDX-License-Identifier: Apache-2.0
*/

#pragma once

#include "effect/offscreeneffect.h"

#include <QLoggingCategory>

#include <QSet>
#include <memory>

Q_DECLARE_LOGGING_CATEGORY(KWIN_FACETUI_GLASS)

namespace KWin
{

class GLShader;

/**
 * FacetUI glass, for KWin.
 *
 * Applies the two FacetUI shaders -- the specular edge and the rim darkening --
 * to the system's own surfaces, so a panel, a menu or a dialog reads as a lit
 * pane of glass rather than a translucent grey rectangle.
 *
 * WHAT THIS DOES NOT DO
 *
 * It does not blur. KWin's own blur effect does that, and FacetUI's depth model
 * is expressed there and in the Plasma theme. This effect supplies the other
 * two thirds of the rule -- the specular edge and the rim -- which nothing in
 * Plasma provides, and which is what separates glass from translucency.
 *
 * WHICH WINDOWS
 *
 * System surfaces only: docks, menus, dialogs, tooltips, notifications and
 * on-screen displays. NOT normal application windows, and not the desktop.
 *
 * That is not a conservatism, it is the doctrine: a compositor can only work on
 * what it composites, which is a window. An application's toolbars, cards and
 * list backgrounds are drawn inside its window and are the application's to
 * style. Treating a whole app window as one glass pane would put a rim down the
 * middle of its content.
 */
class FacetUIGlassEffect : public OffscreenEffect
{
    Q_OBJECT

public:
    FacetUIGlassEffect();
    ~FacetUIGlassEffect() override;

    static bool supported();

    // Returns void, not bool. KWin's master branch changed this to bool after
    // 6.7; targeting the release means matching the release. Reading the wrong
    // branch's header is how this was written wrong the first time, and only
    // the compiler said so.
    void drawWindow(const RenderTarget &renderTarget, const RenderViewport &viewport,
                    EffectWindow *window, int mask, const Region &region,
                    WindowPaintData &data) override;

    bool isActive() const override;

    /**
     * Runs after KWin's blur effect, which asks for position 20.
     *
     * Effects are ordered by this number and chained: one at a lower position
     * is entered FIRST and calls down to the rest, so blur paints the blurred
     * backdrop and then everything above 20 draws the window over it. That
     * ordering is the whole point here -- blur alone reads as frosted plastic,
     * and the specular edge only reads as glass when it sits on top of the
     * blur rather than under it.
     */
    int requestedEffectChainPosition() const override
    {
        return 60;
    }

private Q_SLOTS:
    void slotWindowAdded(EffectWindow *window);
    void slotWindowDeleted(EffectWindow *window);

private:
    /** The FacetUI depth tiers, as they land on a desktop. */
    enum class Tier {
        None,   ///< not a glass surface: application windows, the desktop
        L2,     ///< menus, dialogs, tooltips, combo boxes -- small floating panels
        L3,     ///< notifications and on-screen displays
        L4,     ///< the panel; the deepest layer, and the only lit one
    };

    static Tier tierFor(const EffectWindow *window);
    void considerWindow(EffectWindow *window);

    std::unique_ptr<GLShader> m_shader;
    QSet<EffectWindow *> m_windows;
};

} // namespace KWin
