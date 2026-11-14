// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Standardized dynamic version resolution engine for C++ services and tools.
// Reads dynamic semver strictly from VERSION.txt (or compile-time APP_VERSION baked from VERSION.txt).
//
// DATA FLOW:
// Bounded 12-level Climber (.git boundary) -> VERSION.txt -> Cache (Throws Fail-Fast if Missing)
//
// KEY PARAMETERS:
// - startDir: Optional starting directory or file path for upward traversal.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_VERSION_HPP
#define MICROSERVICE_TOOLBOX_VERSION_HPP

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

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
    std::string trimmed = Trim(version);
    if (trimmed.empty()) {
        throw std::invalid_argument("version::SetVersion: version string must not be empty (FAIL-FAST)");
    }
    std::lock_guard<std::mutex> lock(GetVersionMutex());
    GetCachedVersionRef() = trimmed;
}

inline void set_version(const std::string& version) {
    SetVersion(version);
}

inline void ResetVersion() {
    std::lock_guard<std::mutex> lock(GetVersionMutex());
    GetCachedVersionRef().clear();
}

inline void reset_version() {
    ResetVersion();
}

namespace detail {

inline bool ReadVersionFile(const fs::path& filePath, std::string& out) {
    if (!fs::exists(filePath) || !fs::is_regular_file(filePath)) return false;
    std::ifstream f(filePath);
    if (!f.is_open()) return false;
    std::string line;
    if (std::getline(f, line)) {
        std::string trimmed = Trim(line);
        if (!trimmed.empty()) {
            out = trimmed;
            return true;
        }
    }
    return false;
}

} // namespace detail

inline std::string ResolveVersion(const std::string& startDir = "") {
    // 1. Climb parent directories for VERSION.txt (bounded 12 levels, stopping at .git boundary)
    std::vector<fs::path> searchPaths;
    if (!startDir.empty()) {
        fs::path p = fs::absolute(startDir);
        std::string direct;
        if (fs::is_regular_file(p) && detail::ReadVersionFile(p, direct)) {
            return direct;
        }
        searchPaths.push_back(fs::is_regular_file(p) ? p.parent_path() : p);
    }
    searchPaths.push_back(fs::current_path());

    for (const auto& origin : searchPaths) {
        fs::path searchPath = origin;
        for (int depth = 0; depth < 12; ++depth) {
            std::string resolved;
            if (detail::ReadVersionFile(searchPath / "VERSION.txt", resolved)) {
                return resolved;
            }
            if (fs::exists(searchPath / ".git") ||
                !searchPath.has_parent_path() ||
                searchPath == searchPath.parent_path()) {
                break;
            }
            searchPath = searchPath.parent_path();
        }
    }

    // 2. Check compile-time macro (baked from VERSION.txt by build system)
#ifdef APP_VERSION
    std::string buildVer = Trim(APP_VERSION);
    if (!buildVer.empty()) {
        return buildVer;
    }
#endif

    throw std::runtime_error("version::ResolveVersion: VERSION.txt not found or empty (FAIL-FAST)");
}

inline std::string resolve_version(const std::string& startDir = "") {
    return ResolveVersion(startDir);
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

inline std::string get_version(const std::string& startDir = "") {
    return GetVersion(startDir);
}

} // namespace version
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_VERSION_HPP
