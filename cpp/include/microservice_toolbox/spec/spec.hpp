#ifndef MICROSERVICE_TOOLBOX_SPEC_HPP
#define MICROSERVICE_TOOLBOX_SPEC_HPP

/*
 * ESSENTIAL PROCESS:
 * Standardizes self-describing microservice specifications and dynamic
 * registration with web-interface across the Bastien-Antigravity fleet for C++.
 * Auto-resolves runtime listen/REST addresses, dynamic semver, host node,
 * canvas/health metadata, and documentation links from AppConfig.
 *
 * FAIL-FAST PRINCIPLE:
 * Zero silent fallbacks, zero default values, and zero dummy placeholders.
 * Microservices must explicitly declare their own specification metadata
 * (name, tag, layer, category, description, docLink, protocol, framing).
 * Configuration addresses (including web_interface) must resolve strictly;
 * missing capabilities, missing ports, or missing metadata FAIL FAST immediately.
 *
 * DATA FLOW:
 * 1. Microservice ServiceSpec + Capability Name -> Dynamic AppConfig Lookups
 * 2. Strict Fail-Fast Validation of all required fields & dynamic endpoints
 * 3. POST /api/v1/register with exponential backoff and randomized jitter
 *
 * KEY PARAMETERS:
 * - appConfig: Active AppConfig for capability host/port/version resolution.
 * - logger: Logger pointer for status logging and retry diagnostics.
 * - capability: Capability key in AppConfig e.g. "config_server".
 * - base: Microservice-provided ServiceSpec containing domain metadata.
 */

#include <atomic>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <sys/socket.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <unistd.h>
#endif

#include "../config/AppConfig.hpp"
#include "../config/json.hpp"
#include "../utils/Logger.hpp"
#include "../lifecycle/LifecycleManager.hpp"
#include "contracts.hpp"

namespace microservice_toolbox {
namespace spec {

namespace detail {

inline bool SendHttpRequest(const std::string& targetAddr, const std::string& payload) {
    auto colon = targetAddr.rfind(':');
    if (colon == std::string::npos) return false;
    std::string host = targetAddr.substr(0, colon);
    if (host.size() >= 2 && host.front() == '[' && host.back() == ']') {
        host = host.substr(1, host.size() - 2);
    }
    int port = 0;
    try {
        port = std::stoi(targetAddr.substr(colon + 1));
    } catch (...) {
        return false;
    }
    if (port <= 0) return false;

#if defined(_WIN32)
    static std::once_flag wsa_init;
    std::call_once(wsa_init, []() {
        WSADATA wsa;
        WSAStartup(MAKEWORD(2, 2), &wsa);
    });
#endif

    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    std::string portStr = std::to_string(port);
    if (getaddrinfo(host.c_str(), portStr.c_str(), &hints, &res) != 0 || !res) {
        return false;
    }

    int sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock < 0) {
        freeaddrinfo(res);
        return false;
    }

#if defined(_WIN32)
    DWORD tv = 3000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof(tv));
#else
    struct timeval tv{3, 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif

    if (connect(sock, res->ai_addr, res->ai_addrlen) != 0) {
        freeaddrinfo(res);
#if defined(_WIN32)
        closesocket(sock);
#else
        close(sock);
#endif
        return false;
    }
    freeaddrinfo(res);

    std::ostringstream req;
    req << "POST /api/v1/register HTTP/1.1\r\n"
        << "Host: " << targetAddr << "\r\n"
        << "Content-Type: application/json\r\n"
        << "Content-Length: " << payload.size() << "\r\n"
        << "Connection: close\r\n\r\n"
        << payload;
    std::string reqStr = req.str();

    size_t sent = 0;
    while (sent < reqStr.size()) {
        ssize_t n = send(sock, reqStr.c_str() + sent, reqStr.size() - sent, 0);
        if (n <= 0) break;
        sent += n;
    }

    char buf[1024];
    std::string resp;
    while (true) {
        ssize_t n = recv(sock, buf, sizeof(buf) - 1, 0);
        if (n <= 0) break;
        buf[n] = '\0';
        resp.append(buf, n);
    }

#if defined(_WIN32)
    closesocket(sock);
#else
    close(sock);
#endif

