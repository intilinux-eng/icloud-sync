# SPDX-License-Identifier: MIT
# Dolphin overlay icons for icloud-sync: a check mark on synced files, arrows on files waiting to sync.
cmake_minimum_required(VERSION 3.16)
project(icloud-sync-dolphin VERSION 0.3.0 LANGUAGES CXX)

set(QT_MIN_VERSION "6.5.0")
set(KF_MIN_VERSION "6.0.0")

find_package(ECM ${KF_MIN_VERSION} REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH})
include(KDEInstallDirs)
include(KDECMakeSettings)
include(KDECompilerSettings NO_POLICY_SCOPE)

find_package(Qt6 ${QT_MIN_VERSION} REQUIRED COMPONENTS Core)
find_package(KF6 ${KF_MIN_VERSION} REQUIRED COMPONENTS KIO)

add_library(icloudsyncoverlay MODULE icloudsyncoverlay.cpp)
target_link_libraries(icloudsyncoverlay KF6::KIOCore)
install(TARGETS icloudsyncoverlay DESTINATION ${KDE_INSTALL_PLUGINDIR}/kf6/overlayicon)

include(CTest)
if(BUILD_TESTING)
    add_executable(overlaytest overlaytest.cpp)
    target_link_libraries(overlaytest Qt6::Core KF6::KIOCore)
    add_test(NAME overlay COMMAND overlaytest $<TARGET_FILE:icloudsyncoverlay>)
endif()
