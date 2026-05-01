#ifndef DISTCONF_HPP
#define DISTCONF_HPP

#include <string>
#include <vector>
#include <functional>
#include <stdexcept>
#include <memory>

// Include the generated C header
#include "libdistconf.h"
#include <map>
#include <mutex>

namespace distconf {

/**
 * DistConfig is a C++ wrapper around the libdistconf CGO bridge.
 * It provides a clean, object-oriented interface for configuration management.
 */
class DistConfig {
public:
    explicit DistConfig(const std::string& profile) {
        handle_ = DistConf_New(const_cast<char*>(profile.c_str()));
        if (handle_ == 0) {
            throw std::runtime_error("Failed to initialize DistConf with profile: " + profile);
        }
    }

    ~DistConfig() {
        if (handle_ != 0) {
            DistConf_Close(handle_);
        }
    }

    // Disable copy
    DistConfig(const DistConfig&) = delete;
    DistConfig& operator=(const DistConfig&) = delete;

    // Get a configuration value
    std::string Get(const std::string& section, const std::string& key) const {
        char* val = DistConf_Get(handle_, 
                                 const_cast<char*>(section.c_str()), 
                                 const_cast<char*>(key.c_str()));
        if (!val) return "";
        std::string result(val);
        DistConf_FreeString(val);
        return result;
    }

    // Set a configuration value
    bool Set(const std::string& section, const std::string& key, const std::string& value) {
        return DistConf_Set(handle_, 
                     const_cast<char*>(section.c_str()), 
                     const_cast<char*>(key.c_str()), 
                     const_cast<char*>(value.c_str())) != 0;
    }

    // Synchronize with the Config Server
    bool Sync() {
        return DistConf_Sync(handle_) != 0;
    }

    // Broadcast state to the ecosystem
    bool ShareConfig(const std::string& json_data) {
        return DistConf_ShareConfig(handle_, 
                                  const_cast<char*>(json_data.c_str())) != 0;
    }

    // Validate mandatory services
    bool ValidateMandatoryServices() {
        return DistConf_ValidateMandatoryServices(handle_) != 0;
    }

    // Get an address (host:port) for a capability
    std::string GetAddress(const std::string& capability) const {
        char* val = DistConf_GetAddress(handle_, const_cast<char*>(capability.c_str()));
        if (!val) return "";
        std::string result(val);
        DistConf_FreeString(val);
        return result;
    }

    // Get a gRPC address for a capability
    std::string GetGRPCAddress(const std::string& capability) const {
        char* val = DistConf_GetGRPCAddress(handle_, const_cast<char*>(capability.c_str()));
        if (!val) return "";
        std::string result(val);
        DistConf_FreeString(val);
        return result;
    }

    // Get full configuration as JSON
    std::string GetFullConfig() const {
        char* val = DistConf_GetFullConfig(handle_);
        if (!val) return "{}";
        std::string result(val);
        DistConf_FreeString(val);
        return result;
    }

    // Get a capability configuration as JSON
    std::string GetCapability(const std::string& capability) const {
        char* val = DistConf_GetCapability(handle_, const_cast<char*>(capability.c_str()));
        if (!val) return "{}";
        std::string result(val);
        DistConf_FreeString(val);
        return result;
    }

    // Decrypt a secret
    std::string Decrypt(const std::string& ciphertext) const {
        char* val = DistConf_Decrypt(handle_, const_cast<char*>(ciphertext.c_str()));
        if (!val) {
            std::string err = GetLastError();
            if (err.empty()) err = "Decryption failed (bridge error)";
            throw std::runtime_error(err);
        }
        std::string result(val);
        DistConf_FreeString(val);
        return result;
    }

    // Get the last error from the underlying engine
    std::string GetLastError() const {
        char* err = DistConf_GetLastError();
        if (!err) return "";
        return std::string(err);
    }

    // Register a live update listener
    void OnLiveConfUpdate(std::function<void(const std::string&)> callback) {
        callback_ = callback;
        
        std::lock_guard<std::mutex> lock(GetRegistryMutex());
        GetRegistry()[handle_] = this;

        DistConf_OnLiveConfUpdate(handle_, StaticCallbackBridge);
    }

    // Register a registry update listener
    void OnRegistryUpdate(std::function<void(const std::string&)> callback) {
        registry_callback_ = callback;
        
        std::lock_guard<std::mutex> lock(GetRegistryMutex());
        GetRegistry()[handle_] = this;

        DistConf_OnRegistryUpdate(handle_, StaticRegistryBridge);
    }

private:
    static void StaticCallbackBridge(uintptr_t handle, const char* json_data) {
        std::lock_guard<std::mutex> lock(GetRegistryMutex());
        auto it = GetRegistry().find(handle);
        if (it != GetRegistry().end() && it->second->callback_) {
            it->second->callback_(std::string(json_data));
        }
    }

    static void StaticRegistryBridge(uintptr_t handle, const char* json_data) {
        std::lock_guard<std::mutex> lock(GetRegistryMutex());
        auto it = GetRegistry().find(handle);
        if (it != GetRegistry().end() && it->second->registry_callback_) {
            it->second->registry_callback_(std::string(json_data));
        }
    }

    uintptr_t handle_;
    std::function<void(const std::string&)> callback_;
    std::function<void(const std::string&)> registry_callback_;

    // Meyer's Singleton for header-only static registry without C++17 inline variables
    static std::map<uintptr_t, DistConfig*>& GetRegistry() {
        static std::map<uintptr_t, DistConfig*> registry;
        return registry;
    }

    static std::mutex& GetRegistryMutex() {
        static std::mutex registry_mutex;
        return registry_mutex;
    }
};

} // namespace distconf

#endif // DISTCONF_HPP