    return (resp.find(" 200 ") != std::string::npos || resp.find(" 201 ") != std::string::npos);
}

inline int JitteredBackoffMs(int delayMs) {
    static thread_local std::mt19937 rng{std::random_device{}()};
    int half = delayMs / 2;
    if (half <= 0) return delayMs;
    std::uniform_int_distribution<int> dist(0, half);
    return delayMs + dist(rng);
}

inline std::string CurrentHostname() {
    char hostBuf[256] = {0};
#if defined(_WIN32)
    const char* envHost = std::getenv("COMPUTERNAME");
    if (envHost && envHost[0] != '\0') return std::string(envHost);
#endif
    if (gethostname(hostBuf, sizeof(hostBuf) - 1) == 0 && hostBuf[0] != '\0') {
        return std::string(hostBuf);
    }
    return "";
}

} // namespace detail

// -----------------------------------------------------------------------------

/**
 * ProtocolSpec describes an exposed network protocol and port.
 */
struct ProtocolSpec {
    std::string type;
    int port{0};
    std::string framing;
    std::string description;

    nlohmann::json ToJson() const {
        return {
            {"type", type},
            {"port", port},
            {"framing", framing},
            {"description", description}
        };
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static ProtocolSpec FromJson(const nlohmann::json& j) {
        ProtocolSpec p;
        p.type = j.value("type", "");
        p.port = j.value("port", 0);
        p.framing = j.value("framing", "");
        p.description = j.value("description", "");
        return p;
    }

    static ProtocolSpec fromJson(const nlohmann::json& j) { return FromJson(j); }
    static ProtocolSpec from_json(const nlohmann::json& j) { return FromJson(j); }
};

// -----------------------------------------------------------------------------

/**
 * DependencySpec represents a declared downstream dependency of a microservice.
 */
struct DependencySpec {
    std::string target;
    std::string proto;
    std::string label;
    std::string exchangeId;
    std::string description;

    nlohmann::json ToJson() const {
        nlohmann::json j = {
            {"target", target},
            {"proto", proto}
        };
        if (!label.empty()) j["label"] = label;
        if (!exchangeId.empty()) j["exchangeId"] = exchangeId;
        if (!description.empty()) j["description"] = description;
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static DependencySpec FromJson(const nlohmann::json& j) {
        DependencySpec d;
        d.target = j.value("target", "");
        d.proto = j.value("proto", "");
        d.label = j.value("label", "");
        d.exchangeId = j.value("exchangeId", "");
        d.description = j.value("description", "");
        return d;
    }

    static DependencySpec fromJson(const nlohmann::json& j) { return FromJson(j); }
    static DependencySpec from_json(const nlohmann::json& j) { return FromJson(j); }
};

// -----------------------------------------------------------------------------

/**
 * HealthSpec standardizes declarative health check and reachability probes.
 */
struct HealthSpec {
    std::string type;
    int port{0};
    std::string path;
    int timeoutMs{0};

    nlohmann::json ToJson() const {
        nlohmann::json j = nlohmann::json::object();
        if (!type.empty()) j["type"] = type;
        if (port > 0) j["port"] = port;
        if (!path.empty()) j["path"] = path;
        if (timeoutMs > 0) j["timeoutMs"] = timeoutMs;
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static HealthSpec FromJson(const nlohmann::json& j) {
        HealthSpec h;
        h.type = j.value("type", "");
        h.port = j.value("port", 0);
        h.path = j.value("path", "");
        h.timeoutMs = j.value("timeoutMs", 0);
        return h;
    }

    static HealthSpec fromJson(const nlohmann::json& j) { return FromJson(j); }
    static HealthSpec from_json(const nlohmann::json& j) { return FromJson(j); }
};

// -----------------------------------------------------------------------------

/**
 * CanvasSpec declares presentation attributes for the transport SVG mesh canvas and UI tiers.
 */
struct CanvasSpec {
    std::string icon;
    std::string color;
    std::string preferredSlot;
    double preferredX{0.0};
    double preferredY{0.0};
    std::vector<std::string> particleProto;

