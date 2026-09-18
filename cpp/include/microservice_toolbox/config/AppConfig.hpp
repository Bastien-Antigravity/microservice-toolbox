// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-level application configuration interface providing typed accessors and resolution.
//
// DATA FLOW:
// Config Hierarchy -> AppConfig Resolution -> Service Endpoint Strings
//
// KEY PARAMETERS:
// - capability: Target service capability name.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_APP_CONFIG_HPP
#define MICROSERVICE_TOOLBOX_APP_CONFIG_HPP

#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "../utils/Logger.hpp"
#include "CommandLine.hpp"
#include "DistConf.hpp"
#include "json.hpp"

namespace microservice_toolbox {
namespace config {

using Logger = microservice_toolbox::utils::Logger;
using NoOpLogger = microservice_toolbox::utils::NoOpLogger;
using StdOutLogger = microservice_toolbox::utils::StdOutLogger;

/**
 * AppConfig is the C++ implementation of the Microservice Toolbox configuration
 * loader. It provides a unified, hardened API across the polyglot ecosystem.
 */
class AppConfig {
public:
  explicit AppConfig(const std::string &profile,
                     std::shared_ptr<Logger> logger = nullptr,
                     const CLIArgs &args = {})
      : profile_(args.profile.empty() ? profile : args.profile),
        logger_(logger ? logger : std::make_shared<NoOpLogger>()),
        args_(args) {

    try {
      config_ = std::make_unique<distconf::DistConfig>(profile_);
      logger_->Info("libdistconf session initialized for profile: " + profile_);

      // Full FFI Bridge Sync: Fetch entire config state once
      SyncFromBridge();

      // Phase 2: Manual loading of 'local' section (Parity with Go Toolbox)
      LoadLocalOverrides();

      // Phase 3: Apply CLI Overrides
      ApplyCLIOverrides();

      // Phase 4: Validate Unique Endpoints (Parity with Go, Python, Rust)
      ValidateUniquePorts();
    } catch (const std::exception &e) {
      logger_->Error(std::string("Failed to initialize DistConf: ") + e.what());
      throw;
    }
  }

  void SetLogger(std::shared_ptr<Logger> logger) {
    logger_ = logger ? logger : std::make_shared<NoOpLogger>();
    logger_->Info("Logger updated successfully");
  }

  std::string GetServiceName() const {
    if (data_.contains("common") && data_["common"].contains("name")) {
        return data_["common"]["name"].get<std::string>();
    }
    return "unknown-service";
  }

  std::string DecryptSecret(const std::string &ciphertext) const {
    if (ciphertext.size() < 5 || ciphertext.compare(0, 4, "ENC(") != 0 ||
        ciphertext.back() != ')') {
      return ciphertext;
    }
    return config_->Decrypt(ciphertext);
  }

  std::string GetListenAddr(const std::string &capability) const {
    try {
      if (data_.contains("capabilities") &&
          data_["capabilities"].contains(capability)) {
        auto cap = data_["capabilities"][capability];
        if (cap.contains("ip") && cap.contains("port")) {
          return cap["ip"].get<std::string>() + ":" +
                 cap["port"].get<std::string>();
        }
      }
    } catch (...) {
    }

    // Fallback to direct FFI if mirror fails or is incomplete
    std::string addr = config_->GetAddress(capability);
    if (addr.empty()) {
      throw std::runtime_error(
          "Capability not found or address resolution failed: " + capability);
    }
    return addr;
  }

  std::string GetGRPCListenAddr(const std::string &capability) const {
    try {
      if (data_.contains("capabilities") &&
          data_["capabilities"].contains(capability)) {
        auto cap = data_["capabilities"][capability];
        if (cap.contains("grpc_ip") && cap.contains("grpc_port")) {
          return cap["grpc_ip"].get<std::string>() + ":" +
                 cap["grpc_port"].get<std::string>();
        }
      }
    } catch (...) {
    }

    // Fallback to direct FFI
    std::string addr = config_->GetGRPCAddress(capability);
    if (addr.empty()) {
      throw std::runtime_error("gRPC capability not found: " + capability);
    }
    return addr;
  }

  std::string GetRESTAddr(const std::string &capability) const {
    try {
      if (data_.contains("capabilities") &&
          data_["capabilities"].contains(capability)) {
        auto cap = data_["capabilities"][capability];
        if (cap.contains("ip") && cap.contains("rest_port")) {
          return cap["ip"].get<std::string>() + ":" +
                 cap["rest_port"].get<std::string>();
        }
      }
    } catch (...) {
    }

    std::string addr = config_->GetRESTAddress(capability);
    if (addr.empty()) {
      throw std::runtime_error("REST capability not found: " + capability);
    }
    return addr;
  }


