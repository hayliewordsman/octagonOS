# SPDX-FileCopyrightText: 2026 The octagonOS Project
# SPDX-License-Identifier: Apache-2.0
#
# An out-of-tree KWin effect.
#
#     cmake -B build -DCMAKE_BUILD_TYPE=Release
#     cmake --build build
#     sudo cmake --install build
#
# THIS MUST BE BUILT AGAINST THE KWIN IT WILL RUN ON
#
# KWin's effect API is explicitly not binary compatible across versions -- its
# own header says so, next to KWIN_EFFECT_FACTORY. A plugin built against a
# different KWin than the one running will fail to load, or load and misbehave.
#
# That is not a problem for a distribution, which is what octagonOS Desktop is:
# the effect is built from source against the KWin in the same release, the
# same way every other package is. It IS a reason not to ship a prebuilt
# binary of this and expect it to keep working.

cmake_minimum_required(VERSION 3.20)

project(facetui-glass VERSION 0.1 LANGUAGES CXX)

set(QT_MIN_VERSION 6.6)
set(KF6_MIN_VERSION 6.0)

find_package(ECM ${KF6_MIN_VERSION} REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH})

include(KDEInstallDirs)
include(KDECMakeSettings)
include(KDECompilerSettings NO_POLICY_SCOPE)
include(FeatureSummary)

# Widgets and Quick are not used by this effect, but KWin::kwin names them in
# its own link interface, so they have to be found before that target can be
# used at all.
find_package(Qt6 ${QT_MIN_VERSION} REQUIRED COMPONENTS Core Gui Widgets Quick)
# The COMPONENT is Config; the TARGET it provides is KF6::ConfigCore. Asking
# for a component named ConfigCore configures cleanly right up to the point
# where it does not exist.
find_package(KF6 ${KF6_MIN_VERSION} REQUIRED COMPONENTS CoreAddons Config)

# KWin exports the KWin::kwin target and installs its effect and opengl headers
# under ${KDE_INSTALL_INCLUDEDIR}/kwin. Both are needed: the headers to compile
# against, the target to link.
find_package(KWin REQUIRED)

set(CMAKE_AUTOMOC ON)
# Without this, AutoMoc does not recognise KWIN_EFFECT_FACTORY_SUPPORTED as a
# macro that declares a QObject and warns on every build that main.cpp includes
# main.moc for no reason. moc still runs, so the plugin works -- but a warning
# that is always there is a warning nobody reads.
list(APPEND CMAKE_AUTOMOC_MACRO_NAMES
    KWIN_EFFECT_FACTORY
    KWIN_EFFECT_FACTORY_ENABLED
    KWIN_EFFECT_FACTORY_SUPPORTED
    KWIN_EFFECT_FACTORY_SUPPORTED_ENABLED
)
set(CMAKE_AUTORCC ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(facetui-glass MODULE)

target_sources(facetui-glass PRIVATE
    main.cpp
    facetuiglasseffect.cpp
    facetui-glass.qrc
)

target_link_libraries(facetui-glass PRIVATE
    KWin::kwin
    Qt6::Core
    Qt6::Gui
    KF6::ConfigCore
    KF6::CoreAddons
)

# Where KWin's EffectLoader looks for binary effects: the "kwin/effects/plugins"
# sub-directory of the Qt plugin path. See EffectLoader's m_pluginSubDirectory.
install(TARGETS facetui-glass
        DESTINATION ${KDE_INSTALL_PLUGINDIR}/kwin/effects/plugins)

feature_summary(WHAT ALL FATAL_ON_MISSING_REQUIRED_PACKAGES)
