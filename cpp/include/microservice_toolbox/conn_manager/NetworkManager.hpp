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
namespace conn_manager {

class ManagedConnection; // Forward declaration

using OnErrorHandler = std::function<void(int attempt, const std::string& error, const std::string& source, const std::string& msg)>;

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

    NetworkManager(int max_retries, int base_delay_ms, int max_delay_ms, int connect_timeout_ms, double backoff, double jitter, std::shared_ptr<utils::Logger> logger = nullptr)
        : max_retries(max_retries),
          base_delay(base_delay_ms),
          max_delay(max_delay_ms),
          connect_timeout(connect_timeout_ms),
          backoff(backoff),
          jitter(jitter),
          logger(utils::EnsureSafeLogger(logger)) {}

    std::chrono::milliseconds GetNextDelay(int attempt) {
        double delay = base_delay.count() * std::pow(backoff, attempt);
        if (delay > max_delay.count()) {
            delay = max_delay.count();
        }

        if (jitter > 0) {
            static std::mt19937 rng(std::random_device{}());
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

    // Static Factory Methods for Strategies
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
