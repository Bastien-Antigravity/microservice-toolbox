#ifndef MICROSERVICE_TOOLBOX_SPEC_CONTRACTS_HPP
#define MICROSERVICE_TOOLBOX_SPEC_CONTRACTS_HPP

/*
 * ESSENTIAL PROCESS:
 * C++17 Exchange Contract data models, JSON serializers, and schema introspection
 * extractors (.proto IDL and Cap'n Proto) matching the Go, Python, and Rust
 * microservice-toolbox contract APIs 1:1.
 *
 * DATA FLOW:
 * 1. Input: Microservice-embedded .proto/.capnp schemas or manually built
 *    ExchangeContract descriptors.
 * 2. Logic: Extracts RPC/STRUCT/ENUM operations, normalizes endpoints, formats
 *    UTC RFC3339 timestamps, and packages ContractsEnvelope payloads.
 * 3. Output: Serialized JSON for GET /api/v1/contracts and ServiceSpec.contracts.
 *
 * KEY PARAMETERS:
 * - ExchangeContract: Single typed protocol/channel contract rendered as a tab.
 * - ContractsEnvelope: Canonical HTTP JSON payload returned by microservices.
 */

#include <algorithm>
#include <cctype>
#include <chrono>
#include <ctime>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "contracts.h"
#include "../config/json.hpp"

namespace microservice_toolbox {
namespace spec {

// -----------------------------------------------------------------------------

namespace detail {

inline std::string TrimStr(const std::string& s) {
    size_t start = 0;
    while (start < s.size() && std::isspace(static_cast<unsigned char>(s[start]))) {
        ++start;
    }
    size_t end = s.size();
    while (end > start && std::isspace(static_cast<unsigned char>(s[end - 1]))) {
        --end;
    }
    return s.substr(start, end - start);
}

inline std::vector<std::string> CompactNonCommentLines(const std::string& block, char commentChar) {
    std::vector<std::string> out;
    std::istringstream iss(block);
    std::string line;
    while (std::getline(iss, line)) {
        size_t cpos = line.find(commentChar);
        if (cpos != std::string::npos) {
            line = line.substr(0, cpos);
        }
        std::string trimmed = TrimStr(line);
        if (trimmed.empty()) continue;
        if (!trimmed.empty() && trimmed.back() == ';') {
            trimmed.pop_back();
            trimmed = TrimStr(trimmed);
        }
        if (!trimmed.empty()) {
            out.push_back(trimmed);
        }
    }
    return out;
}

inline std::string JoinStrings(const std::vector<std::string>& items, const std::string& sep) {
    std::string out;
    for (size_t i = 0; i < items.size(); ++i) {
        if (i > 0) out += sep;
        out += items[i];
    }
    return out;
}

inline bool FindMatchingBraceBlock(const std::string& text, size_t openPos, size_t& closePosOut) {
    if (openPos >= text.size() || text[openPos] != '{') return false;
    int depth = 0;
    for (size_t i = openPos; i < text.size(); ++i) {
        if (text[i] == '{') {
            ++depth;
        } else if (text[i] == '}') {
            --depth;
            if (depth == 0) {
                closePosOut = i;
                return true;
            }
        }
    }
    return false;
}

inline bool IsIdentChar(char c) {
    return std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '.';
}

inline std::string ParseStreamingType(const std::string& raw, bool& isStream) {
    std::string t = TrimStr(raw);
    isStream = false;
    const std::string prefix = "stream";
    if (t.size() > prefix.size() && t.compare(0, prefix.size(), prefix) == 0 &&
        std::isspace(static_cast<unsigned char>(t[prefix.size()]))) {
        isStream = true;
        t = TrimStr(t.substr(prefix.size()));
    }
    return t;
}

} // namespace detail

// -----------------------------------------------------------------------------

/**
 * ContractPeer identifies a collaborating microservice participating in an exchange contract.
 */
struct ContractPeer {
    std::string service;
    std::string role;
    std::string description;

