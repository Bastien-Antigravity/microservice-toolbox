// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for C++ microservice-toolbox notification module:
// NotificationClient validation, fail-fast configuration resolution, and bridge dispatch.
//
// DATA FLOW:
// Test Harness -> NotificationClient -> libtoolbox C ABI Bridge -> Assertions
//
// KEY PARAMETERS:
// - None (Unit Test Suite).
// -----------------------------------------------------------------------------

#include <cassert>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>

#include "../include/microservice_toolbox/config/AppConfig.hpp"
#include "../include/microservice_toolbox/notification/NotificationClient.hpp"

using namespace microservice_toolbox;
using namespace microservice_toolbox::notification;

// -----------------------------------------------------------------------------

static void ensure_test_config_dir() {
#ifdef _WIN32
    system("mkdir config 2>nul");
#else
    system("mkdir -p config");
#endif
}

// -----------------------------------------------------------------------------

void test_notification_client_validation() {
    std::cout << "Testing NotificationClient address validation..." << std::endl;

    // 1. Empty target_addr must throw invalid_argument
    bool caught = false;
    try {
        NotificationClient client("");
    } catch (const std::invalid_argument &e) {
        caught = true;
    }
    assert(caught && "Expected empty target_addr to throw std::invalid_argument");

    // 2. Valid target_addr sets target address
    NotificationClient validClient("127.0.0.1:1027");
    assert(validClient.TargetAddr() == "127.0.0.1:1027");

    std::cout << "  Passed (Constructor validation verified)." << std::endl;
}

// -----------------------------------------------------------------------------

void test_from_config_fail_fast() {
    std::cout << "Testing NotificationClient::FromConfig fail-fast on missing capability..." << std::endl;
    ensure_test_config_dir();

    std::ofstream ofs("config/test.yaml");
    ofs << "common:\n  name: test-app\n"
        << "capabilities:\n"
        << "  log_server: {ip: '127.0.0.2', port: '9998'}\n"
        << "  config_server: {ip: '127.0.0.2', port: '9999'}\n";
    ofs.close();

    auto ac = config::LoadConfig("test");
    assert(ac != nullptr);

    bool caught = false;
    try {
        NotificationClient::FromConfig(*ac, nullptr, "nonexistent_capability");
    } catch (const std::runtime_error &e) {
        caught = true;
        std::string msg = e.what();
        assert(msg.find("nonexistent_capability") != std::string::npos);
    }
    std::remove("config/test.yaml");
    assert(caught && "Expected missing capability to fail-fast immediately");

    std::cout << "  Passed (Fail-fast verification verified: zero silent fallback)." << std::endl;
}

// -----------------------------------------------------------------------------

void test_from_config_success() {
    std::cout << "Testing NotificationClient::FromConfig default capability success..." << std::endl;
    ensure_test_config_dir();

    std::ofstream ofs("config/test.yaml");
    ofs << "common:\n  name: test-valid-notif\n"
        << "capabilities:\n"
        << "  log_server: {ip: '127.0.0.2', port: '9998'}\n"
        << "  config_server: {ip: '127.0.0.2', port: '9999'}\n"
        << "  notif_server:\n"
        << "    ip: '127.0.0.1'\n"
        << "    port: '1026'\n"
        << "    grpc_ip: '127.0.0.1'\n"
        << "    grpc_port: '1027'\n";
    ofs.close();

    auto ac = config::LoadConfig("test");
    assert(ac != nullptr);

    NotificationClient client = NotificationClient::FromConfig(*ac);
    assert(client.TargetAddr() == "127.0.0.1:1027");

    std::remove("config/test.yaml");
    std::cout << "  Passed (FromConfig properly resolved notif_server to 127.0.0.1:1027)." << std::endl;
}

// -----------------------------------------------------------------------------

void test_client_closed_and_methods() {
    std::cout << "Testing NotificationClient Close() and timeout..." << std::endl;

    NotificationClient client("127.0.0.1:1027");
    client.SetTimeout(2.5);

    // Close client
    client.Close();
    // Dispatch after close should return false without crashing
    bool sent = client.Send("Should be rejected because closed");
    assert(!sent);

    sent = client.SendAlert("WARNING", "Alert after close");
    assert(!sent);

    sent = client.SendWithAttachment("CRITICAL", "Attach after close", "chart.png", {"telegram"});
    assert(!sent);

    std::cout << "  Passed (Closed state guarded cleanly)." << std::endl;
}

// -----------------------------------------------------------------------------

void test_bridge_dynamic_loader() {
    std::cout << "Testing NotifBridgeLoader dynamic symbol loading..." << std::endl;

    std::string err;
    bool loaded = NotifBridgeLoader::Instance().EnsureLoaded(err);
    if (!loaded) {
        std::cerr << "  Bridge loader note: " << err << std::endl;
    }
    // We expect libnotif to load successfully from ../../notif-server/notif/libnotif/libnotif.dylib or candidate paths
    assert(loaded && "Expected libnotif to be found and loaded successfully");
    assert(NotifBridgeLoader::Instance().FnSend() != nullptr);
    assert(NotifBridgeLoader::Instance().FnGetLastError() != nullptr);
    assert(NotifBridgeLoader::Instance().FnFreeString() != nullptr);

    std::cout << "  Passed (libnotif C ABI symbols resolved)." << std::endl;
}

// -----------------------------------------------------------------------------

void test_dispatch_error_handling() {
    std::cout << "Testing NotificationClient dispatch error handling (offline target)..." << std::endl;

    // Port 19999 should be unreachable, with 0.1s timeout
    NotificationClient client("127.0.0.1:19999");
    client.SetTimeout(0.2);

    // Should return false cleanly and not throw / panic
    bool ok = client.SendAlert("TRADE", "BTC buy signal", {"telegram"});
    assert(!ok && "Expected offline dispatch to return false");

    std::cout << "  Passed (Graceful error handling without crash verified)." << std::endl;
}

// -----------------------------------------------------------------------------

int main() {
    try {
        test_notification_client_validation();
        test_from_config_fail_fast();
        test_from_config_success();
        test_client_closed_and_methods();
        test_bridge_dynamic_loader();
        test_dispatch_error_handling();

        std::cout << "\n=======================================" << std::endl;
        std::cout << "  All C++ Notification Tests Passed!" << std::endl;
        std::cout << "=======================================" << std::endl;
    } catch (const std::exception &e) {
        std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
