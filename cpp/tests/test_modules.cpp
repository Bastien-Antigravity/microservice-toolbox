// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Unit tests for C++ microservice-toolbox modules: Connectivity, Lifecycle, Business Models, Serializers.
//
// DATA FLOW:
// Test Harness -> Module Execution -> Assertions
//
// KEY PARAMETERS:
// - None (Unit Test Suite).
// -----------------------------------------------------------------------------

#include <cassert>
#include <iostream>
#include <vector>
#include <string>

#include "../include/microservice_toolbox/connectivity/Resolver.hpp"
#include "../include/microservice_toolbox/lifecycle/LifecycleManager.hpp"
#include "../include/microservice_toolbox/business/Models.hpp"
#include "../include/microservice_toolbox/serializers/JsonSerializer.hpp"
#include "../include/microservice_toolbox/serializers/BinSerializer.hpp"
#include "../include/microservice_toolbox/logger/Logger.hpp"
#include "../include/microservice_toolbox/wiretap/WireTap.hpp"
#include "../include/microservice_toolbox/conn_manager/ManagedConnection.hpp"
#include "../include/microservice_toolbox/trace/MissionTrace.hpp"

using namespace microservice_toolbox;

void test_connectivity_resolver() {
    std::cout << "Testing Connectivity Resolver..." << std::endl;
    
    // Native mode
    connectivity::Resolver r_native(false);
    assert(r_native.resolve_bind_addr("127.0.0.1") == "127.0.0.1");
    assert(r_native.resolve_full_bind_addr("127.0.0.1:8080") == "127.0.0.1:8080");
    assert(r_native.is_loopback("127.0.0.1"));
    assert(r_native.is_loopback("localhost"));
    assert(r_native.is_loopback("LocalHost"));
    assert(r_native.resolve_full_bind_addr("::1") == "::1");
    assert(r_native.resolve_full_bind_addr("[::1]:8080") == "[::1]:8080");

    // Docker mode also relies strictly on configured IP (zero hardcoded 0.0.0.0 override)
    connectivity::Resolver r_docker(true);
    assert(r_docker.is_docker);
    assert(r_docker.resolve_bind_addr("127.0.0.2") == "127.0.0.2");
    assert(r_docker.resolve_full_bind_addr("10.0.0.5:5000") == "10.0.0.5:5000");
    assert(r_docker.resolve_full_bind_addr("[::1]:8080") == "[::1]:8080");

    bool emptyThrew = false;
    try {
        (void)r_docker.resolve_bind_addr("");
    } catch (const std::invalid_argument&) {
        emptyThrew = true;
    }
    assert(emptyThrew);

    std::cout << "  Passed (Config-driven address resolution & fail-fast verified)." << std::endl;
}

void test_lifecycle_manager_lifo() {
    std::cout << "Testing Lifecycle Manager LIFO execution..." << std::endl;
    lifecycle::LifecycleManager lm;

    std::vector<std::string> executed;

    lm.Register("first", [&]() {
        executed.push_back("first");
    });
    lm.Register("second", [&]() {
        executed.push_back("second");
    });
    lm.Register("third", [&]() {
        executed.push_back("third");
    });
    lm.ExecuteCleanups();
    assert(executed.size() == 3);
    assert(executed[0] == "third" && executed[1] == "second" && executed[2] == "first");

    std::cout << "  Passed (Hooks registered and LIFO executed)." << std::endl;
}

