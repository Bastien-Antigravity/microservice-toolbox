#ifndef MICROSERVICE_TOOLBOX_APP_CONFIG_HPP
#define MICROSERVICE_TOOLBOX_APP_CONFIG_HPP

#include <string>
#include <memory>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <map>
#include <fstream>
#include <sstream>
#include <algorithm>

// Include the underlying SDK
#include "../../../../../distributed-config/distconf/cpp/DistConf.hpp"
#include "json.hpp"

namespace microservice_toolbox {
namespace config {

/**
 * Basic Logger interface to match Toolbox pattern.
 */
class Logger {
public:
    virtual ~Logger() = default;
    virtual void Info(const std::string& msg) = 0;
    virtual void Warning(const std::string& msg) = 0;
    virtual void Error(const std::string& msg) = 0;
};

class NoOpLogger : public Logger {
public:
    void Info(const std::string&) override {}
    void Warning(const std::string&) override {}
    void Error(const std::string&) override {}
};

/**
 * Standard output logger for debugging and CLI tools.
 */
class StdOutLogger : public Logger {
public:
    void Info(const std::string& msg) override { std::cout << "[INFO] " << msg << std::endl; }
    void Warning(const std::string& msg) override { std::cout << "[WARN] " << msg << std::endl; }
    void Error(const std::string& msg) override { std::cerr << "[ERROR] " << msg << std::endl; }
};

/**
 * AppConfig is the C++ implementation of the Microservice Toolbox configuration loader.
 * It provides a unified, hardened API across the polyglot ecosystem.
 */
class AppConfig {
public:
    explicit AppConfig(const std::string& profile, std::shared_ptr<Logger> logger = nullptr)
        : profile_(profile), logger_(logger ? logger : std::make_shared<NoOpLogger>()) {
        
        try {
            config_ = std::make_unique<distconf::DistConfig>(profile);
            logger_->Info("libdistconf session initialized for profile: " + profile);
            
            // Full FFI Bridge Sync: Fetch entire config state once
            SyncFromBridge();

            // Phase 2: Manual loading of 'local' section (Parity with Go Toolbox)
            // Note: distributed-config engine ignores 'local', so we handle it here as 'local' config.
            LoadLocalOverrides();
        } catch (const std::exception& e) {
            logger_->Error(std::string("Failed to initialize DistConf: ") + e.what());
            throw;
        }
    }

    void SetLogger(std::shared_ptr<Logger> logger) {
        logger_ = logger ? logger : std::make_shared<NoOpLogger>();
        logger_->Info("Logger updated successfully");
    }

    std::string DecryptSecret(const std::string& ciphertext) const {
        if (ciphertext.size() < 5 || 
            ciphertext.compare(0, 4, "ENC(") != 0 || 
            ciphertext.back() != ')') {
            return ciphertext;
        }
        return config_->Decrypt(ciphertext);
    }

    std::string GetListenAddr(const std::string& capability) const {
        try {
            if (data_.contains("capabilities") && data_["capabilities"].contains(capability)) {
                auto cap = data_["capabilities"][capability];
                if (cap.contains("ip") && cap.contains("port")) {
                    return cap["ip"].get<std::string>() + ":" + cap["port"].get<std::string>();
                }
            }
        } catch (...) {}
        
        // Fallback to direct FFI if mirror fails or is incomplete
        std::string addr = config_->GetAddress(capability);
        if (addr.empty()) {
            throw std::runtime_error("Capability not found or address resolution failed: " + capability);
        }
        return addr;
    }

    std::string GetGRPCListenAddr(const std::string& capability) const {
        try {
            if (data_.contains("capabilities") && data_["capabilities"].contains(capability)) {
                auto cap = data_["capabilities"][capability];
                if (cap.contains("grpc_ip") && cap.contains("grpc_port")) {
                    return cap["grpc_ip"].get<std::string>() + ":" + cap["grpc_port"].get<std::string>();
                }
            }
        } catch (...) {}

        // Fallback to direct FFI
        std::string addr = config_->GetGRPCAddress(capability);
        if (addr.empty()) {
            throw std::runtime_error("gRPC capability not found: " + capability);
        }
        return addr;
    }

    /**
     * Access service-specific local configuration.
     * Supports nested lookups using dot notation (e.g., "database.host").
     */
    std::string GetLocal(const std::string& key) const {
        // Our current C++ parser is flat (key-value).
        // For parity, we check the flat map. 
        // Real nested parsing would require a full YAML parser which we don't have in this C++ wrapper yet.
        auto it = local_config_.find(key);
        if (it != local_config_.end()) {
            return it->second;
        }
        return "";
    }