    bool IsEmpty() const {
        return icon.empty() && color.empty() && preferredSlot.empty() &&
               preferredX == 0.0 && preferredY == 0.0 && particleProto.empty();
    }

    nlohmann::json ToJson() const {
        nlohmann::json j = nlohmann::json::object();
        if (!icon.empty()) j["icon"] = icon;
        if (!color.empty()) j["color"] = color;
        if (!preferredSlot.empty()) j["preferredSlot"] = preferredSlot;
        if (preferredX > 0.0) j["preferredX"] = preferredX;
        if (preferredY > 0.0) j["preferredY"] = preferredY;
        if (!particleProto.empty()) j["particleProto"] = particleProto;
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static CanvasSpec FromJson(const nlohmann::json& j) {
        CanvasSpec c;
        c.icon = j.value("icon", "");
        c.color = j.value("color", "");
        c.preferredSlot = j.value("preferredSlot", "");
        c.preferredX = j.value("preferredX", 0.0);
        c.preferredY = j.value("preferredY", 0.0);
        if (j.contains("particleProto") && j["particleProto"].is_array()) {
            c.particleProto = j["particleProto"].get<std::vector<std::string>>();
        }
        return c;
    }

    static CanvasSpec fromJson(const nlohmann::json& j) { return FromJson(j); }
    static CanvasSpec from_json(const nlohmann::json& j) { return FromJson(j); }
};

// -----------------------------------------------------------------------------

/**
 * ServiceSpec is the canonical specification of a microservice.
 * Microservices must explicitly provide their own domain metadata; zero dummy defaults are permitted.
 */
namespace detail {
inline bool IsDockerInternalHost(const std::string& host) {
    std::string trimmed = detail::TrimStr(host);
    if (trimmed.size() >= 2 && trimmed.front() == '[' && trimmed.back() == ']') {
        trimmed = trimmed.substr(1, trimmed.size() - 2);
    }
    if (trimmed.empty() || trimmed == "0.0.0.0" || trimmed == "::") {
        return true;
    }
    std::string lower = trimmed;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (lower == "localhost") {
        return false;
    }
    if (trimmed.find(':') != std::string::npos) {
        return false; // IPv6 literal
    }
    // Check IPv4 dotted quad
    bool all_ipv4_chars = !trimmed.empty();
    int dots = 0;
    for (unsigned char ch : trimmed) {
        if (ch == '.') {
            dots++;
        } else if (!std::isdigit(ch)) {
            all_ipv4_chars = false;
            break;
        }
    }
    if (all_ipv4_chars && dots == 3) {
        return false;
    }
    return trimmed.find('.') == std::string::npos;
}
} // namespace detail

/**
 * ResolveMFEURL rewrites wildcard (0.0.0.0, ::, empty) or single-label Docker DNS hosts
 * to a browser-reachable host from HOST_IP or appConfig.GetPublicIP() when DOCKER_ENV=true.
 */
inline std::string ResolveMFEURL(const config::AppConfig& appConfig, const std::string& rawUrl) {
    std::string trimmed = detail::TrimStr(rawUrl);
    const char* dockerEnv = std::getenv("DOCKER_ENV");
    if (trimmed.empty() || !dockerEnv || std::string(dockerEnv) != "true") {
        return rawUrl;
    }
    std::string lowerPrefix = trimmed.substr(0, std::min<size_t>(trimmed.size(), 8));
    std::transform(lowerPrefix.begin(), lowerPrefix.end(), lowerPrefix.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    size_t schemeEnd = std::string::npos;
    if (lowerPrefix.rfind("http://", 0) == 0) {
        schemeEnd = 7;
    } else if (lowerPrefix.rfind("https://", 0) == 0) {
        schemeEnd = 8;
    } else {
        return rawUrl;
    }

    size_t pathStart = trimmed.find_first_of("/?#", schemeEnd);
    std::string authority = (pathStart == std::string::npos)
                                ? trimmed.substr(schemeEnd)
                                : trimmed.substr(schemeEnd, pathStart - schemeEnd);
    std::string suffix = (pathStart == std::string::npos) ? "" : trimmed.substr(pathStart);
    if (authority.empty()) {
        return rawUrl;
    }

    std::string hostname = authority;
    std::string port;
    if (authority.front() == '[') {
        size_t closeBracket = authority.find(']');
        if (closeBracket == std::string::npos) {
            return rawUrl;
        }
        hostname = authority.substr(1, closeBracket - 1);
        if (closeBracket + 1 < authority.size() && authority[closeBracket + 1] == ':') {
            port = authority.substr(closeBracket + 2);
        }
    } else {
        size_t colon = authority.rfind(':');
        if (colon != std::string::npos) {
            hostname = authority.substr(0, colon);
            port = authority.substr(colon + 1);
        }
    }

    if (!detail::IsDockerInternalHost(hostname)) {
        return rawUrl;
    }

    std::string publicHost;
    if (const char* envHost = std::getenv("HOST_IP")) {
        publicHost = detail::TrimStr(std::string(envHost));
    }
    if (publicHost.empty()) {
        publicHost = detail::TrimStr(appConfig.GetPublicIP());
    }
    if (publicHost.empty() || publicHost == "0.0.0.0" || publicHost == "::") {
        return rawUrl;
    }

    std::string formattedHost = (publicHost.find(':') != std::string::npos && publicHost.front() != '[')
                                    ? ("[" + publicHost + "]")
                                    : publicHost;
    std::string newAuthority = port.empty() ? formattedHost : (formattedHost + ":" + port);
    return trimmed.substr(0, schemeEnd) + newAuthority + suffix;
}

struct ServiceSpec {
    std::string name;
    std::string tag;
    std::string url;
    std::string navTitle;
    std::string layer;
    std::string category;
    int priority{100};
    std::string icon{"fa-cubes"};
    std::string color;
    bool requiresAuth{false};
    std::string capability;
    std::string brainId;
    std::string description;
    std::string protocol;
    std::string framing;
    std::string docLink;
    std::string navRoute;
    std::optional<HealthSpec> health;
    std::optional<CanvasSpec> canvas;
    std::vector<DependencySpec> dependencies;
    std::vector<ProtocolSpec> protocols;
    std::vector<ExchangeContract> contracts;
    std::vector<std::string> flowDiagram;
    nlohmann::json dataStructure = nlohmann::json::object();
    std::string sdkLang{"language-cpp"};
    std::string sourceCode;

    nlohmann::json ToJson() const {
        nlohmann::json j = {
            {"name", name},
            {"tag", tag},
            {"url", url},
            {"navTitle", navTitle.empty() ? name : navTitle},
            {"layer", layer},
            {"category", category},
            {"priority", priority},
            {"icon", icon},
            {"requiresAuth", requiresAuth},
            {"capability", capability},
            {"desc", description},
            {"protocol", protocol},
            {"framing", framing},
            {"docLink", docLink},
            {"flowDiagram", flowDiagram},
            {"dataStructure", dataStructure},
            {"sdkLang", sdkLang},
            {"sourceCode", sourceCode}
        };
        if (!color.empty()) {
            j["color"] = color;
        }
        if (!detail::TrimStr(brainId).empty()) {
            j["brain_id"] = detail::TrimStr(brainId);
        }
        if (!navRoute.empty()) {
            j["navRoute"] = navRoute;
        }
        if (health.has_value()) {
            j["health"] = health->ToJson();
        }
        if (canvas.has_value() && !canvas->IsEmpty()) {
            j["canvas"] = canvas->ToJson();
        }
        if (!dependencies.empty()) {
            nlohmann::json depArr = nlohmann::json::array();
            for (const auto& d : dependencies) {
                depArr.push_back(d.ToJson());
            }
            j["dependencies"] = depArr;
        }
        if (!protocols.empty()) {
            nlohmann::json protoArr = nlohmann::json::array();
            for (const auto& p : protocols) {
                protoArr.push_back(p.ToJson());
            }
            j["protocols"] = protoArr;
        }
        if (!contracts.empty()) {
            nlohmann::json contractArr = nlohmann::json::array();
            for (const auto& c : contracts) {
                contractArr.push_back(c.ToJson());
            }
            j["contracts"] = contractArr;
        }
        return j;
    }

    nlohmann::json toJson() const { return ToJson(); }
    nlohmann::json to_json() const { return ToJson(); }

    static ServiceSpec FromJson(const nlohmann::json& j) {
        ServiceSpec s;
        s.name = j.value("name", "");
        s.tag = j.value("tag", "");
        s.url = j.value("url", "");
        s.navTitle = j.value("navTitle", "");
        s.layer = j.value("layer", "");
        s.category = j.value("category", "");
        s.priority = j.value("priority", 100);
        s.icon = j.value("icon", "fa-cubes");
        s.color = j.value("color", "");
        s.requiresAuth = j.value("requiresAuth", false);
        s.capability = j.value("capability", "");
        s.brainId = j.value("brain_id", "");
        s.description = j.value("desc", j.value("description", ""));
        s.protocol = j.value("protocol", "");
        s.framing = j.value("framing", "");
        s.docLink = j.value("docLink", "");
        s.navRoute = j.value("navRoute", "");
        if (j.contains("health") && j["health"].is_object()) {
            s.health = HealthSpec::FromJson(j["health"]);
        }
        if (j.contains("canvas") && j["canvas"].is_object()) {
            s.canvas = CanvasSpec::FromJson(j["canvas"]);
        }
        if (j.contains("dependencies") && j["dependencies"].is_array()) {
            for (const auto& item : j["dependencies"]) {
                s.dependencies.push_back(DependencySpec::FromJson(item));
            }
        }
        if (j.contains("protocols") && j["protocols"].is_array()) {
            for (const auto& item : j["protocols"]) {
                s.protocols.push_back(ProtocolSpec::FromJson(item));
            }
        }
        if (j.contains("contracts") && j["contracts"].is_array()) {
            for (const auto& item : j["contracts"]) {
                s.contracts.push_back(ExchangeContract::FromJson(item));
            }
        }
        if (j.contains("flowDiagram") && j["flowDiagram"].is_array()) {
            s.flowDiagram = j["flowDiagram"].get<std::vector<std::string>>();
        }
        if (j.contains("dataStructure") && j["dataStructure"].is_object()) {
            s.dataStructure = j["dataStructure"];
        }
        s.sdkLang = j.value("sdkLang", "language-cpp");
        s.sourceCode = j.value("sourceCode", "");
        return s;
    }

    static ServiceSpec fromJson(const nlohmann::json& j) { return FromJson(j); }
    static ServiceSpec from_json(const nlohmann::json& j) { return FromJson(j); }
};

// -----------------------------------------------------------------------------

/**
 * SpecPublisher handles dynamic specification validation, enrichment, and fail-fast publishing.
 */
class SpecPublisher {
public:
    /**
     * BuildSpecFromConfig validates and enriches a ServiceSpec using dynamic parameters from AppConfig.
     * FAIL-FAST: Strictly validates all required metadata and dynamic endpoints with zero fallbacks.
     */
    static ServiceSpec BuildSpecFromConfig(const config::AppConfig& appConfig, const std::string& capability, const ServiceSpec& base) {
        std::string cap = contracts_detail_trim(capability);
        if (cap.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: capability name is strictly required (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.name).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'name' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.tag).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'tag' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.layer).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'layer' (L1|L2|L3) is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.category).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'category' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.description).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'description' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.docLink).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'docLink' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.protocol).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'protocol' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }
        if (contracts_detail_trim(base.framing).empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'framing' is strictly required for capability '" + cap + "' (FAIL-FAST)");
        }