void test_business_models() {
    std::cout << "Testing Business Models JSON serialization..." << std::endl;

    // 1. OHLCV
    business::OHLCV candle{"BTC/USDT", "1m", 1600000000, 50000.0, 50100.0, 49900.0, 50050.0, 12.5, 50025.0, 150};
    auto j_candle = candle.to_json();
    assert(j_candle["symbol"] == "BTC/USDT");
    assert(j_candle["close"] == 50050.0);
    assert(j_candle["trades"] == 150);

    // 2. Signal
    business::Signal sig{"strategy_alpha", "ETH/USDT", 1600000001, business::SignalType::Buy, 0.95f, 3500.0, "{}"};
    auto j_sig = sig.to_json();
    assert(j_sig["source"] == "strategy_alpha");
    assert(j_sig["type"] == "buy");
    assert(j_sig["price"] == 3500.0);

    // 3. MarketEvent (Base64 payload + Control + helpers)
    business::MarketEvent me{"evt_123", "SOL/USDT", "binance", 1600000002, business::MarketEventType::Trade, {1, 2, 3}};
    auto j_me = me.to_json();
    assert(j_me["event_id"] == "evt_123");
    assert(j_me["type"] == "trade");
    assert(j_me["payload"].is_string());
    assert(j_me["payload"] == "AQID");

    business::Trade tr{100.5, 1.5, business::Aggressor::Buy, "T1"};
    auto wrapped = business::WrapMarketEvent("BTC/USD", "Binance", business::MarketEventType::Control, tr);
    assert(wrapped.type == business::MarketEventType::Control);
    auto serialized = business::Serialize(wrapped);
    auto decoded = business::Deserialize<business::MarketEvent>(serialized);
    auto decoded_trade = business::Deserialize<business::Trade>(decoded.payload);
    assert(decoded_trade.price == 100.5);
    assert(decoded_trade.aggressor == business::Aggressor::Buy);
    assert(business::SystemTimestamp() > 0);

    std::cout << "  Passed." << std::endl;
}

void test_json_serializer() {
    std::cout << "Testing JsonSerializer..." << std::endl;
    serializers::JsonSerializer s;

    nlohmann::json data = {{"key", "value"}, {"num", 42}};
    std::vector<uint8_t> bytes = s.Marshal(data);
    assert(!bytes.empty());

    nlohmann::json deserialized = s.Unmarshal(bytes);
    assert(deserialized["key"] == "value");
    assert(deserialized["num"] == 42);

    std::cout << "  Passed." << std::endl;
}

void test_bin_serializer() {
    std::cout << "Testing BinSerializer (MsgPack)..." << std::endl;
    serializers::BinSerializer s;

    nlohmann::json data = {{"key", "binary_value"}, {"count", 100}};
    std::vector<uint8_t> bytes = s.Marshal(data);
    assert(!bytes.empty());

    nlohmann::json deserialized = s.Unmarshal(bytes);
    assert(deserialized["key"] == "binary_value");
    assert(deserialized["count"] == 100);

    std::cout << "  Passed." << std::endl;
}

void test_logger_interface() {
    std::cout << "Testing Logger interface..." << std::endl;
    unsetenv("STRICT_LOGGER");
    auto l = logger::EnsureSafeLogger(nullptr);
    assert(l != nullptr);
    l->Info("Test log message via EnsureSafeLogger");

    // Test strict mode
    setenv("STRICT_LOGGER", "true", 1);
    bool caught = false;
    try {
        logger::EnsureSafeLogger(nullptr);
    } catch (const std::runtime_error& e) {
        caught = true;
    }
    unsetenv("STRICT_LOGGER");
    assert(caught && "Expected EnsureSafeLogger to throw in strict mode");

    std::cout << "  Passed." << std::endl;
}

void test_wiretap() {
    std::cout << "Testing WireTap lock-free telemetry & sampling..." << std::endl;
    using namespace wiretap;

    Reset();
    SetEnabled(true);
    assert(IsEnabled());

    RecordEvent(
        "cpp-service",
        "web-interface",
        "SAFESOCKET",
        "frame",
        "market:trades",
        "frame",
        "outbound",
        "test payload",
        2048,
        0.8,
        false,
        false
    );

    auto snap = Snapshot();
    assert(snap.size() == 1);
    assert(snap[0].source == "cpp_service");
    assert(snap[0].target == "web_interface");
    assert(snap[0].protocol == "SAFESOCKET");
    assert(snap[0].total_frames == 1);
    assert(snap[0].total_bytes == 2048);
    assert(snap[0].channels.size() == 1);
    assert(snap[0].channels[0].channel == "market:trades");
    assert(snap[0].channels[0].frames == 1);
    assert(snap[0].channels[0].bytes == 2048);
    assert(snap[0].channels[0].last_payload == "test payload");

    // Test sampling (mask 0x3 -> 1 in 4)
    int samples = 0;
    for (int i = 0; i < 16; ++i) {
        if (ShouldSample(0x3)) {
            samples++;
        }
    }
    assert(samples == 4);

    // Test toggle OFF
    SetEnabled(false);
    assert(!IsEnabled());
    RecordEvent("cpp-service", "web-interface", "SAFESOCKET", "frame", "market:trades", "frame", "outbound", "", 500);
    auto snap2 = Snapshot();
    assert(snap2[0].total_frames == 1); // Should not increase when disabled

    // Test local service, hub URL, framing update & MergeRemoteSnapshot
    SetEnabled(true);
    SetLocalService("cpp-svc");
    assert(GetLocalService() == "cpp_svc");
    SetWebHubURL("http://127.0.0.1:5000/");
    assert(GetWebHubURL() == "http://127.0.0.1:5000");
    RecordEvent("cpp-service", "web-interface", "SAFESOCKET", "SafeSocket/TCP", "market:trades");
    auto snap3 = Snapshot();
    assert(snap3[0].framing == "SafeSocket/TCP");

    IngestResponse resp = IngestResponse::from_json({{"status", "ok"}, {"enabled", false}});
    assert(resp.status == "ok" && !resp.enabled);

    assert(SanitizePayloadSummary("secret=ENC(abc123xyz)") == "secret=ENC([REDACTED])");
    std::string long_payload(300, 'A');
    std::string sanitized_long = SanitizePayloadSummary(long_payload);
    assert(sanitized_long.size() == 256);
    assert(sanitized_long.substr(253) == "...");

    Reset();
    std::cout << "  Passed." << std::endl;
}

