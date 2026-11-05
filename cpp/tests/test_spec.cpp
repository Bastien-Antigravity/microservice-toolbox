/*
 * ESSENTIAL PROCESS:
 * Unit tests for C++ microservice-toolbox dynamic specification and fail-fast publishing.
 *
 * DATA FLOW:
 * 1. ProtocolSpec & ServiceSpec instantiation -> ToJson() -> Assert JSON fields
 * 2. Valid AppConfig + ServiceSpec -> BuildSpecFromConfig() -> Assert dynamic enrichment
 * 3. Missing metadata fields -> BuildSpecFromConfig() -> Assert fail-fast exceptions
 * 4. Missing web_interface -> PublishSync() -> Assert fail-fast exception
 *
 * KEY PARAMETERS:
 * - None (Unit Test Suite).
 */

#include <cassert>
#include <iostream>
#include <string>

#include "../include/microservice_toolbox/spec/spec.hpp"

using namespace microservice_toolbox::spec;

// -----------------------------------------------------------------------------

void test_protocol_spec_serialization() {
    std::cout << "Testing ProtocolSpec serialization..." << std::endl;
    ProtocolSpec p{"tcp", 9020, "length-prefix", "SafeSocket TCP framing"};
    auto j = p.ToJson();
    assert(j["type"] == "tcp");
    assert(j["port"] == 9020);
    assert(j["framing"] == "length-prefix");
    assert(j["description"] == "SafeSocket TCP framing");

    auto jCamel = p.toJson();
    assert(jCamel["port"] == 9020);
    std::cout << "  Passed." << std::endl;
}

// -----------------------------------------------------------------------------

void test_service_spec_serialization() {
    std::cout << "Testing ServiceSpec serialization..." << std::endl;
    ServiceSpec s;
    s.name = "test_service";
    s.tag = "test-service-mfe";
    s.url = "http://127.0.0.1:9999/static/mfe.js";
    s.navTitle = "Test Service";
    s.layer = "L2";
    s.category = "Domain Services";
    s.priority = 50;
    s.icon = "fa-rocket";
    s.requiresAuth = true;
    s.capability = "test_service";
    s.description = "Test microservice description";
    s.protocol = "gRPC & REST";
    s.framing = "Protobuf";
    s.docLink = "obsidian-brain/06-Microservices/TestService.md";
    s.flowDiagram = {"Step 1", "Step 2"};
    s.sdkLang = "language-cpp";

    auto j = s.ToJson();
    assert(j["name"] == "test_service");
    assert(j["tag"] == "test-service-mfe");
    assert(j["url"] == "http://127.0.0.1:9999/static/mfe.js");
    assert(j["navTitle"] == "Test Service");
    assert(j["layer"] == "L2");
    assert(j["category"] == "Domain Services");
    assert(j["priority"] == 50);
    assert(j["icon"] == "fa-rocket");
    assert(j["requiresAuth"] == true);
    assert(j["capability"] == "test_service");
    assert(j["desc"] == "Test microservice description");
    assert(j["protocol"] == "gRPC & REST");
    assert(j["framing"] == "Protobuf");
    assert(j["docLink"] == "obsidian-brain/06-Microservices/TestService.md");
    assert(j["flowDiagram"].size() == 2);
    assert(j["sdkLang"] == "language-cpp");

    std::cout << "  Passed." << std::endl;
}

// -----------------------------------------------------------------------------

