#ifndef MICROSERVICE_TOOLBOX_LIFECYCLE_MANAGER_HPP
#define MICROSERVICE_TOOLBOX_LIFECYCLE_MANAGER_HPP

#include <vector>
#include <string>
#include <functional>
#include <csignal>
#include <atomic>
#include <iostream>
#include <mutex>
#include <thread>
#include "../utils/Logger.hpp"

namespace microservice_toolbox {
namespace lifecycle {

using ShutdownFunc = std::function<void()>;

struct CleanupEntry {
    std::string name;
    ShutdownFunc func;
};

class LifecycleManager {
public:
    LifecycleManager(std::shared_ptr<utils::Logger> logger = nullptr)
        : logger_(utils::EnsureSafeLogger(logger)), shutdown_requested(false) {
        instance_ = this;
    }

    ~LifecycleManager() {
        if (instance_ == this) instance_ = nullptr;
    }

    void Register(const std::string& name, ShutdownFunc fn) {
        std::lock_guard<std::mutex> lock(mutex_);
        cleanups_.push_back({name, fn});
    }

    void Wait() {
        std::signal(SIGINT, SignalHandler);
        std::signal(SIGTERM, SignalHandler);

        while (!shutdown_requested.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        ExecuteCleanups();
    }

    void ExecuteCleanups() {
        std::lock_guard<std::mutex> lock(mutex_);
        // Execute cleanups in reverse order (LIFO)
        for (auto it = cleanups_.rbegin(); it != cleanups_.rend(); ++it) {
            try {
                logger_->Info("Lifecycle: Running cleanup '" + it->name + "'...");
                it->func();
            } catch (const std::exception& e) {
                logger_->Error("Lifecycle: Cleanup '" + it->name + "' failed: " + e.what());
            } catch (...) {
                logger_->Error("Lifecycle: Cleanup '" + it->name + "' failed with unknown error");
            }
        }
        logger_->Info("Lifecycle: Clean shutdown completed.");
    }

    static void RequestShutdown() {
        if (instance_) {
            instance_->shutdown_requested.store(true);
        }
    }

private:
    static void SignalHandler(int sig) {
        if (instance_) {
            instance_->logger_->Info("Lifecycle: Received signal " + std::to_string(sig) + ". Initiating graceful shutdown...");
            instance_->shutdown_requested.store(true);
        }
    }

    static LifecycleManager* instance_;
    std::shared_ptr<utils::Logger> logger_;
    std::vector<CleanupEntry> cleanups_;
    std::atomic<bool> shutdown_requested;
    std::mutex mutex_;
};

// Initialize static member
#ifdef MICROSERVICE_TOOLBOX_LIFECYCLE_IMPL
LifecycleManager* LifecycleManager::instance_ = nullptr;
#endif

} // namespace lifecycle
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_LIFECYCLE_MANAGER_HPP
