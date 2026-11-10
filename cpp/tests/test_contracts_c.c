/*
 * ESSENTIAL PROCESS:
 * Pure C11 unit tests for microservice_toolbox/spec/contracts.h.
 * Verifies C structs, address/port normalization, UTC timestamp generation,
 * and escaped RFC 8259 JSON serialization.
 *
 * DATA FLOW:
 * 1. Builds MtExchangeContract and MtContractsEnvelope values on the stack.
 * 2. Invokes mt_contracts_envelope_to_json and helper utilities.
 * 3. Asserts valid JSON structure, escaping, and memory cleanup.
 *
 * KEY PARAMETERS:
 * - None (Unit Test Suite).
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../include/microservice_toolbox/spec/contracts.h"

// -----------------------------------------------------------------------------

static void test_address_and_port_helpers(void) {
    char buf[128];

    assert(mt_resolve_contract_port("127.0.0.1:9021") == 9021);
    assert(mt_resolve_contract_port(":50051") == 50051);
    assert(mt_resolve_contract_port("no-port") == 0);
    assert(mt_resolve_contract_port(NULL) == 0);

    assert(strcmp(mt_display_address(NULL, buf, sizeof(buf)), "dynamic") == 0);
    assert(strcmp(mt_display_address(":3308", buf, sizeof(buf)), "127.0.0.1:3308") == 0);
    assert(strcmp(mt_display_address("0.0.0.0:1029", buf, sizeof(buf)), "127.0.0.1:1029") == 0);
    assert(strcmp(mt_display_address("10.0.0.5:8080", buf, sizeof(buf)), "10.0.0.5:8080") == 0);

    char ts[32];
    assert(mt_utc_timestamp_iso8601(ts, sizeof(ts)) == 0);
    assert(strlen(ts) == 20);
    assert(ts[10] == 'T' && ts[19] == 'Z');
}

// -----------------------------------------------------------------------------

static void test_c_contracts_envelope_json(void) {
    MtContractPeer peers[] = {
        {"web_interface", "consumer", "Displays live contract tabs"}
    };
    MtContractOperation ops[] = {
        {"Ping", "RPC", "demo.DemoService/Ping", "PingReq", "PingResp", "Health \"probe\"\nline2"}
    };
    MtExchangeContract contracts[] = {
        {
            .id = "grpc",
            .type = "gRPC / Protobuf",
            .tab_label = "gRPC Control",
            .icon = "fa-code",
            .direction = "inbound",
            .transport = "HTTP/2 + Protobuf",
            .address = "127.0.0.1:9021",
            .port = 9021,
            .framing = "gRPC frames",
            .auth = "Internal mesh",
            .summary = "Pure C contract test",
            .source = "demo.proto",
            .peers = peers,
            .peers_count = 1,
            .operations = ops,
            .operations_count = 1,
            .schema_format = "proto3",
            .schema = "syntax = \"proto3\";\nservice Demo {}"
        }
    };
    MtContractsEnvelope env = {
        .service = "c_demo_service",
        .version = "0.1.0",
        .reliable = 1,
        .exhaustive = 1,
        .generated_at = NULL,
        .source = "c_demo runtime",
        .contracts = contracts,
        .contracts_count = 1
    };

    char* json = mt_contracts_envelope_to_json(&env);
    assert(json != NULL);
    assert(strstr(json, "\"service\":\"c_demo_service\"") != NULL);
    assert(strstr(json, "\"reliable\":true") != NULL);
    assert(strstr(json, "\"exhaustive\":true") != NULL);
    assert(strstr(json, "\"tabLabel\":\"gRPC Control\"") != NULL);
    assert(strstr(json, "\"schemaFormat\":\"proto3\"") != NULL);
    assert(strstr(json, "\"port\":9021") != NULL);
    assert(strstr(json, "Health \\\"probe\\\"\\nline2") != NULL);
    assert(strstr(json, "syntax = \\\"proto3\\\";\\nservice Demo {}") != NULL);

    mt_spec_free_string(json);
}

// -----------------------------------------------------------------------------

int main(void) {
    printf("\n=======================================\n");
    printf("  Running Pure C Contracts Unit Tests\n");
    printf("=======================================\n");

    test_address_and_port_helpers();
    test_c_contracts_envelope_json();

    printf("  All Pure C Contract Tests Passed!\n\n");
    return 0;
}

