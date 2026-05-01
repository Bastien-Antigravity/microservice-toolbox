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

/**
 * Default No-Op Logger to prevent crashes.
 */
class NoOpLogger : public Logger {
public:
    void Info(const std::string&) override {}
    void Warning(const std::string&) override {}
    void Error(const std::string&) override {}
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
            
            // Phase 2: Manual loading of 'private' section (Parity with Go Toolbox)
            // Note: distributed-config engine ignores 'private', so we handle it here.
            LoadPrivateOverrides();
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
        std::string addr = config_->GetAddress(capability);
        if (addr.empty()) {
            throw std::runtime_error("Capability not found or address resolution failed: " + capability);
        }
        return addr;
    }

    std::string GetGRPCListenAddr(const std::string& capability) const {
        std::string addr = config_->GetGRPCAddress(capability);
        if (addr.empty()) {
            throw std::runtime_error("gRPC capability not found: " + capability);
        }
        return addr;
    }

    /**
     * Access service-specific private configuration.
     * Manually extracted from local YAML files to maintain engine decoupling.
     */
    std::string GetPrivate(const std::string& key) const {
        auto it = private_config_.find(key);
        if (it != private_config_.end()) {
            return it->second;
        }
        return "";
    }

    distconf::DistConfig& GetRawConfig() { return *config_; }
    const std::string& GetProfile() const { return profile_; }

private:
    std::string profile_;
    std::shared_ptr<Logger> logger_;
    std::unique_ptr<distconf::DistConfig> config_;
    std::map<std::string, std::string> private_config_;

    void LoadPrivateOverrides() {
        // We look for [profile].yaml or config/[profile].yaml (matching engine discovery)
        std::vector<std::string> candidates = {
            profile_ + ".yaml",
            "config/" + profile_ + ".yaml"
        };

        for (const auto& path : candidates) {
            std::ifstream file(path);
            if (!file.is_open()) continue;

            std::string line;
            bool in_private = false;
            while (std::getline(file, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();

                // Simple YAML-lite parser for top-level "private:"
                if (line.find("private:") == 0) {
                    in_private = true;
                    continue;
                }

                if (in_private) {
                    // Check if we exited the private section (new top-level key or EOF)
                    if (!line.empty() && !isspace(line[0]) && line.find('#') != 0) {
                        in_private = false;
                        continue;
                    }

                    size_t colon = line.find(':');
                    if (colon != std::string::npos) {
                        std::string k = line.substr(0, colon);
                        std::string v = line.substr(colon + 1);

                        // Trim whitespace
                        k.erase(0, k.find_first_not_of(" \t"));
                        k.erase(k.find_last_not_of(" \t") + 1);
                        v.erase(0, v.find_first_not_of(" \t"));
                        v.erase(v.find_last_not_of(" \t") + 1);

                        if (k.empty()) continue;

                        // Remove quotes
                        if (v.size() >= 2 && v.front() == '\'' && v.back() == '\'') v = v.substr(1, v.size() - 2);
                        if (v.size() >= 2 && v.front() == '\"' && v.back() == '\"') v = v.substr(1, v.size() - 2);

                        // Basic ENV expansion: ${VAR} or ${VAR:default}
                        v = ExpandEnv(v);
                        private_config_[k] = v;
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
