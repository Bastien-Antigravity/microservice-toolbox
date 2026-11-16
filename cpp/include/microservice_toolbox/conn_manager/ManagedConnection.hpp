// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: ManagedConnection.hpp.
//
// DATA FLOW:
// Callers -> ManagedConnection.hpp -> Processed Output
//
// KEY PARAMETERS:
// - Standard module parameters.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_CONN_MANAGER_MANAGED_CONNECTION_HPP
#define MICROSERVICE_TOOLBOX_CONN_MANAGER_MANAGED_CONNECTION_HPP

#include <atomic>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include "NetworkManager.hpp"
#include "../config/AppConfig.hpp"

// We expect safesock to be available in the workspace or linked
#include "../../../../../safe-socket/safesock/cpp/SafeSocket.hpp"

namespace microservice_toolbox {
namespace conn_manager {

/**
 * ManagedConnection is a resilient wrapper around safesock::SafeSocket.
 * It automatically handles reconnections using the policy defined in NetworkManager.
 */
class ManagedConnection {
public:
    ManagedConnection(const std::string& ip, const std::string& port, 
                      const std::string& public_ip, const std::string& profile,
                      std::shared_ptr<NetworkManager> nm,
                      std::shared_ptr<config::AppConfig> app_config = nullptr,
                      const std::string& capability = "")
        : endpoint_(std::make_shared<const Endpoint>(ip, port, public_ip, profile)), nm_(nm),
          app_config_(app_config ? std::move(app_config) : (nm ? nm->app_config : nullptr)),
          capability_(capability),
          closed_(false) {}

    ManagedConnection(std::shared_ptr<const Endpoint> ep,
                      std::shared_ptr<NetworkManager> nm,
                      std::shared_ptr<config::AppConfig> app_config = nullptr,
                      const std::string& capability = "")
        : endpoint_(std::move(ep)), nm_(nm),
          app_config_(app_config ? std::move(app_config) : (nm ? nm->app_config : nullptr)),
          capability_(capability),
          closed_(false) {}

    ~ManagedConnection() {
        Close();
    }

    void UpdateEndpoint(const std::string& ip, const std::string& port) {
        auto old_ep = std::atomic_load(&endpoint_);
        auto next_ep = std::make_shared<const Endpoint>(
            ip, port,
            old_ep ? old_ep->public_ip : "",
            old_ep ? old_ep->profile : ""
        );
        std::atomic_store(&endpoint_, std::move(next_ep));
    }

    std::pair<std::string, std::string> GetEndpoint() const {
        auto ep = std::atomic_load(&endpoint_);
        if (!ep) return {"", ""};
        return {ep->ip, ep->port};
    }

    std::shared_ptr<const Endpoint> GetEndpointPtr() const {
        return std::atomic_load(&endpoint_);
    }

    std::shared_ptr<const Endpoint> CurrentEndpoint() {
        auto ep = std::atomic_load(&endpoint_);
        if (app_config_ && !capability_.empty()) {
            try {
                std::string new_addr = app_config_->GetListenAddr(capability_);
                if (!ep || new_addr != ep->address) {
                    auto colon_pos = new_addr.rfind(':');
                    if (colon_pos != std::string::npos) {
                        UpdateEndpoint(new_addr.substr(0, colon_pos), new_addr.substr(colon_pos + 1));
                        ep = std::atomic_load(&endpoint_);
                    }
                }
            } catch (...) {
            }
        }
        return ep;
    }

    // Send data, reconnecting if necessary
    void Send(const std::vector<uint8_t>& data) {
        std::unique_lock<std::mutex> lock(mutex_);
        if (closed_.load()) return;

        EnsureConnected(lock);
        try {
            socket_->send(data);
        } catch (const std::exception& e) {
            nm_->logger->Warning("ManagedConnection: Send failed, attempting reconnect: " + std::string(e.what()));
            Reconnect(lock);
            if (!closed_.load() && socket_) {
                socket_->send(data);
            }
        }
    }

    // Receive data
    std::vector<uint8_t> Receive(int max_length = 65535) {
        std::unique_lock<std::mutex> lock(mutex_);
        if (closed_.load()) return {};

        EnsureConnected(lock);
        try {
            return socket_->receive(max_length);
        } catch (const std::exception& e) {
            nm_->logger->Warning("ManagedConnection: Receive failed, attempting reconnect: " + std::string(e.what()));
            Reconnect(lock);
            if (!closed_.load() && socket_) {
                return socket_->receive(max_length);
            }
            return {};
        }
    }

    void Close() {
        bool expected = false;
        if (closed_.compare_exchange_strong(expected, true)) {
            std::lock_guard<std::mutex> lock(mutex_);
            if (socket_) socket_->close();
        }
    }

    // Reconnect logic mirroring Go/Python/Rust
    void Reconnect() {
        std::unique_lock<std::mutex> lock(mutex_);
        Reconnect(lock);
    }