    /**
     * Unmarshals the 'local' configuration section into a target type.
     * Uses nlohmann::json's automatic mapping.
     */
    template <typename T>
    void UnmarshalLocal(T& target) const {
        target = nlohmann::json(local_config_).get<T>();
    }

    /**
     * Returns the entire 'local' configuration as a JSON object.
     * Parity with Go's raw local map.
     */
    nlohmann::json GetLocalJSON() const {
        return nlohmann::json(local_config_);
    }

    distconf::DistConfig& GetRawConfig() { return *config_; }
    const std::string& GetProfile() const { return profile_; }

private:
    std::string profile_;
    std::shared_ptr<Logger> logger_;
    std::unique_ptr<distconf::DistConfig> config_;
    nlohmann::json data_;
    std::map<std::string, std::string> local_config_;

    void SyncFromBridge() {
        try {
            std::string json_raw = config_->GetFullConfig();
            data_ = nlohmann::json::parse(json_raw);
            logger_->Info("Full FFI Bridge Sync completed successfully");
        } catch (const std::exception&) {
            std::string err = config_->GetLastError();
            if (!err.empty()) {
                logger_->Warning(err);
            }
            data_ = nlohmann::json::object();
        }
    }

    void LoadLocalOverrides() {
        // We look for [profile].yaml or config/[profile].yaml (matching engine discovery)
        std::vector<std::string> candidates = {
            profile_ + ".yaml",
            "config/" + profile_ + ".yaml"
        };

        for (const auto& path : candidates) {
            std::ifstream file(path);
            if (!file.is_open()) continue;

            std::string line;
            bool in_local = false;
            std::vector<std::pair<int, std::string>> stack;

            while (std::getline(file, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                
                std::string trimmed = line;
                trimmed.erase(0, trimmed.find_first_not_of(" \t"));
                if (trimmed.empty() || trimmed[0] == '#') continue;

                int indent = line.find_first_not_of(" \t");

                if (trimmed.find("local:") == 0) {
                    in_local = true;
                    stack.clear();
                    continue;
                }

                if (in_local) {
                    if (indent == 0 && trimmed.find(":") != std::string::npos) {
                         in_local = false;
                         continue;
                    }

                    size_t colon = trimmed.find(':');
                    if (colon != std::string::npos) {
                        std::string k = trimmed.substr(0, colon);
                        std::string v = trimmed.substr(colon + 1);
                        v.erase(0, v.find_first_not_of(" \t"));
                        v.erase(v.find_last_not_of(" \t") + 1);

                        // Pop from stack if indent is less or equal to previous
                        while (!stack.empty() && indent <= stack.back().first) {
                            stack.pop_back();
                        }

                        if (v.empty()) {
                            stack.push_back({indent, k});
                        } else {
                            // Strip quotes
                            if (v.size() >= 2 && ((v.front() == '"' && v.back() == '"') || (v.front() == '\'' && v.back() == '\''))) {
                                v = v.substr(1, v.size() - 2);
                            }
                            
                            std::string full_key = "";
                            for (const auto& pair : stack) full_key += pair.second + ".";
                            full_key += k;
                            local_config_[full_key] = ExpandEnv(v);
                        }
                    }
                }
            }
            file.close();
        }
    }

    std::string ExpandEnv(const std::string& input) const {
        std::string result = input;
        size_t start_pos = 0;
        while ((start_pos = result.find("${", start_pos)) != std::string::npos) {
            size_t end_pos = result.find("}", start_pos);
            if (end_pos == std::string::npos) break;

            std::string token = result.substr(start_pos + 2, end_pos - start_pos - 2);
            std::string var_name = token;
            std::string default_val = "";

            size_t colon = token.find(':');
            if (colon != std::string::npos) {
                var_name = token.substr(0, colon);
                default_val = token.substr(colon + 1);
            }

            const char* env_val = std::getenv(var_name.c_str());
            std::string final_val = (env_val) ? std::string(env_val) : default_val;

            result.replace(start_pos, end_pos - start_pos + 1, final_val);
            start_pos += final_val.length();
        }
        return result;
    }
};

inline std::unique_ptr<AppConfig> LoadConfig(const std::string& profile) {
    return std::make_unique<AppConfig>(profile);
}

inline std::unique_ptr<AppConfig> LoadConfigWithLogger(const std::string& profile, std::shared_ptr<Logger> logger) {
    return std::make_unique<AppConfig>(profile, logger);
}

} // namespace config
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_APP_CONFIG_HPP
