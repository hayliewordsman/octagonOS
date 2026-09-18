# SPDX-FileCopyrightText: 2026 The octagonOS Project
# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.20)
project(icon-probe LANGUAGES CXX)

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui)

set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 20)

add_executable(icon-probe main.cpp)
target_link_libraries(icon-probe PRIVATE Qt6::Gui Qt6::Core)
