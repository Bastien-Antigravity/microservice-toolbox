// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: NetworkManager.hpp.
//
// DATA FLOW:
// Callers -> NetworkManager.hpp -> Processed Output
//
// KEY PARAMETERS:
// - Standard module parameters.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_CONN_MANAGER_NETWORK_MANAGER_HPP
#define MICROSERVICE_TOOLBOX_CONN_MANAGER_NETWORK_MANAGER_HPP

#include <chrono>
#include <cmath>
#include <random>
#include <functional>
#include <memory>
#include <string>
#include <thread>
#include "../utils/Logger.hpp"

namespace microservice_toolbox {
namespace config {
class AppConfig;
}
namespace conn_manager {

class ManagedConnection; // Forward declaration

struct Endpoint {
    std::string ip;
    std::string port;
    std::string public_ip;
    std::string profile;
    std::string address;

    Endpoint(std::string i, std::string p, std::string pub = "", std::string prof = "")
        : ip(std::move(i)), port(std::move(p)), public_ip(std::move(pub)), profile(std::move(prof)),
          address(ip + ":" + port) {}
};

using OnErrorHandler = std::function<void(int attempt, const std::string& error, const std::string& source, const std::string& msg)>;
using ReloadHandler = std::function<std::pair<std::string, std::string>(int attempt)>;

enum class ConnectionMode {
    Blocking,
    NonBlocking,
    Indefinite
};

/**
 * NetworkManager handles reliable connection establishment policy with retries.
 * Implements backoff and jitter.
 */
class NetworkManager : public std::enable_shared_from_this<NetworkManager> {
public:
    int max_retries; // -1 for infinite
    std::chrono::milliseconds base_delay;
    std::chrono::milliseconds max_delay;
    std::chrono::milliseconds connect_timeout;
    double backoff;
    double jitter;
    OnErrorHandler on_error;
    std::shared_ptr<utils::Logger> logger;
    ReloadHandler on_reload_config;
    std::shared_ptr<config::AppConfig> app_config;

    NetworkManager(int max_retries, int base_delay_ms, int max_delay_ms, int connect_timeout_ms, double backoff, double jitter, std::shared_ptr<utils::Logger> logger = nullptr, ReloadHandler on_reload = nullptr, std::shared_ptr<config::AppConfig> app_config = nullptr)
        : max_retries(max_retries),
          base_delay(base_delay_ms),
          max_delay(max_delay_ms),
          connect_timeout(connect_timeout_ms),
          backoff(backoff),
          jitter(jitter),
          on_error(nullptr),
          logger(utils::EnsureSafeLogger(logger)),
          on_reload_config(std::move(on_reload)),
          app_config(std::move(app_config)) {}

    std::chrono::milliseconds GetNextDelay(int attempt) {
        double delay = base_delay.count() * std::pow(backoff, attempt);
        if (delay > max_delay.count()) {
            delay = max_delay.count();
        }

        if (jitter > 0) {
            thread_local std::mt19937 rng(std::random_device{}());
            std::uniform_real_distribution<double> dist(0, jitter * delay);
            delay += dist(rng);
        }

        return std::chrono::milliseconds(static_cast<long long>(delay));
    }

    // High-level connection API
    std::shared_ptr<ManagedConnection> ConnectBlocking(const std::string& ip, const std::string& port, 
                                                       const std::string& public_ip, const std::string& profile);
    
    std::shared_ptr<ManagedConnection> ConnectNonBlocking(const std::string& ip, const std::string& port, 
                                                          const std::string& public_ip, const std::string& profile);

    std::shared_ptr<ManagedConnection> Connect(const std::string& ip, const std::string& port, 
                                               const std::string& public_ip, const std::string& profile, 
                                               ConnectionMode mode);

    std::shared_ptr<ManagedConnection> ConnectCapability(const std::string& capability, ConnectionMode mode = ConnectionMode::Blocking);

    // Unified Factory Method combining AppConfig and Logger in one function with pointers
    static std::shared_ptr<NetworkManager> New(std::shared_ptr<config::AppConfig> ac = nullptr, std::shared_ptr<utils::Logger> logger = nullptr) {
        return std::make_shared<NetworkManager>(5, 200, 5000, 2000, 2.0, 0.0, logger, nullptr, ac);
    }

    // Static Factory Methods for Strategies
    static std::shared_ptr<NetworkManager> NewWithConfig(std::shared_ptr<config::AppConfig> ac, std::shared_ptr<utils::Logger> logger = nullptr) {
        return New(ac, logger);
    }

    static std::shared_ptr<NetworkManager> NewCritical(std::shared_ptr<utils::Logger> logger = nullptr) {
        return std::make_shared<NetworkManager>(-1, 200, 10000, 5000, 2.0, 0.2, logger);
    }

    static std::shared_ptr<NetworkManager> NewStandard(std::shared_ptr<utils::Logger> logger = nullptr) {
        return std::make_shared<NetworkManager>(10, 500, 30000, 5000, 1.5, 0.1, logger);
    }

    static std::shared_ptr<NetworkManager> NewPerformance(std::shared_ptr<utils::Logger> logger = nullptr) {
        return std::make_shared<NetworkManager>(-1, 100, 2000, 1000, 1.2, 0.0, logger);
    }
};

} // namespace conn_manager
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_CONN_MANAGER_NETWORK_MANAGER_HPP
