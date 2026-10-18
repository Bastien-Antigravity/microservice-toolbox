// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for C++ microservice-toolbox dynamic versioning engine.
//
// DATA FLOW:
// Test Harness -> Version Resolution -> Assertions
// -----------------------------------------------------------------------------

#include <cassert>
#include <cstdlib>
#include <iostream>
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

    ResetVersion();
    // After reset, re-resolves from file or fallback
    std::string ver = GetVersion();
    assert(ver == "0.0.1");
    std::cout << "  Passed (Manual setter and cache reset verified)." << std::endl;
}

void test_env_override() {
    std::cout << "Testing environment variable override..." << std::endl;
    setenv("APP_VERSION", "1.5.0-custom", 1);
    ResetVersion();
    std::string ver = GetVersion();
    assert(ver == "1.5.0-custom");
    unsetenv("APP_VERSION");

    ResetVersion();
    assert(GetVersion() == "0.0.1");
    std::cout << "  Passed (Environment variable override verified)." << std::endl;
}

int main() {
    std::cout << "\n=======================================" << std::endl;
    std::cout << "  Running C++ Version Unit Tests" << std::endl;
    std::cout << "=======================================" << std::endl;

    test_default_version_resolution();
    test_set_and_reset_version();
    test_env_override();

    std::cout << "\n=======================================" << std::endl;
    std::cout << "  All C++ Version Tests Passed!" << std::endl;
    std::cout << "=======================================\n" << std::endl;
    return 0;
}
