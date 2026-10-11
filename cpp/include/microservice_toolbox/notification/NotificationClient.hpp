// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-level client facade enabling C++ microservices to dispatch direct,
// multi-channel notifications to notif-server via the libtoolbox C ABI bridge.
//
// DATA FLOW:
// C++ Domain Event -> NotificationClient::Send / SendAlert -> libtoolbox C ABI -> gRPC (Port 1027) -> notif-server
//
// KEY PARAMETERS:
// - app_config: Shared ecosystem AppConfig resolving notif_server gRPC capability.
// - target_addr: Target gRPC address (host:port) of notif-server.
// - logger: Unified ecosystem logger instance.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_NOTIFICATION_CLIENT_HPP
#define MICROSERVICE_TOOLBOX_NOTIFICATION_CLIENT_HPP

#include <cstdlib>
#include <future>
#include <iostream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(_WIN32)
#include <windows.h>
#else
#include <dlfcn.h>
#endif

#include "../config/AppConfig.hpp"
#include "../utils/Logger.hpp"

namespace microservice_toolbox {
namespace notification {

using Logger = microservice_toolbox::utils::Logger;

// -----------------------------------------------------------------------------
// Function Pointer Types matching libnotif C ABI
// -----------------------------------------------------------------------------

typedef int (*FnNotif_SendWithTimeout)(
    const char *targetAddr, const char *level, const char *message,
    const char *attachment, const char *tagsCSV, double timeoutSec);

typedef char *(*FnNotif_GetLastError)(void);
typedef void (*FnNotif_FreeString)(char *ptr);
typedef void (*FnNotif_Close)(void);

// -----------------------------------------------------------------------------
// Dynamic Library Loader Helper for libnotif
// -----------------------------------------------------------------------------

class NotifBridgeLoader {
public:
  static NotifBridgeLoader &Instance() {
    static NotifBridgeLoader instance;
    return instance;
  }

  bool EnsureLoaded(std::string &errorOut) {
    std::lock_guard<std::mutex> lock(mu_);
    if (loaded_)
      return true;

    std::vector<std::string> candidates;
    const char *envPath = std::getenv("LIBNOTIF_PATH");
    if (envPath && *envPath) {
      candidates.push_back(envPath);
    }

#if defined(__APPLE__)
    candidates.push_back("../../notif-server/notif/libnotif/libnotif.dylib");
    candidates.push_back("../notif-server/notif/libnotif/libnotif.dylib");
    candidates.push_back("notif-server/notif/libnotif/libnotif.dylib");
    candidates.push_back("/usr/local/lib/libnotif.dylib");
    candidates.push_back("lib/libnotif.dylib");
#elif defined(_WIN32)
    candidates.push_back("libnotif.dll");
    candidates.push_back("../../notif-server/notif/libnotif/libnotif.dll");
    candidates.push_back("../notif-server/notif/libnotif/libnotif.dll");
#else
    candidates.push_back("../../notif-server/notif/libnotif/libnotif.so");
    candidates.push_back("../notif-server/notif/libnotif/libnotif.so");
    candidates.push_back("notif-server/notif/libnotif/libnotif.so");
    candidates.push_back("/usr/local/lib/libnotif.so");
    candidates.push_back("lib/libnotif.so");
#endif

    for (const auto &path : candidates) {
#if defined(_WIN32)
      HMODULE handle = LoadLibraryA(path.c_str());
      if (handle) {
        handle_ = handle;
        fnSend_ = (FnNotif_SendWithTimeout)GetProcAddress(
            handle, "Notif_SendWithTimeout");
        fnGetLastError_ =
            (FnNotif_GetLastError)GetProcAddress(handle, "Notif_GetLastError");
        fnFreeString_ =
            (FnNotif_FreeString)GetProcAddress(handle, "Notif_FreeString");
        fnClose_ = (FnNotif_Close)GetProcAddress(handle, "Notif_Close");
        if (fnSend_) {
          loaded_ = true;
          return true;
        }
      }
#else
      void *handle = dlopen(path.c_str(), RTLD_NOW | RTLD_GLOBAL);
      if (handle) {
        handle_ = handle;
        fnSend_ = (FnNotif_SendWithTimeout)dlsym(
            handle, "Notif_SendWithTimeout");
        fnGetLastError_ =
            (FnNotif_GetLastError)dlsym(handle, "Notif_GetLastError");
        fnFreeString_ =
            (FnNotif_FreeString)dlsym(handle, "Notif_FreeString");
        fnClose_ = (FnNotif_Close)dlsym(handle, "Notif_Close");
        if (fnSend_) {
          loaded_ = true;
          return true;
        }
      }
#endif
    }

#if defined(_WIN32)
    errorOut = "Failed to load libnotif.dll from candidate paths";
#else
    const char *dlErr = dlerror();
    errorOut = std::string("Failed to load libnotif shared library: ") +
               (dlErr ? dlErr : "file not found in candidate paths");
#endif
    return false;
  }

  FnNotif_SendWithTimeout FnSend() const { return fnSend_; }
  FnNotif_GetLastError FnGetLastError() const { return fnGetLastError_; }
  FnNotif_FreeString FnFreeString() const { return fnFreeString_; }
  FnNotif_Close FnClose() const { return fnClose_; }

private:
  NotifBridgeLoader()
      : loaded_(false), handle_(nullptr), fnSend_(nullptr),
        fnGetLastError_(nullptr), fnFreeString_(nullptr), fnClose_(nullptr) {}