        ServiceSpec spec = base;
        spec.capability = cap;
        if (contracts_detail_trim(spec.brainId).empty()) {
            std::string b = contracts_detail_trim(appConfig.GetCapabilityString("squad_agent", "target_brain_id"));
            if (b.empty()) b = contracts_detail_trim(appConfig.GetCapabilityString("watchdog_agent", "brain_id"));
            if (b.empty()) {
                if (const char* envBrain = std::getenv("BRAIN_ID")) b = contracts_detail_trim(std::string(envBrain));
            }
            if (b.empty()) {
                if (const char* envTarget = std::getenv("TARGET_BRAIN_ID")) b = contracts_detail_trim(std::string(envTarget));
            }
            spec.brainId = b;
        } else {
            spec.brainId = contracts_detail_trim(spec.brainId);
        }
        if (contracts_detail_trim(spec.navTitle).empty()) {
            spec.navTitle = spec.name;
        }
        if (contracts_detail_trim(spec.icon).empty()) {
            spec.icon = "fa-cubes";
        }
        if (contracts_detail_trim(spec.sdkLang).empty()) {
            spec.sdkLang = "language-cpp";
        }

        std::string listenAddr;
        try { listenAddr = appConfig.GetListenAddr(cap); } catch (...) {}
        std::string restAddr;
        try { restAddr = appConfig.GetRESTAddr(cap); } catch (...) {}
        std::string grpcAddr;
        try { grpcAddr = appConfig.GetGRPCListenAddr(cap); } catch (...) {}

