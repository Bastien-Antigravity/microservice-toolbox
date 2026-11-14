// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for C++ microservice-toolbox dynamic versioning engine.
//
// DATA FLOW:
// Test Harness -> Version Resolution -> Assertions
// -----------------------------------------------------------------------------

#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include "../include/microservice_toolbox/version/Version.hpp"

using namespace microservice_toolbox::version;

void test_default_version_resolution() {
    std::cout << "Testing default version resolution..." << std::endl;
    ResetVersion();
    std::string ver = GetVersion();
    assert(!ver.empty());
    assert(ver == "0.0.1");
    std::cout << "  Passed (Resolved version: " << ver << ")." << std::endl;
}

void test_set_and_reset_version() {
    std::cout << "Testing SetVersion and ResetVersion..." << std::endl;
    SetVersion("2.3.4");
    assert(GetVersion() == "2.3.4");

    bool emptyThrew = false;
    try {
        SetVersion("   ");
    } catch (const std::invalid_argument&) {
        emptyThrew = true;
    }
    assert(emptyThrew);

    ResetVersion();
    // After reset, re-resolves from VERSION.txt
    std::string ver = GetVersion();
    assert(ver == "0.0.1");
    std::cout << "  Passed (Manual setter fail-fast and cache reset verified)." << std::endl;
}

void test_fail_fast_missing_version_txt() {
    std::cout << "Testing fail-fast when VERSION.txt is absent..." << std::endl;
    ResetVersion();

    namespace fs = std::filesystem;
    fs::path origCwd = fs::current_path();
    fs::path isolated = fs::temp_directory_path() / "mt_cpp_ver_missing_test";
    fs::remove_all(isolated);
    fs::create_directories(isolated / ".git");

    bool missingThrew = false;
    try {
        fs::current_path(isolated);
        try {
            (void)ResolveVersion(isolated.string());
        } catch (const std::runtime_error&) {
            missingThrew = true;
        }
        fs::current_path(origCwd);
    } catch (...) {
        fs::current_path(origCwd);
        fs::remove_all(isolated);
        throw;
    }
    fs::remove_all(isolated);
    assert(missingThrew);
    std::cout << "  Passed (Fail-fast exception verified when VERSION.txt absent)." << std::endl;
}

void test_isolated_version_file_ignores_env() {
    std::cout << "Testing VERSION.txt resolution ignores runtime env vars..." << std::endl;
    setenv("APP_VERSION", "9.9.9-ignored", 1);
    ResetVersion();

    namespace fs = std::filesystem;
    fs::path origCwd = fs::current_path();
    fs::path root = fs::temp_directory_path() / "mt_cpp_ver_file_test";
    fs::path nested = root / "src" / "handlers";
    fs::remove_all(root);
    fs::create_directories(nested);
    fs::create_directories(root / ".git");
    {
        std::ofstream ofs(root / "VERSION.txt");
        ofs << "1.5.0-custom\n";
    }

    std::string ver;
    try {
        fs::current_path(nested);
        ver = GetVersion(nested.string());
        fs::current_path(origCwd);
    } catch (...) {
        fs::current_path(origCwd);
        unsetenv("APP_VERSION");
        fs::remove_all(root);
        throw;
    }
    unsetenv("APP_VERSION");
    fs::remove_all(root);
    assert(ver == "1.5.0-custom");

    ResetVersion();
    assert(GetVersion() == "0.0.1");
    std::cout << "  Passed (VERSION.txt climber strictly preferred over env verified)." << std::endl;
}

int main() {
    std::cout << "\n=======================================" << std::endl;
    std::cout << "  Running C++ Version Unit Tests" << std::endl;
    std::cout << "=======================================" << std::endl;

    test_default_version_resolution();
    test_set_and_reset_version();
    test_fail_fast_missing_version_txt();
    test_isolated_version_file_ignores_env();

    std::cout << "\n=======================================" << std::endl;
    std::cout << "  All C++ Version Tests Passed!" << std::endl;
    std::cout << "=======================================\n" << std::endl;
    return 0;
}
