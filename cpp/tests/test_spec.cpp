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

void test_exchange_contracts_and_extractors() {
    std::cout << "Testing ExchangeContract, ContractsEnvelope & IDL Extractors..." << std::endl;

    std::string proto =
        "syntax = \"proto3\";\n"
        "package demo.v1;\n"
        "service DemoControl {\n"
        "  rpc Ping (PingReq) returns (PingResp);\n"
        "  rpc StreamEvents (stream EventReq) returns (stream EventResp);\n"
        "  rpc TailLogs (TailReq) returns (stream LogChunk);\n"
        "}\n";

    auto protoOps = ExtractProtoTextOperations(proto);
    assert(protoOps.size() == 3);
    assert(protoOps[0].kind == "RPC");
    assert(protoOps[0].target == "demo.v1.DemoControl/Ping");
    assert(protoOps[1].kind == "BIDI_STREAM");
    assert(protoOps[1].input == "stream EventReq");
    assert(protoOps[1].output == "stream EventResp");
    assert(protoOps[2].kind == "SERVER_STREAM");

    std::string capnp =
        "enum Level {\n"
        "  info @0; # info severity\n"
        "  error @1;\n"
        "}\n"
        "struct Frame {\n"
        "  seq @0 :UInt64;\n"
        "  payload @1 :Data;\n"
        "}\n";

    auto capOps = ExtractCapnpOperations(capnp);
    assert(capOps.size() == 2);
    assert(capOps[0].kind == "ENUM");
    assert(capOps[0].name == "Level");
    assert(capOps[0].output.find("info @0") != std::string::npos);
    assert(capOps[1].kind == "STRUCT");
    assert(capOps[1].name == "Frame");
    assert(capOps[1].input.find("payload @1 :Data") != std::string::npos);

    assert(ResolveContractPort("0.0.0.0:9021") == 9021);
    assert(DisplayAddress(":3308") == "127.0.0.1:3308");
    assert(DisplayAddress("") == "dynamic");

    ExchangeContract grpcContract;
    grpcContract.id = "grpc";
    grpcContract.type = "gRPC / Protobuf";
    grpcContract.tabLabel = "gRPC Protobuf";
    grpcContract.address = DisplayAddress(":9021");
    grpcContract.port = ResolveContractPort(":9021");
    grpcContract.peers = {ContractPeer{"web_interface", "consumer", "Displays OpenMFE tabs"}};
    grpcContract.operations = protoOps;
    grpcContract.schemaFormat = "proto3";
    grpcContract.schema = proto;

    auto env = NewContractsEnvelope("demo_cpp_service", "0.2.0", "unit test", {grpcContract});
    auto envJson = env.ToJson();
    assert(envJson["service"] == "demo_cpp_service");
    assert(envJson["version"] == "0.2.0");
    assert(envJson["reliable"] == true);
    assert(envJson["exhaustive"] == true);
    assert(envJson["contracts"].size() == 1);
    assert(envJson["contracts"][0]["tabLabel"] == "gRPC Protobuf");
    assert(envJson["contracts"][0]["operations"].size() == 3);

    // Verify FromJson round-trip
    auto parsedEnv = ContractsEnvelope::FromJson(envJson);
    assert(parsedEnv.contracts.size() == 1);
    assert(parsedEnv.contracts[0].operations.size() == 3);

    // Verify ServiceSpec carries protocols + contracts through BuildSpecFromConfig
    microservice_toolbox::config::AppConfig cfg("test");
    ServiceSpec base;
    base.name = "Config Server";
    base.tag = "config-server-mfe";
    base.layer = "L1";
    base.category = "Base Fleet";
    base.description = "Centralized configuration repository.";
    base.protocol = "TCP, REST & gRPC";
    base.framing = "Port %s REST";
    base.docLink = "obsidian-brain/06-Microservices/Config-Server-Hub.md";
    base.protocols = {ProtocolSpec{"gRPC", 9021, "Protobuf", "gRPC control"}};
    base.contracts = {grpcContract};

    ServiceSpec enriched = SpecPublisher::BuildSpecFromConfig(cfg, "config_server", base);
    auto specJson = enriched.ToJson();
    assert(specJson["navRoute"] == "/mfe/Config Server");
    assert(specJson["protocols"].size() == 1);
    assert(specJson["contracts"].size() == 1);
    assert(specJson["contracts"][0]["schemaFormat"] == "proto3");

    // Verify C helper JSON parses cleanly via nlohmann::json::parse
    MtExchangeContract cContract = {
        "c-contract", "gRPC / C ABI", "C Contract", "fa-code", "inbound",
        "TCP", "127.0.0.1:9020", 9020, "Raw frame", "mesh", "summary", "c.proto",
        nullptr, 0, nullptr, 0, "wire", "line1\n\"quoted\""
    };
    MtContractsEnvelope cEnv = {
        "c_service", "0.0.1", 1, 1, nullptr, "c_test", &cContract, 1
    };
    char* rawCJson = mt_contracts_envelope_to_json(&cEnv);
    assert(rawCJson != nullptr);
    auto cParsed = nlohmann::json::parse(rawCJson);
    mt_spec_free_string(rawCJson);
    assert(cParsed["service"] == "c_service");
    assert(cParsed["reliable"] == true);
    assert(cParsed["contracts"][0]["schema"] == "line1\n\"quoted\"");

    std::cout << "  Passed (ExchangeContract, Extractors, BuildSpecFromConfig & C ABI JSON verified)." << std::endl;
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
        test_exchange_contracts_and_extractors();

        std::cout << "\n=======================================" << std::endl;
        std::cout << "  All C++ Spec Tests Passed!" << std::endl;
        std::cout << "=======================================\n" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "\n!!! TEST FAILED: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