  /**
   * Access service-specific local configuration.
   * Supports nested lookups using dot notation (e.g., "database.host").
   */
  std::string GetLocal(const std::string &key) const {
    // Look in our private local config member (Ecosystem Parity)
    try {
      auto current = local_data_;
      std::stringstream ss(key);
      std::string part;
      while (std::getline(ss, part, '.')) {
        if (current.contains(part)) {
          current = current[part];
        } else {
          return "";
        }
      }
      if (current.is_string())
        return current.get<std::string>();
      return current.dump();
    } catch (...) {
    }
    return "";
  }

  /**
   * Unmarshals the 'local' configuration section into a target type.
   * Uses nlohmann::json's automatic mapping.
   */
  template <typename T> void UnmarshalLocal(T &target) const {
    target = local_data_.get<T>();
  }

  /**
   * Returns the entire 'local' configuration as a JSON object.
   * Parity with Go's raw local map.
   */
  nlohmann::json GetLocalJSON() const {
    return local_data_;
  }

  /**
   * Access the 'common' configuration block.
   */
  nlohmann::json GetCommon() const {
    if (data_.contains("common")) {
      return data_["common"];
    }
    return nlohmann::json::object();
  }

  void OnLiveConfUpdate(std::function<void(const std::string&)> callback) {
    config_->OnLiveConfUpdate([this, callback](const std::string& json_data) {
        callback(json_data);
        SyncFromBridge(); // Keep local mirror updated
    });
  }

  void OnRegistryUpdate(std::function<void(const std::string&)> callback) {
    config_->OnRegistryUpdate([this, callback](const std::string& json_data) {
        callback(json_data);
        SyncFromBridge();
    });
  }

  bool ShareConfig(const nlohmann::json& payload) {
    return config_->ShareConfig(payload.dump());
  }

  distconf::DistConfig &GetRawConfig() { return *config_; }
  const std::string &GetProfile() const { return profile_; }
  const CLIArgs &GetArgs() const { return args_; }

  void ValidateUniquePorts() const {
    if (!data_.contains("capabilities") || !data_["capabilities"].is_object()) {
      return;
    }

    struct Endpoint {
      std::string ip;
      int port;
      bool operator<(const Endpoint &other) const {
        if (ip != other.ip) return ip < other.ip;
        return port < other.port;
      }
    };

    auto normalize_ip = [](const std::string &ip_in) {
      std::string s = ip_in;
      std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
      if (s == "localhost") return std::string("127.0.0.1");
      return s;
    };

    std::map<Endpoint, std::string> seen;

    auto check_and_add = [&](const std::string &ip_val, int port_val, const std::string &desc) {
      if (ip_val.empty() || port_val <= 0) return;
      std::string nip = normalize_ip(ip_val);
      for (const auto &kv : seen) {
        if (kv.first.port == port_val) {
          if (nip == kv.first.ip || nip == "0.0.0.0" || kv.first.ip == "0.0.0.0") {
            throw std::runtime_error("Duplicate endpoint detected: " + ip_val + ":" + std::to_string(port_val) +
                                     " for " + desc + " conflicts with " + kv.first.ip + ":" +
                                     std::to_string(kv.first.port) + " for " + kv.second);
          }
        }
      }
      seen[{nip, port_val}] = desc;
    };

    auto parse_port = [](const nlohmann::json &v) -> int {
      if (v.is_number_integer()) return v.get<int>();
      if (v.is_string()) {
        try {
          return std::stoi(v.get<std::string>());
        } catch (...) {
          return -1;
        }
      }
      return -1;
    };

    for (auto it = data_["capabilities"].begin(); it != data_["capabilities"].end(); ++it) {
      const auto &cap_name = it.key();
      const auto &cap_data = it.value();
      if (!cap_data.is_object()) continue;

      std::string ip = cap_data.contains("ip") && cap_data["ip"].is_string() ? cap_data["ip"].get<std::string>() : "";
      std::string g_ip = cap_data.contains("grpc_ip") && cap_data["grpc_ip"].is_string() ? cap_data["grpc_ip"].get<std::string>() : ip;

      // Explicit TCP port
      if (!ip.empty() && cap_data.contains("port")) {
        int p = parse_port(cap_data["port"]);
        if (p > 0) check_and_add(ip, p, cap_name + " (TCP)");
      }

      // Explicit gRPC port
      if (!g_ip.empty() && cap_data.contains("grpc_port")) {
        int gp = parse_port(cap_data["grpc_port"]);
        if (gp > 0) check_and_add(g_ip, gp, cap_name + " (gRPC)");
      }

      // Explicit REST port
      if (!ip.empty() && cap_data.contains("rest_port")) {
        int rp = parse_port(cap_data["rest_port"]);
        if (rp > 0) check_and_add(ip, rp, cap_name + " (REST)");
      }
    }
  }

private:
  std::string profile_;
  std::shared_ptr<Logger> logger_;
  std::unique_ptr<distconf::DistConfig> config_;
  nlohmann::json data_;
  nlohmann::json local_data_;
  CLIArgs args_;

