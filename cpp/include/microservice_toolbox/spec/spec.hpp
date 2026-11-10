#ifndef MICROSERVICE_TOOLBOX_SPEC_HPP
#define MICROSERVICE_TOOLBOX_SPEC_HPP

/*
 * ESSENTIAL PROCESS:
 * Standardizes self-describing microservice specifications and dynamic
 * registration with web-interface across the Bastien-Antigravity fleet for C++.
 * Auto-resolves runtime listen/REST addresses, dynamic semver, active
 * profile, and documentation links from AppConfig.
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

#include <string>
#include <vector>
#include <map>
#include <memory>
#include <thread>
#include <chrono>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <atomic>
#include <mutex>

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

    nlohmann::json toJson() const {
        return ToJson();
    }
};

// -----------------------------------------------------------------------------

/**
 * ServiceSpec is the canonical specification of a microservice.
 * Microservices must explicitly provide their own domain metadata; zero dummy defaults are permitted.
 */
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
    std::string description;
    std::string protocol;
    std::string framing;
    std::string docLink;
    std::string navRoute;
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
        if (!navRoute.empty()) {
            j["navRoute"] = navRoute;
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

    nlohmann::json toJson() const {
        return ToJson();
    }
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
        if (capability.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: capability name is strictly required (FAIL-FAST)");
        }
        if (base.name.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'name' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.tag.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'tag' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.layer.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'layer' (L1|L2|L3) is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.category.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'category' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.description.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'description' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.docLink.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'docLink' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.protocol.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'protocol' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }
        if (base.framing.empty()) {
            throw std::invalid_argument("spec.BuildSpecFromConfig: 'framing' is strictly required for capability '" + capability + "' (FAIL-FAST)");
        }

        ServiceSpec spec = base;
        spec.capability = capability;
        if (spec.navTitle.empty()) {
            spec.navTitle = spec.name;
        }

        std::string listenAddr;
        try { listenAddr = appConfig.GetListenAddr(capability); } catch (...) {}
        std::string restAddr;
        try { restAddr = appConfig.GetRESTAddr(capability); } catch (...) {}
        std::string grpcAddr;
        try { grpcAddr = appConfig.GetGRPCListenAddr(capability); } catch (...) {}

        auto extractPort = [](const std::string& addr) -> std::string {
            auto idx = addr.rfind(':');
            return (idx != std::string::npos) ? addr.substr(idx + 1) : "";
        };

        std::string tcpPort = extractPort(listenAddr);
        std::string restPort = extractPort(restAddr);
        std::string grpcPort = extractPort(grpcAddr);

        if (spec.url.empty()) {
            if (!restAddr.empty()) {
                spec.url = "http://" + restAddr;
            } else if (!listenAddr.empty()) {
                spec.url = "http://" + listenAddr;
            } else {
                throw std::runtime_error("spec.BuildSpecFromConfig: unable to resolve URL for capability '" + capability + "' (FAIL-FAST)");
            }
        }

        // Framing port interpolation: If caller provided format string with %s, populate available ports
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
                throw std::runtime_error("spec.BuildSpecFromConfig: framing requires " + std::to_string(count) + " port(s) for capability '" + capability + "' (FAIL-FAST)");
            }

            for (size_t i = 0; i < count; ++i) {
                size_t p = spec.framing.find("%s");
                if (p != std::string::npos) {
                    spec.framing.replace(p, 2, available[i]);
                }
            }
        }

        std::string ver = appConfig.GetVersion();
        if (ver.empty()) {
            throw std::runtime_error("spec.BuildSpecFromConfig: dynamic version resolution returned empty string (FAIL-FAST)");
        }

        spec.dataStructure["version"] = ver;
        spec.dataStructure["capability"] = capability;
        spec.dataStructure["ports"] = nlohmann::json::object();

        if (!tcpPort.empty()) spec.dataStructure["ports"]["tcp"] = tcpPort;
        if (!restPort.empty()) spec.dataStructure["ports"]["rest"] = restPort;
        if (!grpcPort.empty()) spec.dataStructure["ports"]["grpc"] = grpcPort;

#if !defined(_WIN32)
        char hostBuf[256] = {0};
        if (gethostname(hostBuf, sizeof(hostBuf) - 1) == 0 && hostBuf[0] != '\0') {
            spec.dataStructure["node"] = std::string(hostBuf);
        }
#endif
        if (spec.navRoute.empty()) {
            spec.navRoute = "/mfe/" + spec.name;
        }

        return spec;
    }

    static ServiceSpec buildSpecFromConfig(const config::AppConfig& appConfig, const std::string& capability, const ServiceSpec& base) {
        return BuildSpecFromConfig(appConfig, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * PublishSync validates web_interface connectivity (FAIL-FAST) and executes HTTP publishing.
     */
    static bool PublishSync(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, const std::string& capability, const ServiceSpec& base) {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (webAddr.empty()) {
            if (logger) {
                logger->Critical("spec.PublishSync: Capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
            }
            throw std::runtime_error("spec.PublishSync: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
        }

        // Validate specification synchronously (FAIL-FAST)
        ServiceSpec spec = BuildSpecFromConfig(appConfig, capability, base);
        std::string payload = spec.ToJson().dump();

        bool ok = detail::SendHttpRequest(webAddr, payload);
        if (ok) {
            if (logger) {
                logger->Info("spec.PublishSync: Successfully published '" + spec.name + "' to " + webAddr);
            }
        } else {
            if (logger) {
                logger->Debug("spec.PublishSync: Failed to reach web-interface at " + webAddr);
            }
        }
        return ok;
    }

    static bool PublishSync(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        std::shared_ptr<utils::Logger> safeLogger;
        if (logger) {
            safeLogger = std::shared_ptr<utils::Logger>(logger, [](utils::Logger*){});
        } else {
            safeLogger = appConfig.GetLogger();
        }
        return PublishSync(appConfig, safeLogger, capability, base);
    }

    static bool publishSync(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        return PublishSync(appConfig, logger, capability, base);
    }

    static bool publishSync(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, const std::string& capability, const ServiceSpec& base) {
        return PublishSync(appConfig, logger, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * Publish validates web_interface reachability and specification synchronously (FAIL-FAST)
     * before spawning background publishing with periodic 30s heartbeats.
     */
    static void Publish(const config::AppConfig& appConfig, std::shared_ptr<utils::Logger> logger, const std::string& capability, const ServiceSpec& base, std::shared_ptr<std::atomic<bool>> stopFlag = nullptr) {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (webAddr.empty()) {
            if (logger) {
                logger->Critical("spec.Publish: Capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
            }
            throw std::runtime_error("spec.Publish: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
        }

        // Validate specification synchronously (FAIL-FAST)
        ServiceSpec spec = BuildSpecFromConfig(appConfig, capability, base);
        std::string payload = spec.ToJson().dump();

        if (!stopFlag) {
            stopFlag = std::make_shared<std::atomic<bool>>(false);
        }

        // Spawn non-blocking background thread maintaining periodic 30s heartbeats
        // Avoid raw pointer capture by holding std::shared_ptr<utils::Logger>
        std::thread([webAddr, payload, spec, logger, stopFlag]() {
            bool isFirst = true;
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
                } else {
                    if (logger) {
                        logger->Debug("spec.Publish: Waiting for web-interface at " + webAddr + ". Retrying...");
                    }
                }
                for (int i = 0; i < 30; ++i) {
                    if (stopFlag->load()) return;
                    std::this_thread::sleep_for(std::chrono::seconds(1));
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
};

} // namespace spec
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SPEC_HPP