        auto extractPort = [](const std::string& addr) -> std::string {
            auto idx = addr.rfind(':');
            return (idx != std::string::npos) ? addr.substr(idx + 1) : "";
        };

        std::string tcpPort = extractPort(listenAddr);
        std::string restPort = extractPort(restAddr);
        std::string grpcPort = extractPort(grpcAddr);

        if (contracts_detail_trim(spec.url).empty()) {
            if (!restAddr.empty()) {
                spec.url = "http://" + restAddr;
            } else if (!listenAddr.empty()) {
                spec.url = "http://" + listenAddr;
            } else {
                throw std::runtime_error("spec.BuildSpecFromConfig: unable to resolve URL for capability '" + cap + "' (FAIL-FAST)");
            }
        }
        spec.url = ResolveMFEURL(appConfig, spec.url);

        // Framing port interpolation
        if (spec.framing.find("%s") != std::string::npos) {
            std::vector<std::string> available;
            if (!tcpPort.empty()) available.push_back(tcpPort);
            if (!restPort.empty()) available.push_back(restPort);
            if (!grpcPort.empty()) available.push_back(grpcPort);

            size_t count = 0;
            size_t pos = 0;
            while ((pos = spec.framing.find("%s", pos)) != std::string::npos) {
                count++;
                pos += 2;
            }

            if (available.size() < count) {
                throw std::runtime_error("spec.BuildSpecFromConfig: framing requires " + std::to_string(count) + " port(s) for capability '" + cap + "' (FAIL-FAST)");
            }

            for (size_t i = 0; i < count; ++i) {
                size_t p = spec.framing.find("%s");
                if (p != std::string::npos) {
                    spec.framing.replace(p, 2, available[i]);
                }
            }
        }