void test_build_spec_from_config() {
    std::cout << "Testing BuildSpecFromConfig..." << std::endl;
    microservice_toolbox::config::AppConfig cfg("test");

    ServiceSpec validBase;
    validBase.name = "Config Server";
    validBase.tag = "config-server-mfe";
    validBase.layer = "L1";
    validBase.category = "Base Fleet";
    validBase.priority = 20;
    validBase.icon = "fa-cogs";
    validBase.description = "Centralized configuration repository.";
    validBase.protocol = "TCP, REST & gRPC";
    validBase.framing = "Port %s REST";
    validBase.docLink = "obsidian-brain/06-Microservices/Config-Server-Hub.md";

    ServiceSpec enriched = SpecPublisher::BuildSpecFromConfig(cfg, "config_server", validBase);
    assert(enriched.name == "Config Server");
    assert(enriched.tag == "config-server-mfe");
    assert(enriched.layer == "L1");
    assert(enriched.category == "Base Fleet");
    assert(!enriched.url.empty());
    assert(enriched.dataStructure["version"].is_string());
    std::cout << "  Passed (Enrichment verified with URL: " << enriched.url << ")." << std::endl;

    // Fail-fast tests
    bool caught = false;
    try {
        ServiceSpec missingName = validBase;
        missingName.name = "";
        SpecPublisher::BuildSpecFromConfig(cfg, "config_server", missingName);
    } catch (const std::invalid_argument&) {
        caught = true;
    }
    assert(caught && "Expected fail-fast on missing name");

    caught = false;
    try {
        ServiceSpec missingLayer = validBase;
        missingLayer.layer = "";
        SpecPublisher::BuildSpecFromConfig(cfg, "config_server", missingLayer);
    } catch (const std::invalid_argument&) {
        caught = true;
    }
    assert(caught && "Expected fail-fast on missing layer");

    caught = false;
    try {
        ServiceSpec missingDoc = validBase;
        missingDoc.docLink = "";
        SpecPublisher::BuildSpecFromConfig(cfg, "config_server", missingDoc);
    } catch (const std::invalid_argument&) {
        caught = true;
    }
    assert(caught && "Expected fail-fast on missing docLink");

    caught = false;
    try {
        SpecPublisher::BuildSpecFromConfig(cfg, "unknown_capability_xyz", validBase);
    } catch (const std::runtime_error&) {
        caught = true;
    }
    assert(caught && "Expected fail-fast on unknown capability with no addresses");

    std::cout << "  Fail-Fast assertions passed." << std::endl;
}

// -----------------------------------------------------------------------------

void test_publish_sync() {
    std::cout << "Testing PublishSync with AppConfig..." << std::endl;
    microservice_toolbox::config::AppConfig cfg("test");

    ServiceSpec validBase;
    validBase.name = "Config Server";
    validBase.tag = "config-server-mfe";
    validBase.layer = "L1";
    validBase.category = "Base Fleet";
    validBase.description = "Centralized configuration repository.";
    validBase.protocol = "TCP";
    validBase.framing = "Port %s TCP";
    validBase.docLink = "obsidian-brain/06-Microservices/Config-Server-Hub.md";

    // When web_interface is offline, PublishSync attempts network delivery and returns false cleanly
    bool published = SpecPublisher::PublishSync(cfg, nullptr, "config_server", validBase);
    assert(!published && "Expected PublishSync to return false when web_interface is offline");

    // Fail-fast test: missing web_interface in config throws std::runtime_error
    bool caught = false;
    try {
        SpecPublisher::PublishSync(cfg, nullptr, "unknown_capability_xyz", validBase);
    } catch (const std::runtime_error&) {
        caught = true;
    }
    assert(caught && "Expected fail-fast on unknown capability in PublishSync");

    std::cout << "  Passed (Offline delivery gracefully returned false & fail-fast verified)." << std::endl;
}

// -----------------------------------------------------------------------------

int main() {
    std::cout << "\n=======================================" << std::endl;
    std::cout << "  Running C++ Spec Unit Tests" << std::endl;
    std::cout << "=======================================" << std::endl;

    try {
        test_protocol_spec_serialization();
        test_service_spec_serialization();
        test_build_spec_from_config();
        test_publish_sync();

        std::cout << "\n=======================================" << std::endl;
        std::cout << "  All C++ Spec Tests Passed!" << std::endl;
        std::cout << "=======================================\n" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