  bool loaded_;
  void *handle_;
  FnNotif_SendWithTimeout fnSend_;
  FnNotif_GetLastError fnGetLastError_;
  FnNotif_FreeString fnFreeString_;
  FnNotif_Close fnClose_;
  std::mutex mu_;
};

// -----------------------------------------------------------------------------
// NotificationClient Class (100% Parity with Go, Python, Rust)
// -----------------------------------------------------------------------------

class NotificationClient {
public:
  /// Initializes a NotificationClient pointing to a specific target address.
  explicit NotificationClient(const std::string &target_addr,
                              std::shared_ptr<Logger> logger = nullptr)
      : target_addr_(target_addr),
        logger_(microservice_toolbox::utils::EnsureSafeLogger(logger)),
        timeout_sec_(5.0), closed_(false) {
    if (target_addr_.empty()) {
      throw std::invalid_argument("target_addr cannot be empty");
    }
  }

  // ---------------------------------------------------------------------------

  /// Initializes a NotificationClient by dynamically resolving the notif_server
  /// capability address from the provided ecosystem AppConfig.
  /// Fails fast if the notif_server capability or its gRPC address is unresolvable.
  static NotificationClient FromConfig(const config::AppConfig &app_config,
                                       std::shared_ptr<Logger> logger = nullptr,
                                       const std::string &capability = "notif_server") {
    auto safe_logger = microservice_toolbox::utils::EnsureSafeLogger(logger);

    std::string addr = app_config.GetGRPCListenAddr(capability);
    if (addr.empty()) {
      throw std::runtime_error(
          "failed to resolve " + capability + " gRPC address: address is empty");
    }

    safe_logger->Info("NotificationClient configured with target address: " + addr);
    return NotificationClient(addr, safe_logger);
  }

  // ---------------------------------------------------------------------------

  /// Sets default RPC dispatch timeout in seconds.
  void SetTimeout(double seconds) {
    if (seconds > 0) {
      timeout_sec_ = seconds;
    }
  }

  // ---------------------------------------------------------------------------

  /// 1-line helper dispatching an untyped or informational notification
  /// with optional destination tags (e.g. "telegram", "discord").
  bool Send(const std::string &message,
            const std::vector<std::string> &tags = {}) {
    return SendWithAttachment("", message, "", tags);
  }

  // ---------------------------------------------------------------------------

  /// Dispatches a categorized notification with a specific severity level
  /// (e.g., "TRADE", "CRITICAL", "WARNING", "REPORT", "INFO") and optional tags.
  bool SendAlert(const std::string &level, const std::string &message,
                 const std::vector<std::string> &tags = {}) {
    return SendWithAttachment(level, message, "", tags);
  }

  // ---------------------------------------------------------------------------

  /// Dispatches a full notification payload including level, message,
  /// attachment reference, and destination tags.
  bool SendWithAttachment(const std::string &level, const std::string &message,
                          const std::string &attachment,
                          const std::vector<std::string> &tags = {}) {
    if (closed_) {
      logger_->Warning("NotificationClient dispatch rejected: client is closed");
      return false;
    }

    std::string loadErr;
    if (!NotifBridgeLoader::Instance().EnsureLoaded(loadErr)) {
      logger_->Error("NotificationClient bridge error: " + loadErr);
      return false;
    }

    // Join tags into CSV string
    std::string tagsCSV;
    for (size_t i = 0; i < tags.size(); ++i) {
      if (i > 0)
        tagsCSV += ",";
      tagsCSV += tags[i];
    }

    auto fnSend = NotifBridgeLoader::Instance().FnSend();
    std::string targetAddr = target_addr_;
    double timeoutSec = timeout_sec_;
    auto fut = std::async(std::launch::async, [fnSend, targetAddr, level, message, attachment, tagsCSV, timeoutSec]() {
      return fnSend(targetAddr.c_str(), level.c_str(), message.c_str(),
                    attachment.c_str(), tagsCSV.c_str(), timeoutSec);
    });
    int rc = fut.get();

    if (rc != 0) {
      std::string lastErr;
      auto fnGetErr = NotifBridgeLoader::Instance().FnGetLastError();
      auto fnFree = NotifBridgeLoader::Instance().FnFreeString();
      if (fnGetErr && fnFree) {
        char *errPtr = fnGetErr();
        if (errPtr) {
          lastErr = errPtr;
          fnFree(errPtr);
        }
      }
      logger_->Warning("Notification dispatch to " + target_addr_ +
                       " failed (rc=" + std::to_string(rc) + "): " + lastErr);
      return false;
    }

    logger_->Debug("Notification dispatched successfully to " + target_addr_ +
                   " (level=" + level + ")");
    return true;
  }

  // ---------------------------------------------------------------------------

  /// Marks the client as closed.
  void Close() { closed_ = true; }

  // ---------------------------------------------------------------------------

  const std::string &TargetAddr() const { return target_addr_; }

private:
  std::string target_addr_;
  std::shared_ptr<Logger> logger_;
  double timeout_sec_;
  bool closed_;
};

} // namespace notification
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_NOTIFICATION_CLIENT_HPP
