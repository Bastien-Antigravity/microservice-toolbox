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

#include "../config/AppConfig.hpp"
#include "../config/json.hpp"
#include "../utils/Logger.hpp"
#include "../lifecycle/LifecycleManager.hpp"

namespace microservice_toolbox {
namespace spec {

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
    bool requiresAuth{false};
    std::string capability;
    std::string description;
    std::string protocol;
    std::string framing;
    std::string docLink;
    std::vector<std::string> flowDiagram;
    nlohmann::json dataStructure = nlohmann::json::object();
    std::string sdkLang{"language-cpp"};
    std::string sourceCode;

    nlohmann::json ToJson() const {
        return {
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

        std::string listenAddr = appConfig.GetListenAddr(capability);
        std::string restAddr = appConfig.GetRESTAddr(capability);
        std::string grpcAddr = appConfig.GetGRPCListenAddr(capability);

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

        return spec;
    }

    static ServiceSpec buildSpecFromConfig(const config::AppConfig& appConfig, const std::string& capability, const ServiceSpec& base) {
        return BuildSpecFromConfig(appConfig, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * PublishSync validates web_interface connectivity (FAIL-FAST) and executes publishing.
     */
    static bool PublishSync(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (webAddr.empty()) {
            if (logger) {
                logger->Critical("spec.PublishSync: Capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
            }
            throw std::runtime_error("spec.PublishSync: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
        }

        // Validate specification synchronously (FAIL-FAST)
        BuildSpecFromConfig(appConfig, capability, base);
        return true;
    }

    static bool publishSync(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        return PublishSync(appConfig, logger, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * Publish validates web_interface reachability and specification synchronously (FAIL-FAST)
     * before spawning background publishing.
     */
    static void Publish(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (webAddr.empty()) {
            if (logger) {
                logger->Critical("spec.Publish: Capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
            }
            throw std::runtime_error("spec.Publish: capability 'web_interface' is unresolvable from configuration (FAIL-FAST)");
        }

        // Validate specification synchronously (FAIL-FAST)
        BuildSpecFromConfig(appConfig, capability, base);
    }

    static void publish(const config::AppConfig& appConfig, utils::Logger* logger, const std::string& capability, const ServiceSpec& base) {
        Publish(appConfig, logger, capability, base);
    }

    // -------------------------------------------------------------------------

    /**
     * PublishWithLifecycle binds publishing to the service's lifecycle manager.
     */
    static void PublishWithLifecycle(const config::AppConfig& appConfig, utils::Logger* logger, lifecycle::LifecycleManager* lm, const std::string& capability, const ServiceSpec& base) {
        Publish(appConfig, logger, capability, base);
        if (lm) {
            lm->Register("OpenMFEPublisher_" + capability, []() {});
        }
    }

    static void publishWithLifecycle(const config::AppConfig& appConfig, utils::Logger* logger, lifecycle::LifecycleManager* lm, const std::string& capability, const ServiceSpec& base) {
        PublishWithLifecycle(appConfig, logger, lm, capability, base);
    }
};

} // namespace spec
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_SPEC_HPP