  void SyncFromBridge() {
    try {
      std::string json_raw = config_->GetFullConfig();
      data_ = nlohmann::json::parse(json_raw);
      logger_->Info("Full FFI Bridge Sync completed successfully");
    } catch (const std::exception &) {
      std::string err = config_->GetLastError();
      if (!err.empty()) {
        logger_->Warning(err);
      }
      data_ = nlohmann::json::object();
    }
  }

  void LoadLocalOverrides() {
    std::vector<std::string> candidates = {profile_ + ".yaml",
                                           "config/" + profile_ + ".yaml"};

    for (const auto &path : candidates) {
      std::ifstream infile(path);
      if (!infile.good()) continue;
      infile.close();

      std::string local_json = config_->ApplyFileOverride(path);
      if (!local_json.empty() && local_json != "{}") {
        try {
          auto parsed = nlohmann::json::parse(local_json);
          // Standard Deep Merge for local config parity
          for (auto it = parsed.begin(); it != parsed.end(); ++it) {
            local_data_[it.key()] = it.value();
          }
          logger_->Info("Standardized Local overrides merged from: " + path);
        } catch (...) {
          logger_->Warning("Failed to parse expanded local config from bridge");
        }
      }
      SyncFromBridge(); // Refresh mirror for common/capabilities
      return;
    }
  }

  void ApplyCLIOverrides() {
    if (!args_.name.empty()) {
      data_["common"]["name"] = args_.name;
    }

    std::string target = args_.name;
    if (target.empty() && data_.contains("common") &&
        data_["common"].contains("name")) {
      target = data_["common"]["name"].get<std::string>();
    }
    if (target.empty())
      target = "config_server";

    if (!args_.host.empty() || args_.port != 0) {
      if (!data_.contains("capabilities"))
        data_["capabilities"] = nlohmann::json::object();
      if (!data_["capabilities"].contains(target))
        data_["capabilities"][target] = nlohmann::json::object();

      if (!args_.host.empty())
        data_["capabilities"][target]["ip"] = args_.host;
      if (args_.port != 0)
        data_["capabilities"][target]["port"] = std::to_string(args_.port);
    }

    if (!args_.grpc_host.empty() || args_.grpc_port != 0) {
      if (!data_.contains("capabilities"))
        data_["capabilities"] = nlohmann::json::object();
      if (!data_["capabilities"].contains(target))
        data_["capabilities"][target] = nlohmann::json::object();

      if (!args_.grpc_host.empty())
        data_["capabilities"][target]["grpc_ip"] = args_.grpc_host;
      if (args_.grpc_port != 0)
        data_["capabilities"][target]["grpc_port"] = std::to_string(args_.grpc_port);
    }

    if (!args_.key.empty()) {
      // Set environment variable for decryption engine
#ifdef _WIN32
      _putenv_s("BASTIEN_PRIVATE_KEY_PATH", args_.key.c_str());
#else
      setenv("BASTIEN_PRIVATE_KEY_PATH", args_.key.c_str(), 1);
#endif
    }
  }
};

inline std::unique_ptr<AppConfig>
LoadConfigWithLogger(const std::string &profile,
                     std::shared_ptr<Logger> logger,
                     int argc = 0, char **argv = nullptr,
                     const std::vector<std::string> &specific_flags = {}) {
  CLIArgs args;
  if (argc > 0 && argv != nullptr) {
    args = CommandLine::Parse(argc, argv, specific_flags);
  }
  return std::make_unique<AppConfig>(profile, logger, args);
}

inline std::unique_ptr<AppConfig>
LoadConfig(const std::string &profile, int argc = 0, char **argv = nullptr,
           const std::vector<std::string> &specific_flags = {}) {
  return LoadConfigWithLogger(profile, nullptr, argc, argv, specific_flags);
}

} // namespace config
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_APP_CONFIG_HPP