    nlohmann::json ToJson() const {
        nlohmann::json j = {
            {"service", service},
            {"role", role}
        };
        if (!description.empty()) {
            j["description"] = description;
        }
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static ContractPeer FromJson(const nlohmann::json& j) {
        ContractPeer p;
        p.service = j.value("service", "");
        p.role = j.value("role", "");
        p.description = j.value("description", "");
        return p;
    }
};

// -----------------------------------------------------------------------------

/**
 * ContractOperation describes an individual endpoint, RPC, subject, table, frame, or tool.
 */
struct ContractOperation {
    std::string name;
    std::string kind;
    std::string target;
    std::string input;
    std::string output;
    std::string description;

    nlohmann::json ToJson() const {
        nlohmann::json j = {
            {"name", name},
            {"kind", kind},
            {"target", target}
        };
        if (!input.empty()) j["input"] = input;
        if (!output.empty()) j["output"] = output;
        if (!description.empty()) j["description"] = description;
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static ContractOperation FromJson(const nlohmann::json& j) {
        ContractOperation op;
        op.name = j.value("name", "");
        op.kind = j.value("kind", "");
        op.target = j.value("target", "");
        op.input = j.value("input", "");
        op.output = j.value("output", "");
        op.description = j.value("description", "");
        return op;
    }
};

// -----------------------------------------------------------------------------

/**
 * ExchangeContract represents a single exhaustive communication contract type for a microservice.
 */
struct ExchangeContract {
    std::string id;
    std::string type;
    std::string tabLabel;
    std::string icon{"fa-exchange"};
    std::string direction{"inbound"};
    std::string transport;
    std::string address;
    int port{0};
    std::string framing;
    std::string auth;
    std::string summary;
    std::string source;
    std::vector<ContractPeer> peers;
    std::vector<ContractOperation> operations;
    std::string schemaFormat;
    std::string schema;

    nlohmann::json ToJson() const {
        nlohmann::json j = {
            {"id", id},
            {"type", type}
        };
        if (!tabLabel.empty()) j["tabLabel"] = tabLabel;
        if (!icon.empty()) j["icon"] = icon;
        if (!direction.empty()) j["direction"] = direction;
        if (!transport.empty()) j["transport"] = transport;
        if (!address.empty()) j["address"] = address;
        if (port > 0) j["port"] = port;
        if (!framing.empty()) j["framing"] = framing;
        if (!auth.empty()) j["auth"] = auth;
        if (!summary.empty()) j["summary"] = summary;
        if (!source.empty()) j["source"] = source;
        if (!peers.empty()) {
            nlohmann::json arr = nlohmann::json::array();
            for (const auto& p : peers) arr.push_back(p.ToJson());
            j["peers"] = arr;
        }
        if (!operations.empty()) {
            nlohmann::json arr = nlohmann::json::array();
            for (const auto& op : operations) arr.push_back(op.ToJson());
            j["operations"] = arr;
        }
        if (!schemaFormat.empty()) j["schemaFormat"] = schemaFormat;
        if (!schema.empty()) j["schema"] = schema;
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static ExchangeContract FromJson(const nlohmann::json& j) {
        ExchangeContract c;
        c.id = j.value("id", "");
        c.type = j.value("type", "");
        c.tabLabel = j.value("tabLabel", "");
        c.icon = j.value("icon", "");
        c.direction = j.value("direction", "");
        c.transport = j.value("transport", "");
        c.address = j.value("address", "");
        c.port = j.value("port", 0);
        c.framing = j.value("framing", "");
        c.auth = j.value("auth", "");
        c.summary = j.value("summary", "");
        c.source = j.value("source", "");
        if (j.contains("peers") && j["peers"].is_array()) {
            for (const auto& item : j["peers"]) {
                c.peers.push_back(ContractPeer::FromJson(item));
            }
        }
        if (j.contains("operations") && j["operations"].is_array()) {
            for (const auto& item : j["operations"]) {
                c.operations.push_back(ContractOperation::FromJson(item));
            }
        }
        c.schemaFormat = j.value("schemaFormat", "");
        c.schema = j.value("schema", "");
        return c;
    }
};

// -----------------------------------------------------------------------------

/**
 * ContractsEnvelope is the standard HTTP JSON response payload for GET /api/v1/contracts.
 */
struct ContractsEnvelope {
    std::string service;
    std::string version{"0.0.1"};
    bool reliable{true};
    bool exhaustive{true};
    std::string generatedAt;
    std::string source;
    std::vector<ExchangeContract> contracts;

