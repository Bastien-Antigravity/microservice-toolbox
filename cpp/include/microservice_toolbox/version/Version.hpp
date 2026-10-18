// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized dynamic version resolution engine for C++ services and tools.
// Reads dynamic semver strictly from VERSION.txt single source of truth,
// environment variable overrides, compile-time LDFLAGS/macros, and caches in memory.
//
// DATA FLOW:
// Compile-time Macro / Environment -> Directory Climbing -> VERSION.txt -> Cached Version
//
// KEY PARAMETERS:
// - startDir: Optional starting directory path for parent directory traversal.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_VERSION_HPP
#define MICROSERVICE_TOOLBOX_VERSION_HPP

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>

namespace microservice_toolbox {
namespace version {

namespace fs = std::filesystem;

inline std::string Trim(const std::string& str) {
    auto start = str.find_first_not_of(" \t\n\r");
    if (start == std::string::npos) return "";
    auto end = str.find_last_not_of(" \t\n\r");
    return str.substr(start, end - start + 1);
}

inline std::mutex& GetVersionMutex() {
    static std::mutex mtx;
    return mtx;
}

inline std::string& GetCachedVersionRef() {
    static std::string cached;
    return cached;
}

inline void SetVersion(const std::string& version) {
    std::lock_guard<std::mutex> lock(GetVersionMutex());
    GetCachedVersionRef() = Trim(version);
}

inline void ResetVersion() {
    std::lock_guard<std::mutex> lock(GetVersionMutex());
    GetCachedVersionRef().clear();
}

inline std::string ResolveVersion(const std::string& startDir = "") {
    // 1. Check compile-time macro
#ifdef APP_VERSION
    std::string buildVer = APP_VERSION;
    if (!buildVer.empty()) {
        return Trim(buildVer);
    }
#endif

    // 2. Check environment variables
    const char* appVer = std::getenv("APP_VERSION");
    if (appVer && *appVer) {
        return Trim(appVer);
    }
    const char* svcVer = std::getenv("SERVICE_VERSION");
    if (svcVer && *svcVer) {
        return Trim(svcVer);
    }

    // 3. Climb parent directories searching for VERSION.txt
    try {
        fs::path searchPath;
        if (!startDir.empty()) {
            searchPath = fs::absolute(startDir);
        } else {
            searchPath = fs::current_path();
        }

        while (true) {
            fs::path candidate = searchPath / "VERSION.txt";
            if (fs::exists(candidate) && fs::is_regular_file(candidate)) {
                std::ifstream f(candidate);
                if (f.is_open()) {
                    std::string line;
                    if (std::getline(f, line)) {
                        std::string trimmed = Trim(line);
                        if (!trimmed.empty()) {
                            return trimmed;
                        }
                    }
                }
            }
            if (!searchPath.has_parent_path() || searchPath == searchPath.parent_path()) {
                break;
            }
            searchPath = searchPath.parent_path();
        }
    } catch (...) {
        // Fallback on filesystem exception
    }

    return "0.0.1";
}

inline std::string GetVersion(const std::string& startDir = "") {
    std::lock_guard<std::mutex> lock(GetVersionMutex());
    std::string& cached = GetCachedVersionRef();
    if (!cached.empty()) {
        return cached;
    }
    cached = ResolveVersion(startDir);
    return cached;
}

} // namespace version
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_VERSION_HPP
