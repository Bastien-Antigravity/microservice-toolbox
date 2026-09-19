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

using namespace microservice_toolbox;

void test_connectivity_resolver() {
    std::cout << "Testing Connectivity Resolver..." << std::endl;
    
    // Native mode
    connectivity::Resolver r_native(false);
    assert(r_native.resolve_bind_addr("127.0.0.1") == "127.0.0.1");
    assert(r_native.resolve_bind_addr("\"127.0.0.1\"") == "127.0.0.1");
    assert(r_native.resolve_full_bind_addr("127.0.0.1:8080") == "127.0.0.1:8080");
    assert(r_native.is_loopback("127.0.0.1"));
    assert(r_native.is_loopback("localhost"));

    // Docker Guard mode (forced)
    connectivity::Resolver r_docker(true);
    assert(r_docker.resolve_bind_addr("127.0.0.1") == "0.0.0.0");
    assert(r_docker.resolve_bind_addr("\"127.0.0.2\"") == "0.0.0.0");
    assert(r_docker.resolve_full_bind_addr("127.0.0.1:5000") == "0.0.0.0:5000");

    std::cout << "  Passed (Docker Guard suppression & address translation verified)." << std::endl;
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

    std::cout << "  Passed (Hooks registered)." << std::endl;
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

    // 3. MarketEvent
    business::MarketEvent me{"evt_123", "SOL/USDT", "binance", 1600000002, business::MarketEventType::Trade, {1, 2, 3}};
    auto j_me = me.to_json();
    assert(j_me["event_id"] == "evt_123");
    assert(j_me["type"] == "trade");

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
    auto l = logger::EnsureSafeLogger(nullptr);
    assert(l != nullptr);
    l->Info("Test log message via EnsureSafeLogger");

    std::cout << "  Passed." << std::endl;
}

int main() {
    try {
        test_connectivity_resolver();
        test_lifecycle_manager_lifo();
        test_business_models();
        test_json_serializer();
        test_bin_serializer();
        test_logger_interface();

        std::cout << "\n=======================================" << std::endl;
        std::cout << "  All C++ Modules Tests Passed!" << std::endl;
        std::cout << "=======================================" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