    nlohmann::json ToJson() const {
        nlohmann::json arr = nlohmann::json::array();
        for (const auto& c : contracts) {
            arr.push_back(c.ToJson());
        }
        nlohmann::json j = {
            {"service", service},
            {"reliable", reliable},
            {"exhaustive", exhaustive},
            {"generatedAt", generatedAt},
            {"source", source},
            {"contracts", arr}
        };
        if (!version.empty()) {
            j["version"] = version;
        }
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static ContractsEnvelope FromJson(const nlohmann::json& j) {
        ContractsEnvelope env;
        env.service = j.value("service", "");
        env.version = j.value("version", "");
        env.reliable = j.value("reliable", false);
        env.exhaustive = j.value("exhaustive", false);
        env.generatedAt = j.value("generatedAt", "");
        env.source = j.value("source", "");
        if (j.contains("contracts") && j["contracts"].is_array()) {
            for (const auto& item : j["contracts"]) {
                env.contracts.push_back(ExchangeContract::FromJson(item));
            }
        }
        return env;
    }
};

// -----------------------------------------------------------------------------

inline int ResolveContractPort(const std::string& addr) {
    return mt_resolve_contract_port(addr.c_str());
}

inline int resolveContractPort(const std::string& addr) {
    return ResolveContractPort(addr);
}

inline int resolve_contract_port(const std::string& addr) {
    return ResolveContractPort(addr);
}

inline std::string DisplayAddress(const std::string& addr) {
    char buf[512];
    mt_display_address(addr.c_str(), buf, sizeof(buf));
    return std::string(buf);
}

inline std::string displayAddress(const std::string& addr) {
    return DisplayAddress(addr);
}

inline std::string display_address(const std::string& addr) {
    return DisplayAddress(addr);
}

inline std::string CurrentUtcTimestampIso8601() {
    char buf[32];
    if (mt_utc_timestamp_iso8601(buf, sizeof(buf)) == 0) {
        return std::string(buf);
    }
    return "1970-01-01T00:00:00Z";
}

inline std::string ReadSchemaFile(const std::string& filePath) {
    std::ifstream ifs(filePath);
    if (!ifs.is_open()) return "";
    std::ostringstream oss;
    oss << ifs.rdbuf();
    return oss.str();
}

inline std::string readSchemaFile(const std::string& filePath) {
    return ReadSchemaFile(filePath);
}

inline std::string read_schema_file(const std::string& filePath) {
    return ReadSchemaFile(filePath);
}

// -----------------------------------------------------------------------------

inline ContractsEnvelope NewContractsEnvelope(
    const std::string& service,
    const std::string& version,
    const std::string& source,
    const std::vector<ExchangeContract>& contracts) {
    ContractsEnvelope env;
    env.service = service;
    env.version = detail::TrimStr(version).empty() ? "0.0.1" : detail::TrimStr(version);
    env.reliable = true;
    env.exhaustive = true;
    env.generatedAt = CurrentUtcTimestampIso8601();
    env.source = detail::TrimStr(source).empty() ? (service + " runtime") : source;
    env.contracts = contracts;
    return env;
}

inline ContractsEnvelope BuildContractsEnvelope(
    const std::string& service,
    const std::string& version,
    const std::string& source,
    const std::vector<ExchangeContract>& contracts) {
    return NewContractsEnvelope(service, version, source, contracts);
}

inline ContractsEnvelope build_contracts_envelope(
    const std::string& service,
    const std::string& version,
    const std::string& source,
    const std::vector<ExchangeContract>& contracts) {
    return NewContractsEnvelope(service, version, source, contracts);
}

// -----------------------------------------------------------------------------

/**
 * ExtractProtoTextOperations parses RPC declarations directly from an embedded .proto file.
 */
inline std::vector<ContractOperation> ExtractProtoTextOperations(const std::string& protoText) {
    std::vector<ContractOperation> ops;
    if (protoText.empty()) return ops;

    // 1. Resolve package prefix if declared.
    std::string pkgPrefix;
    {
        std::istringstream iss(protoText);
        std::string line;
        while (std::getline(iss, line)) {
            size_t cpos = line.find("//");
            if (cpos != std::string::npos) line = line.substr(0, cpos);
            std::string t = detail::TrimStr(line);
            if (t.compare(0, 7, "package") == 0 && (t.size() > 7 && std::isspace(static_cast<unsigned char>(t[7])))) {
                size_t semi = t.find(';');
                if (semi != std::string::npos) {
                    std::string pkg = detail::TrimStr(t.substr(7, semi - 7));
                    if (!pkg.empty()) pkgPrefix = pkg + ".";
                    break;
                }
            }
        }
    }

    // 2. Scan top-level "service <Name> { ... }" blocks.
    size_t pos = 0;
    while (pos < protoText.size()) {
        size_t kw = protoText.find("service", pos);
        if (kw == std::string::npos) break;
        bool boundaryBefore = (kw == 0 || !detail::IsIdentChar(protoText[kw - 1]));
        bool boundaryAfter = (kw + 7 < protoText.size() && std::isspace(static_cast<unsigned char>(protoText[kw + 7])));
        if (!boundaryBefore || !boundaryAfter) {
            pos = kw + 7;
            continue;
        }
        size_t nameStart = kw + 7;
        while (nameStart < protoText.size() && std::isspace(static_cast<unsigned char>(protoText[nameStart]))) ++nameStart;
        size_t nameEnd = nameStart;
        while (nameEnd < protoText.size() && detail::IsIdentChar(protoText[nameEnd])) ++nameEnd;
        std::string svcName = protoText.substr(nameStart, nameEnd - nameStart);
        size_t braceOpen = protoText.find('{', nameEnd);
        if (svcName.empty() || braceOpen == std::string::npos) {
            pos = nameEnd + 1;
            continue;
        }
        size_t braceClose = 0;
        if (!detail::FindMatchingBraceBlock(protoText, braceOpen, braceClose)) {
            break;
        }
        std::string body = protoText.substr(braceOpen + 1, braceClose - braceOpen - 1);

        // 3. Scan "rpc <Name>(<Req>) returns (<Resp>)" within the service body.
        size_t rpos = 0;
        while (rpos < body.size()) {
            size_t rkw = body.find("rpc", rpos);
            if (rkw == std::string::npos) break;
            bool rBefore = (rkw == 0 || !detail::IsIdentChar(body[rkw - 1]));
            bool rAfter = (rkw + 3 < body.size() && std::isspace(static_cast<unsigned char>(body[rkw + 3])));
            if (!rBefore || !rAfter) {
                rpos = rkw + 3;
                continue;
            }
            size_t rNameStart = rkw + 3;
            while (rNameStart < body.size() && std::isspace(static_cast<unsigned char>(body[rNameStart]))) ++rNameStart;
            size_t rNameEnd = rNameStart;
            while (rNameEnd < body.size() && detail::IsIdentChar(body[rNameEnd])) ++rNameEnd;
            std::string rpcName = body.substr(rNameStart, rNameEnd - rNameStart);

            size_t inOpen = body.find('(', rNameEnd);
            size_t inClose = (inOpen != std::string::npos) ? body.find(')', inOpen + 1) : std::string::npos;
            size_t retKw = (inClose != std::string::npos) ? body.find("returns", inClose + 1) : std::string::npos;
            size_t outOpen = (retKw != std::string::npos) ? body.find('(', retKw + 7) : std::string::npos;
            size_t outClose = (outOpen != std::string::npos) ? body.find(')', outOpen + 1) : std::string::npos;
            if (rpcName.empty() || inOpen == std::string::npos || inClose == std::string::npos ||
                retKw == std::string::npos || outOpen == std::string::npos || outClose == std::string::npos) {
                rpos = rkw + 3;
                continue;
            }

            bool inStream = false;
            bool outStream = false;
            std::string inType = detail::ParseStreamingType(body.substr(inOpen + 1, inClose - inOpen - 1), inStream);
            std::string outType = detail::ParseStreamingType(body.substr(outOpen + 1, outClose - outOpen - 1), outStream);

            std::string kind = "RPC";
            if (inStream && outStream) {
                kind = "BIDI_STREAM";
            } else if (outStream) {
                kind = "SERVER_STREAM";
            } else if (inStream) {
                kind = "CLIENT_STREAM";
            }

            ContractOperation op;
            op.name = rpcName;
            op.kind = kind;
            op.target = pkgPrefix + svcName + "/" + rpcName;
            op.input = (inStream ? "stream " : "") + inType;
            op.output = (outStream ? "stream " : "") + outType;
            op.description = svcName + "." + rpcName;
            ops.push_back(op);

            rpos = outClose + 1;
        }

        pos = braceClose + 1;
    }

    return ops;
}

inline std::vector<ContractOperation> extractProtoTextOperations(const std::string& protoText) {
    return ExtractProtoTextOperations(protoText);
}

inline std::vector<ContractOperation> extract_proto_operations(const std::string& protoText) {
    return ExtractProtoTextOperations(protoText);
}

// -----------------------------------------------------------------------------

/**
 * ExtractCapnpOperations extracts enum and struct definitions from an embedded .capnp file.
 */
inline std::vector<ContractOperation> ExtractCapnpOperations(const std::string& capnpText) {
    std::vector<ContractOperation> ops;
    if (capnpText.empty()) return ops;

    auto extractBlocks = [&](const std::string& keyword, const std::string& opKind, const std::string& targetPrefix, bool isOutput, const std::string& desc) {
        size_t pos = 0;
        size_t kwLen = keyword.size();
        while (pos < capnpText.size()) {
            size_t kw = capnpText.find(keyword, pos);
            if (kw == std::string::npos) break;
            bool beforeOk = (kw == 0 || !detail::IsIdentChar(capnpText[kw - 1]));
            bool afterOk = (kw + kwLen < capnpText.size() && std::isspace(static_cast<unsigned char>(capnpText[kw + kwLen])));
            if (!beforeOk || !afterOk) {
                pos = kw + kwLen;
                continue;
            }
            size_t nStart = kw + kwLen;
            while (nStart < capnpText.size() && std::isspace(static_cast<unsigned char>(capnpText[nStart]))) ++nStart;
            size_t nEnd = nStart;
            while (nEnd < capnpText.size() && detail::IsIdentChar(capnpText[nEnd])) ++nEnd;
            std::string itemName = capnpText.substr(nStart, nEnd - nStart);
            size_t bOpen = capnpText.find('{', nEnd);
            if (itemName.empty() || bOpen == std::string::npos) {
                pos = nEnd + 1;
                continue;
            }
            size_t bClose = 0;
            if (!detail::FindMatchingBraceBlock(capnpText, bOpen, bClose)) {
                break;
            }
            std::string body = capnpText.substr(bOpen + 1, bClose - bOpen - 1);
            std::vector<std::string> lines = detail::CompactNonCommentLines(body, '#');

            ContractOperation op;
            op.name = itemName;
            op.kind = opKind;
            op.target = targetPrefix + itemName;
            if (isOutput) {
                op.output = detail::JoinStrings(lines, ", ");
            } else {
                op.input = detail::JoinStrings(lines, "; ");
            }
            op.description = desc;
            ops.push_back(op);

            pos = bClose + 1;
        }
    };

    extractBlocks("enum", "ENUM", "enum ", true, "Cap'n Proto enum definition");
    extractBlocks("struct", "STRUCT", "struct ", false, "Cap'n Proto wire struct definition");
    return ops;
}

inline std::vector<ContractOperation> extractCapnpOperations(const std::string& capnpText) {
    return ExtractCapnpOperations(capnpText);
}

inline std::vector<ContractOperation> extract_capnp_operations(const std::string& capnpText) {
    return ExtractCapnpOperations(capnpText);
}

} // namespace spec
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SPEC_CONTRACTS_HPP