        std::string ver = appConfig.GetVersion();
        if (contracts_detail_trim(ver).empty()) {
            throw std::runtime_error("spec.BuildSpecFromConfig: dynamic version resolution returned empty string (FAIL-FAST)");
        }

        if (!spec.dataStructure.is_object()) {
            spec.dataStructure = nlohmann::json::object();
        }
        spec.dataStructure["version"] = ver;
        spec.dataStructure["capability"] = cap;

        nlohmann::json portsJson = nlohmann::json::object();
        if (!tcpPort.empty()) portsJson["tcp"] = tcpPort;
        if (!restPort.empty()) portsJson["rest"] = restPort;
        if (!grpcPort.empty()) portsJson["grpc"] = grpcPort;
        if (!portsJson.empty()) {
            spec.dataStructure["ports"] = portsJson;
        }

        std::string host = detail::CurrentHostname();
        if (!host.empty()) {
            spec.dataStructure["node"] = host;
        }

        if (contracts_detail_trim(spec.navRoute).empty()) {
            spec.navRoute = "/mfe/" + spec.name;
        }

        CanvasSpec cv = spec.canvas.value_or(CanvasSpec{});
        if (spec.color.empty() && !cv.color.empty()) {
            spec.color = cv.color;
        } else if (cv.color.empty() && !spec.color.empty()) {
            cv.color = spec.color;
        }
        if (cv.icon.empty() && !spec.icon.empty()) {
            cv.icon = spec.icon;
        }
        spec.canvas = cv;

