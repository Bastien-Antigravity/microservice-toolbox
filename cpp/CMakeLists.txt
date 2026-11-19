# -----------------------------------------------------------------------------
# ESSENTIAL PROCESS:
# CMake packaging definition for the microservice-toolbox C++17 header-only SDK.
# Enables external L3/L4/L5 services to consume microservice_toolbox::toolbox via
# CMake FetchContent or add_subdirectory without hardcoded relative paths.
#
# DATA FLOW:
# ../VERSION.txt (Fail-Fast) -> project(VERSION) -> INTERFACE target microservice_toolbox::toolbox
# Optional libdistconf discovery -> INTERFACE link libraries
#
# KEY PARAMETERS:
# - LIBDISTCONF_PATH: Optional environment override pointing to libdistconf shared library.
# -----------------------------------------------------------------------------

cmake_minimum_required(VERSION 3.16)

# -----------------------------------------------------------------------------
# Fail-Fast Version Resolution (VERSION.txt is sole source of truth)
# -----------------------------------------------------------------------------
set(_MICROSERVICE_TOOLBOX_VERSION_FILE "${CMAKE_CURRENT_SOURCE_DIR}/../VERSION.txt")
if(NOT EXISTS "${_MICROSERVICE_TOOLBOX_VERSION_FILE}")
    message(FATAL_ERROR "microservice-toolbox: VERSION.txt not found at ${_MICROSERVICE_TOOLBOX_VERSION_FILE} (FAIL-FAST)")
endif()

file(READ "${_MICROSERVICE_TOOLBOX_VERSION_FILE}" _MICROSERVICE_TOOLBOX_RAW_VERSION)
string(STRIP "${_MICROSERVICE_TOOLBOX_RAW_VERSION}" MICROSERVICE_TOOLBOX_VERSION)
if(NOT MICROSERVICE_TOOLBOX_VERSION)
    message(FATAL_ERROR "microservice-toolbox: VERSION.txt is empty at ${_MICROSERVICE_TOOLBOX_VERSION_FILE} (FAIL-FAST)")
endif()

project(microservice_toolbox VERSION ${MICROSERVICE_TOOLBOX_VERSION} LANGUAGES CXX)

# -----------------------------------------------------------------------------
# Header-Only INTERFACE Target Definition
# -----------------------------------------------------------------------------
add_library(microservice_toolbox INTERFACE)
add_library(microservice_toolbox::toolbox ALIAS microservice_toolbox)

target_compile_features(microservice_toolbox INTERFACE cxx_std_17)
target_include_directories(microservice_toolbox INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# -----------------------------------------------------------------------------
# Optional libdistconf Shared Library Discovery
# -----------------------------------------------------------------------------
set(MICROSERVICE_TOOLBOX_DISTCONF_LIB "" CACHE FILEPATH "Optional path to libdistconf shared library")

if(NOT MICROSERVICE_TOOLBOX_DISTCONF_LIB AND DEFINED ENV{LIBDISTCONF_PATH} AND NOT "$ENV{LIBDISTCONF_PATH}" STREQUAL "")
    if(IS_DIRECTORY "$ENV{LIBDISTCONF_PATH}")
        find_library(_ENV_DISTCONF_LIB
            NAMES distconf libdistconf
            PATHS "$ENV{LIBDISTCONF_PATH}"
            NO_DEFAULT_PATH
        )
        if(_ENV_DISTCONF_LIB)
            set(MICROSERVICE_TOOLBOX_DISTCONF_LIB "${_ENV_DISTCONF_LIB}")
        endif()
    elseif(EXISTS "$ENV{LIBDISTCONF_PATH}")
        set(MICROSERVICE_TOOLBOX_DISTCONF_LIB "$ENV{LIBDISTCONF_PATH}")
    endif()
endif()

if(NOT MICROSERVICE_TOOLBOX_DISTCONF_LIB)
    set(_DISTCONF_SEARCH_PATHS
        "/usr/local/lib"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../distributed-config/distconf/libdistconf"
    )
    if(DEFINED ENV{HOME} AND NOT "$ENV{HOME}" STREQUAL "")
        list(PREPEND _DISTCONF_SEARCH_PATHS "$ENV{HOME}/.bastien/lib")
    endif()

    find_library(_FOUND_DISTCONF_LIB
        NAMES distconf libdistconf
        PATHS ${_DISTCONF_SEARCH_PATHS}
    )
    if(_FOUND_DISTCONF_LIB)
        set(MICROSERVICE_TOOLBOX_DISTCONF_LIB "${_FOUND_DISTCONF_LIB}")
    endif()
endif()

if(MICROSERVICE_TOOLBOX_DISTCONF_LIB)
    message(STATUS "microservice_toolbox: found optional libdistconf at ${MICROSERVICE_TOOLBOX_DISTCONF_LIB}")
    target_link_libraries(microservice_toolbox INTERFACE "${MICROSERVICE_TOOLBOX_DISTCONF_LIB}")
    get_filename_component(_DISTCONF_LIB_DIR "${MICROSERVICE_TOOLBOX_DISTCONF_LIB}" DIRECTORY)
    target_include_directories(microservice_toolbox INTERFACE "${_DISTCONF_LIB_DIR}")
else()
    message(STATUS "microservice_toolbox: optional libdistconf not found; exporting header-only interface")
endif()
