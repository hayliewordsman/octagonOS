#version 140
// SPDX-FileCopyrightText: 2026 The octagonOS Project
// SPDX-License-Identifier: Apache-2.0
//
// FacetUI glass, for KWin.
//
// The two FacetUI shaders, transcribed from the AGSL that ships on the Android
// edition -- FacetEdgeShader.kt and FacetRimShader.kt in
// mobile/patches/systemui -- and evaluated in one pass over the window
// texture. The same two functions live in shared/facetui/facet_math.py as
// NumPy, which is what the boot animation and the icon pack are lit by.
//
// The transcription is deliberately literal: same expressions, same order, so
// the three copies can be read side by side. desktop/tools/validate-kwin-shaders.py
// compiles this and checks it computes what the NumPy computes.
//
// THE RULE THIS OBEYS
//
//   On a blurred surface, any effect that works by DISPLACING SAMPLES is
//   invisible. Only effects that MODIFY VALUES survive the blur.
//
// Both do: the edge adds brightness, the rim scales it. That is why these two
// survived and a refraction shader did not.
//
// The "#version 140" above is ignored. KWin's GLShader::preprocess drops any
// #version line in a theme's source and prepends its own ("#version 300 es"
// plus precision qualifiers), so this line documents intent and matches KWin's
// own shader files rather than selecting a language version.

#include "colormanagement.glsl"
#include "saturation.glsl"

uniform sampler2D sampler;
uniform vec4 modulation;

// Window size in DEVICE pixels, not logical ones: position0 below is scaled by
// the viewport scale, so a mismatch here silently halves the effect on a
// 2x display.
uniform vec2 facet_size;

// FacetEdgeShader's in_thickness / in_intensity / in_tint.
uniform float facet_thickness;
uniform float facet_intensity;
uniform vec3 facet_tint;

// FacetRimShader's in_rim / in_amount.
uniform float facet_rim;
uniform float facet_amount;

in vec2 texcoord0;

// Window-relative position in device pixels, with y increasing DOWNWARD from
// the top edge -- which is what the AGSL's `p` means.
//
// This is NOT derived from texcoord0, deliberately. KWin runs the quad's
// texture coordinates through the offscreen texture's own matrix
// (OffscreenData::paint -> postProcessTextureCoordinates), so texcoord0 is a
// position in TEXTURE space and may be flipped relative to the window. Using
// it for the edge distance would put the highlight along whichever edge the
// texture happened to be stored from, and would look correct exactly half the
// time.
//
// position0 comes from KWin's base.vert, which emits it under
// TRAIT_ROUNDED_CORNERS; the effect asks for that trait to get it.
in vec2 position0;

out vec4 fragColor;

// --- FacetEdgeShader --------------------------------------------------------
//
// Blur alone reads as frosted plastic. What reads as GLASS is the edge: a
// bright, narrow band where the surface curves away and catches light.
//
// Returns premultiplied colour, as the AGSL does.
vec4 facet_edge(vec2 p)
{
    float t = max(facet_thickness, 1.0);

    // Falloff from the lit edge. Squared so the band stays tight at its peak
    // and fades quickly, rather than smearing down the surface.
    float d = p.y / t;
    float edge = exp(-d * d * 2.0);

    // Bias toward the centre, so the highlight reads as a curved surface
    // catching light rather than a painted-on stripe.
    float x = (p.x / max(facet_size.x, 1.0)) * 2.0 - 1.0;
    float arc = max(1.0 - x * x * 0.55, 0.0);

    float a = clamp(edge * arc * facet_intensity, 0.0, 1.0);
    return vec4(facet_tint * a, a);
}

// --- FacetRimShader ---------------------------------------------------------
//
// A pane of glass is optically thicker where it curves away, so it absorbs
// more light at the rim than through the middle. Peaks at both vertical edges
// and falls to nothing across the centre, which gives a surface a defined
// boundary without drawing a border on it.
float facet_rim_band(vec2 p)
{
    float r = max(facet_rim, 1.0);

    float dl = p.x / r;
    float dr = (facet_size.x - p.x) / r;

    // Named rather than returned directly so this stays a literal
    // transcription of the AGSL, which validate-kwin-shaders.py compares
    // expression by expression.
    float band = abs(exp(-dl * dl) - exp(-dr * dr));
    return band;
}

// Is this fragment inside the window frame?
//
// NOT a detail. KWin builds the quad from the window's EXPANDED geometry --
// frame plus shadow -- and position0 is measured from the FRAME's top-left
// (OffscreenEffect::drawWindow moves visibleRect by expandedGeometry.topLeft()
// - frameGeometry.topLeft()). So p is NEGATIVE across the shadow above and to
// the left of the window, and runs past facet_size on the other two sides.
//
// Both effects are even in p: exp(-d*d) gives the same value for -d as for d.
// Ungated, the specular edge is therefore mirrored into the shadow and paints
// a bright band floating ABOVE the window, which looks like a compositing bug
// and is really an arithmetic one.
float facet_inside(vec2 p)
{
    vec2 lo = step(vec2(0.0), p);
    vec2 hi = step(p, facet_size);
    return lo.x * lo.y * hi.x * hi.y;
}

void main()
{
    vec2 p = position0;
    float inside = facet_inside(p);
    vec4 tex = texture(sampler, texcoord0);

    // The FacetUI maths runs on the surface's own encoded values, before
    // KWin's colour pipeline, because that is where the AGSL runs on Android:
    // Skia hands the shader the surface colour, not scene-referred light. Doing
    // it after the conversion to nits would be a different operation wearing
    // the same constants.

    // Rim: colour is premultiplied, so scaling rgb darkens without altering
    // coverage. Alpha is deliberately left untouched.
    tex.rgb *= 1.0 - inside * facet_amount * facet_rim_band(p);

    // Edge: composited over the surface, source-over on premultiplied colour,
    // which is what Canvas.drawRect with the shader does on Android.
    vec4 e = facet_edge(p) * inside;
    tex = e + tex * (1.0 - e.a);

    // From here on this is KWin's own pipeline, in KWin's order -- see
    // src/opengl/base.frag. The uniforms it needs are set unconditionally by
    // OffscreenData::paint, so they are available whatever traits were asked
    // for.
    tex = sourceEncodingToNitsInDestinationColorspace(tex);
    tex = adjustSaturation(tex);
    tex *= modulation;
    fragColor = nitsToDestinationEncoding(tex);
}