    void Reconnect(std::unique_lock<std::mutex>& lock) {
        int attempt = 0;

        while (!closed_.load() && (nm_->max_retries == -1 || attempt < nm_->max_retries)) {
            int attempt_num = attempt + 1;
            auto ep = CurrentEndpoint();

            try {
                if (socket_) socket_->close();
                socket_ = safesock::create(ep->profile, ep->address, ep->public_ip, "client", true);
                nm_->logger->Info("ManagedConnection: Reconnected to " + ep->address);
                return;
            } catch (const std::exception& e) {
                if (nm_->on_error) {
                    nm_->on_error(attempt_num, e.what(), "ManagedConnection", "Reconnection failure to " + ep->address);
                }

                auto delay = nm_->GetNextDelay(attempt);
                nm_->logger->Warning("ManagedConnection: Reconnect to " + ep->address + " failed: " + e.what() + ". Retrying in " + std::to_string(delay.count()) + "ms...");
                
                lock.unlock();
                std::this_thread::sleep_for(delay);
                lock.lock();
                if (closed_.load()) return;
                attempt++;
            }
        }
        
        auto ep = CurrentEndpoint();
        throw std::runtime_error("ManagedConnection: Max retries reached for " + (ep ? ep->address : "unknown"));
    }

private:
    void EnsureConnected(std::unique_lock<std::mutex>& lock) {
        if (!socket_) {
            Reconnect(lock);
        }
    }

    std::shared_ptr<const Endpoint> endpoint_;
    std::shared_ptr<NetworkManager> nm_;
    std::shared_ptr<config::AppConfig> app_config_;
    std::string capability_;
    std::unique_ptr<safesock::SafeSocket> socket_;
    mutable std::mutex mutex_;
    std::atomic<bool> closed_{false};
};

// NetworkManager implementation of high-level API
inline std::shared_ptr<ManagedConnection> NetworkManager::ConnectBlocking(const std::string& ip, const std::string& port, 
                                                                   const std::string& public_ip, const std::string& profile) {
    auto ep = std::make_shared<const Endpoint>(ip, port, public_ip, profile);
    auto mc = std::make_shared<ManagedConnection>(ep, shared_from_this());
    try {
        mc->Reconnect();
    } catch (const std::exception& e) {
        if (on_error) {
            on_error(1, e.what(), "NetworkManager", "Initial connection failed");
        }
    }
    return mc;
}

inline std::shared_ptr<ManagedConnection> NetworkManager::ConnectNonBlocking(const std::string& ip, const std::string& port, 
                                                                      const std::string& public_ip, const std::string& profile) {
    auto ep = std::make_shared<const Endpoint>(ip, port, public_ip, profile);
    auto mc = std::make_shared<ManagedConnection>(ep, shared_from_this());
    std::thread([mc]() {
        try {
            mc->Reconnect();
        } catch (...) {
            // Error handled via on_error callback inside Reconnect
        }
    }).detach();
    return mc;
}

inline std::shared_ptr<ManagedConnection> NetworkManager::Connect(const std::string& ip, const std::string& port, 
                                                           const std::string& public_ip, const std::string& profile, 
                                                           ConnectionMode mode) {
    switch (mode) {
        case ConnectionMode::Blocking:
            return ConnectBlocking(ip, port, public_ip, profile);
        case ConnectionMode::NonBlocking:
            return ConnectNonBlocking(ip, port, public_ip, profile);
        case ConnectionMode::Indefinite:
            return ConnectBlocking(ip, port, public_ip, profile); // Indefinite handled by Reconnect policy
        default:
            return ConnectBlocking(ip, port, public_ip, profile);
    }
}

inline std::shared_ptr<ManagedConnection> NetworkManager::ConnectCapability(const std::string& capability, ConnectionMode mode) {
    if (!app_config) {
        throw std::runtime_error("NetworkManager: AppConfig is null, cannot resolve capability " + capability);
    }
    std::string addr = app_config->GetListenAddr(capability);
    auto colon_pos = addr.rfind(':');
    if (colon_pos == std::string::npos) {
        throw std::runtime_error("NetworkManager: invalid address format for capability " + capability + ": " + addr);
    }
    std::string ip = addr.substr(0, colon_pos);
    std::string port = addr.substr(colon_pos + 1);
    std::string public_ip = app_config->GetPublicIP();
    std::string profile = app_config->GetProfile();

    auto ep = std::make_shared<const Endpoint>(ip, port, public_ip, profile);
    auto mc = std::make_shared<ManagedConnection>(ep, shared_from_this(), app_config, capability);

    if (mode == ConnectionMode::NonBlocking) {
        std::thread([mc]() {
            try {
                mc->Reconnect();
            } catch (...) {
            }
        }).detach();
        return mc;
    } else {
        try {
            mc->Reconnect();
        } catch (const std::exception& e) {
            if (on_error) {
                on_error(1, e.what(), "NetworkManager", "Failed to connect to capability " + capability);
            }
        }
        return mc;
    }
}

} // namespace conn_manager
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_CONN_MANAGER_MANAGED_CONNECTION_HPP
