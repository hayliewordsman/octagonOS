# SPDX-FileCopyrightText: 2026 The octagonOS Project
# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.20)
project(plasma-probe LANGUAGES CXX)

find_package(ECM 6.0 REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH})
include(KDEInstallDirs)
include(KDECMakeSettings)
include(KDECompilerSettings NO_POLICY_SCOPE)

find_package(Qt6 6.6 REQUIRED COMPONENTS Core Gui Quick)
find_package(KF6 6.0 REQUIRED COMPONENTS CoreAddons Config Svg)

set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 20)

add_executable(plasma-probe main.cpp)
target_link_libraries(plasma-probe PRIVATE KF6::Svg Qt6::Gui Qt6::Core)
