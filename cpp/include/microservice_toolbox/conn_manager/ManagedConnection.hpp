#ifndef MICROSERVICE_TOOLBOX_CONN_MANAGER_MANAGED_CONNECTION_HPP
#define MICROSERVICE_TOOLBOX_CONN_MANAGER_MANAGED_CONNECTION_HPP

#include <string>
#include <vector>
#include <memory>
#include <thread>
#include <mutex>
#include <iostream>
#include "NetworkManager.hpp"

// We expect safesock to be available in the workspace or linked
#include "../../../../safe-socket/safesock/cpp/SafeSocket.hpp"

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
                      std::shared_ptr<NetworkManager> nm)
        : ip_(ip), port_(port), public_ip_(public_ip), profile_(profile), nm_(nm),
          closed_(false) {}

    ~ManagedConnection() {
        Close();
    }

    // Send data, reconnecting if necessary
    void Send(const std::vector<uint8_t>& data) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closed_) return;

        EnsureConnected();
        try {
            socket_->send(data);
        } catch (const std::exception& e) {
            nm_->logger->Warning("ManagedConnection: Send failed, attempting reconnect: " + std::string(e.what()));
            Reconnect();
            socket_->send(data);
        }
    }

    // Receive data
    std::vector<uint8_t> Receive(int max_length = 65535) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closed_) return {};

        EnsureConnected();
        try {
            return socket_->receive(max_length);
        } catch (const std::exception& e) {
            nm_->logger->Warning("ManagedConnection: Receive failed, attempting reconnect: " + std::string(e.what()));
            Reconnect();
            return socket_->receive(max_length);
        }
    }

    void Close() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!closed_) {
            if (socket_) socket_->close();
            closed_ = true;
        }
    }

    // Reconnect logic mirroring Go/Python/Rust
    void Reconnect() {
        int attempt = 0;
        std::string address = ip_ + ":" + port_;

        while (!closed_ && (nm_->max_retries == -1 || attempt < nm_->max_retries)) {
            try {
                if (socket_) socket_->close();
                socket_ = safesock::create(profile_, address, public_ip_, "client", true);
                nm_->logger->Info("ManagedConnection: Reconnected to " + address);
                return;
            } catch (const std::exception& e) {
                if (nm_->on_error) {
                    nm_->on_error(attempt + 1, e.what(), "ManagedConnection", "Reconnection failure to " + address);
                }

                auto delay = nm_->GetNextDelay(attempt);
                nm_->logger->Warning("ManagedConnection: Reconnect to " + address + " failed: " + e.what() + ". Retrying in " + std::to_string(delay.count()) + "ms...");
                
                std::this_thread::sleep_for(delay);
                attempt++;
            }
        }
        
        throw std::runtime_error("ManagedConnection: Max retries reached for " + address);
    }

private:
    void EnsureConnected() {
        if (!socket_) {
            Reconnect();
        }
    }

    std::string ip_;
    std::string port_;
    std::string public_ip_;
    std::string profile_;
    std::shared_ptr<NetworkManager> nm_;
    std::unique_ptr<safesock::SafeSocket> socket_;
    std::mutex mutex_;
    bool closed_;
};

// NetworkManager implementation of high-level API
inline std::shared_ptr<ManagedConnection> NetworkManager::ConnectBlocking(const std::string& ip, const std::string& port, 
                                                                   const std::string& public_ip, const std::string& profile) {
    auto mc = std::make_shared<ManagedConnection>(ip, port, public_ip, profile, shared_from_this());
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
    auto mc = std::make_shared<ManagedConnection>(ip, port, public_ip, profile, shared_from_this());
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

} // namespace conn_manager
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_CONN_MANAGER_MANAGED_CONNECTION_HPP