void test_mission_trace() {
    std::cout << "Testing MissionTrace inject & case-insensitive extract..." << std::endl;
    std::map<std::string, std::string> headers;
    trace::InjectHeaders(headers, "  mission-cpp-01  ");
    assert(headers["X-Bastien-Mission-ID"] == "mission-cpp-01");

    std::map<std::string, std::string> lower_headers = {{"x-bastien-mission-id", "mission-cpp-02"}};
    assert(trace::ExtractHeaders(lower_headers) == "mission-cpp-02");
    assert(trace::ExtractMissionId(lower_headers) == "mission-cpp-02");
    std::cout << "  Passed." << std::endl;
}

void test_conn_manager_reload() {
    std::cout << "Testing ConnManager lock-free Endpoint atomic swap..." << std::endl;
    auto nm = std::make_shared<conn_manager::NetworkManager>(3, 5, 20, 10, 1.5, 0.0, nullptr);

    conn_manager::ManagedConnection mc("127.0.0.1", "8080", "1.2.3.4", "test", nm);
    assert(mc.GetEndpoint().first == "127.0.0.1");
    assert(mc.GetEndpoint().second == "8080");
    assert(mc.GetEndpointPtr()->address == "127.0.0.1:8080");

    mc.UpdateEndpoint("10.0.0.1", "5000");
    assert(mc.GetEndpoint().first == "10.0.0.1");
    assert(mc.GetEndpoint().second == "5000");
    assert(mc.GetEndpointPtr()->address == "10.0.0.1:5000");
    assert(mc.GetEndpointPtr()->public_ip == "1.2.3.4");

    std::cout << "  Passed (ConnManager lock-free Endpoint atomic swap verified)." << std::endl;
}

void test_conn_manager_app_config_binding() {
    std::cout << "Testing ConnManager AppConfig attachment..." << std::endl;
    auto ac = config::LoadConfigWithLogger("standalone", std::make_shared<utils::StdOutLogger>());
    assert(ac != nullptr);

    auto nm = conn_manager::NetworkManager::NewWithConfig(std::move(ac));
    assert(nm->app_config != nullptr);
    assert(nm->app_config->GetProfile() == "standalone");

    // Test missing capability throws cleanly
    bool threw = false;
    try {
        nm->ConnectCapability("non-existent-capability-1234");
    } catch (const std::exception& e) {
        threw = true;
    }
    assert(threw);
    std::cout << "  Passed (ConnManager AppConfig attachment verified)." << std::endl;
}

int main() {
    try {
        test_connectivity_resolver();
        test_lifecycle_manager_lifo();
        test_business_models();
        test_json_serializer();
        test_bin_serializer();
        test_logger_interface();
        test_wiretap();
        test_mission_trace();
        test_conn_manager_reload();
        test_conn_manager_app_config_binding();

        std::cout << "\n=======================================" << std::endl;
        std::cout << "  All C++ Modules Tests Passed!" << std::endl;
        std::cout << "=======================================" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
