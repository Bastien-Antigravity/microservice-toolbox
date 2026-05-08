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

    } catch (const std::exception &e) {
      logger_->Error(std::string("Failed to initialize DistConf: ") + e.what());
      throw;
    }
  }

  void SetLogger(std::shared_ptr<Logger> logger) {
    logger_ = logger ? logger : std::make_shared<NoOpLogger>();
    logger_->Info("Logger updated successfully");
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

  /**
   * Access service-specific local configuration.
   * Supports nested lookups using dot notation (e.g., "database.host").
   */
  std::string GetLocal(const std::string &key) const {
    // Look in the unified 'local' section of our data mirror
    try {
      if (data_.contains("local")) {
        auto current = data_["local"];
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
      }
    } catch (...) {
    }
    return "";
  }

  /**
   * Unmarshals the 'local' configuration section into a target type.
   * Uses nlohmann::json's automatic mapping.
   */
  template <typename T> void UnmarshalLocal(T &target) const {
    if (data_.contains("local")) {
      target = data_["local"].get<T>();
    }
  }

  /**
   * Returns the entire 'local' configuration as a JSON object.
   * Parity with Go's raw local map.
   */
  nlohmann::json GetLocalJSON() const {
    if (data_.contains("local"))
      return data_["local"];
    return nlohmann::json::object();
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

  distconf::DistConfig &GetRawConfig() { return *config_; }
  const std::string &GetProfile() const { return profile_; }
  const CLIArgs &GetArgs() const { return args_; }

private:
  std::string profile_;
  std::shared_ptr<Logger> logger_;
  std::unique_ptr<distconf::DistConfig> config_;
  nlohmann::json data_;
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
      std::ifstream file(path);
      if (!file.is_open())
        continue;

      std::string line;
      std::vector<std::pair<int, std::string>> stack;

      while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r')
          line.pop_back();
        std::string trimmed = line;
        int indent = trimmed.find_first_not_of(" \t");
        if (indent == std::string::npos)
          continue;
        trimmed.erase(0, indent);
        if (trimmed.empty() || trimmed[0] == '#')
          continue;

        size_t colon = trimmed.find(':');
        if (colon != std::string::npos) {
          std::string k = trimmed.substr(0, colon);
          std::string v = trimmed.substr(colon + 1);
          v.erase(0, v.find_first_not_of(" \t"));
          v.erase(v.find_last_not_of(" \t") + 1);

          // Adjust stack based on indentation
          while (!stack.empty() && indent <= stack.back().first) {
            stack.pop_back();
          }

          // Traverse JSON to the current level
          nlohmann::json *current = &data_;
          for (const auto &level : stack) {
            if (!current->contains(level.second))
              (*current)[level.second] = nlohmann::json::object();
            current = &((*current)[level.second]);
          }

          if (v.empty()) {
            // It's a new level
            stack.push_back({indent, k});
            if (!current->contains(k))
              (*current)[k] = nlohmann::json::object();
          } else {
            // It's a value
            if (v.size() >= 2 && ((v.front() == '"' && v.back() == '"') ||
                                  (v.front() == '\'' && v.back() == '\''))) {
              v = v.substr(1, v.size() - 2);
            }
            (*current)[k] = ExpandEnv(v);
          }
        }
      }
      file.close();
      logger_->Info("Local overrides merged from " + path);
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

  std::string ExpandEnv(const std::string &input) const {
    std::string result = input;
    size_t start_pos = 0;
    while ((start_pos = result.find("${", start_pos)) != std::string::npos) {
      size_t end_pos = result.find("}", start_pos);
      if (end_pos == std::string::npos)
        break;

      std::string token = result.substr(start_pos + 2, end_pos - start_pos - 2);
      std::string var_name = token;
      std::string default_val = "";

      size_t colon = token.find(':');
      if (colon != std::string::npos) {
        var_name = token.substr(0, colon);
        default_val = token.substr(colon + 1);
      }

      const char *env_val = std::getenv(var_name.c_str());
      std::string final_val = (env_val) ? std::string(env_val) : default_val;

      result.replace(start_pos, end_pos - start_pos + 1, final_val);
      start_pos += final_val.length();
    }
    return result;
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