        HealthSpec hs = spec.health.value_or(HealthSpec{});
        if (hs.type.empty()) {
            hs.type = "tcp";
        }
        if (hs.port == 0) {
            for (const auto& pStr : {restPort, tcpPort, grpcPort}) {
                if (!pStr.empty()) {
                    try {
                        int n = std::stoi(pStr);
                        if (n > 0) {
                            hs.port = n;
                            break;
                        }
                    } catch (...) {}
                }
            }
        }
        if (hs.timeoutMs == 0) {
            hs.timeoutMs = 350;
        }
        spec.health = hs;

        return spec;
    }

    static ServiceSpec buildSpecFromConfig(const config::AppConfig& appConfig, const std::string& capability, const ServiceSpec& base) {
        return BuildSpecFromConfig(appConfig, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * PublishSync validates web_interface and spec synchronously (FAIL-FAST).
     * When maxWaitMs == 0 (default), performs a single delivery attempt matching fast unit tests.
     * When maxWaitMs > 0 (or < 0 for infinite), retries with 500ms..30s exponential backoff and jitter.
     */
    static bool PublishSync(
        const config::AppConfig& appConfig,
        std::shared_ptr<utils::Logger> logger,
        const std::string& capability,
        const ServiceSpec& base,
        int maxWaitMs = 0,
        std::shared_ptr<std::atomic<bool>> stopFlag = nullptr) {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (contracts_detail_trim(webAddr).empty()) {
            if (logger) {
                logger->Critical("spec.PublishSync: Capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
            }
            throw std::runtime_error("spec.PublishSync: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
        }

        ServiceSpec spec = BuildSpecFromConfig(appConfig, capability, base);
        std::string payload = spec.ToJson().dump();

        auto start = std::chrono::steady_clock::now();
        int delayMs = 500;
        const int maxDelayMs = 30000;

        while (true) {
            if (stopFlag && stopFlag->load()) return false;

            if (detail::SendHttpRequest(webAddr, payload)) {
                if (logger) {
                    logger->Info("spec.PublishSync: Successfully published '" + spec.name + "' to " + webAddr);
                }
                return true;
            }

            if (maxWaitMs == 0) {
                if (logger) {
                    logger->Debug("spec.PublishSync: Failed to reach web-interface at " + webAddr);
                }
                return false;
            }

            if (maxWaitMs > 0) {
                auto elapsedMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - start).count();
                if (elapsedMs >= maxWaitMs) {
                    return false;
                }
            }

            int sleepMs = detail::JitteredBackoffMs(delayMs);
            if (logger) {
                logger->Debug("spec.PublishSync: Waiting for web-interface at " + webAddr + ". Retrying in " + std::to_string(sleepMs) + "ms...");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(sleepMs));
            delayMs = std::min(delayMs * 2, maxDelayMs);
        }
    }

    static bool PublishSync(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base, int maxWaitMs = 0) {
        std::shared_ptr<utils::Logger> safeLogger;
        if (logger) {
            safeLogger = std::shared_ptr<utils::Logger>(logger, [](utils::Logger*){});
        } else {
            safeLogger = appConfig.GetLogger();
        }
        return PublishSync(appConfig, safeLogger, capability, base, maxWaitMs);
    }

    static bool publishSync(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base, int maxWaitMs = 0) {
        return PublishSync(appConfig, logger, capability, base, maxWaitMs);
    }

    static bool publishSync(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, const std::string& capability, const ServiceSpec& base, int maxWaitMs = 0) {
        return PublishSync(appConfig, logger, capability, base, maxWaitMs);
    }

    // -------------------------------------------------------------------------

    /**
     * Publish validates web_interface reachability and specification synchronously (FAIL-FAST)
     * before spawning background publishing with 500ms..30s exponential backoff, jitter, and 30s heartbeats.
     */
    static void Publish(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, const std::string& capability, const ServiceSpec& base, std::shared_ptr<std::atomic<bool>> stopFlag = nullptr) {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (contracts_detail_trim(webAddr).empty()) {
            if (logger) {
                logger->Critical("spec.Publish: Capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
            }
            throw std::runtime_error("spec.Publish: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
        }

        ServiceSpec spec = BuildSpecFromConfig(appConfig, capability, base);
        std::string payload = spec.ToJson().dump();

        if (!stopFlag) {
            stopFlag = std::make_shared<std::atomic<bool>>(false);
        }

        std::thread([webAddr, payload, spec, logger, stopFlag]() {
            bool isFirst = true;
            int delayMs = 500;
            const int maxDelayMs = 30000;

            while (!stopFlag->load()) {
                if (detail::SendHttpRequest(webAddr, payload)) {
                    if (logger) {
                        if (isFirst) {
                            logger->Info("spec.Publish: Service '" + spec.name + "' registered with web-interface at " + webAddr);
                            isFirst = false;
                        } else {
                            logger->Debug("spec.Publish: Heartbeat for '" + spec.name + "' sent to " + webAddr);
                        }
                    }
                    delayMs = 500;
                    for (int i = 0; i < 30; ++i) {
                        if (stopFlag->load()) return;
                        std::this_thread::sleep_for(std::chrono::seconds(1));
                    }
                } else {
                    int waitMs = detail::JitteredBackoffMs(delayMs);
                    if (logger) {
                        logger->Debug("spec.Publish: Waiting for web-interface at " + webAddr + ". Retrying in " + std::to_string(waitMs) + "ms...");
                    }
                    int chunk = 100;
                    for (int elapsed = 0; elapsed < waitMs; elapsed += chunk) {
                        if (stopFlag->load()) return;
                        std::this_thread::sleep_for(std::chrono::milliseconds(std::min(chunk, waitMs - elapsed)));
                    }
                    delayMs = std::min(delayMs * 2, maxDelayMs);
                }
            }
        }).detach();
    }

    static void Publish(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base, std::shared_ptr<std::atomic<bool>> stopFlag = nullptr) {
        std::shared_ptr<utils::Logger> safeLogger;
        if (logger) {
            safeLogger = std::shared_ptr<utils::Logger>(logger, [](utils::Logger*){});
        } else {
            safeLogger = appConfig.GetLogger();
        }
        Publish(appConfig, safeLogger, capability, base, stopFlag);
    }

    static void publish(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        Publish(appConfig, logger, capability, base);
    }

    static void publish(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, const std::string& capability, const ServiceSpec& base) {
        Publish(appConfig, logger, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * PublishWithLifecycle binds publishing to the service's lifecycle manager.
     */
    static void PublishWithLifecycle(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, lifecycle::LifecycleManager* lm, const std::string& capability, const ServiceSpec& base) {
        auto stopFlag = std::make_shared<std::atomic<bool>>(false);
        Publish(appConfig, logger, capability, base, stopFlag);
        if (lm) {
            lm->Register("OpenMFEPublisher_" + capability, [stopFlag]() {
                if (stopFlag) stopFlag->store(true);
            });
        }
    }

    static void PublishWithLifecycle(const config::AppConfig& appConfig, utils::Logger* logger, lifecycle::LifecycleManager* lm, const std::string& capability, const ServiceSpec& base) {
        std::shared_ptr<utils::Logger> safeLogger;
        if (logger) {
            safeLogger = std::shared_ptr<utils::Logger>(logger, [](utils::Logger*){});
        } else {
            safeLogger = appConfig.GetLogger();
        }
        PublishWithLifecycle(appConfig, safeLogger, lm, capability, base);
    }

    static void publishWithLifecycle(const config::AppConfig& appConfig, utils::Logger* logger, lifecycle::LifecycleManager* lm, const std::string& capability, const ServiceSpec& base) {
        PublishWithLifecycle(appConfig, logger, lm, capability, base);
    }

    static void publishWithLifecycle(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, lifecycle::LifecycleManager* lm, const std::string& capability, const ServiceSpec& base) {
        PublishWithLifecycle(appConfig, logger, lm, capability, base);
    }

private:
    static std::string contracts_detail_trim(const std::string& s) {
        return detail::TrimStr(s);
    }
};

} // namespace spec
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SPEC_HPP
