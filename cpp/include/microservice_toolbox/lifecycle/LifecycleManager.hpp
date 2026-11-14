// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Core microservice-toolbox module: LifecycleManager.hpp.
// Captures OS signals (SIGINT, SIGTERM) and executes cleanup hooks in LIFO order.
//
// DATA FLOW:
// OS Signals / RequestShutdown -> LifecycleManager::Wait() -> LIFO ExecuteCleanups()
//
// KEY PARAMETERS:
// - cleanups_: Synchronized hook stack executed in reverse registration order.
// - shutdown_requested_: Per-instance atomic wakeup flag.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_LIFECYCLE_MANAGER_HPP
#define MICROSERVICE_TOOLBOX_LIFECYCLE_MANAGER_HPP

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>
#include "../utils/Logger.hpp"

namespace microservice_toolbox {
namespace lifecycle {

using ShutdownFunc = std::function<void()>;

struct CleanupEntry {
    std::string name;
    ShutdownFunc func;
};

namespace detail {

inline std::atomic<int>& PendingSignalFlag() noexcept {
    static std::atomic<int> sig{0};
    return sig;
}

inline std::atomic<bool>& GlobalShutdownFlag() noexcept {
    static std::atomic<bool> flag{false};
    return flag;
}

} // namespace detail

class LifecycleManager {
public:
    explicit LifecycleManager(std::shared_ptr<utils::Logger> logger = nullptr)
        : logger_(utils::EnsureSafeLogger(logger)), shutdown_requested_(false) {}

    void Register(const std::string& name, ShutdownFunc fn) {
        std::lock_guard<std::mutex> lock(mutex_);
        cleanups_.push_back({name, std::move(fn)});
    }

    void register_hook(const std::string& name, ShutdownFunc fn) {
        Register(name, std::move(fn));
    }

    void Wait() {
        detail::PendingSignalFlag().store(0, std::memory_order_relaxed);
        detail::GlobalShutdownFlag().store(false, std::memory_order_relaxed);
        std::signal(SIGINT, SignalHandler);
        std::signal(SIGTERM, SignalHandler);

        {
            std::unique_lock<std::mutex> lock(cv_mutex_);
            while (!shutdown_requested_.load(std::memory_order_relaxed) &&
                   !detail::GlobalShutdownFlag().load(std::memory_order_relaxed) &&
                   detail::PendingSignalFlag().load(std::memory_order_relaxed) == 0) {
                cv_.wait_for(lock, std::chrono::milliseconds(50));
            }
        }

        int sig = detail::PendingSignalFlag().load(std::memory_order_relaxed);
        if (sig != 0) {
            logger_->Info("Lifecycle: Received signal " + std::to_string(sig) + ". Initiating graceful shutdown...");
        } else {
            logger_->Info("Lifecycle: Shutdown requested. Initiating graceful shutdown...");
        }

        ExecuteCleanups();
    }

    void wait() { Wait(); }

    void ExecuteCleanups() {
        std::vector<CleanupEntry> hooks;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            hooks.swap(cleanups_);
        }
        // Execute cleanups in reverse order (LIFO)
        for (auto it = hooks.rbegin(); it != hooks.rend(); ++it) {
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

    void execute_cleanups() { ExecuteCleanups(); }

    void RequestInstanceShutdown() {
        shutdown_requested_.store(true, std::memory_order_relaxed);
        cv_.notify_all();
    }

    static void RequestShutdown() {
        detail::GlobalShutdownFlag().store(true, std::memory_order_relaxed);
    }

private:
    static void SignalHandler(int sig) {
        detail::PendingSignalFlag().store(sig, std::memory_order_relaxed);
    }

    std::shared_ptr<utils::Logger> logger_;
    std::vector<CleanupEntry> cleanups_;
    std::atomic<bool> shutdown_requested_;
    std::mutex mutex_;
    std::mutex cv_mutex_;
    std::condition_variable cv_;
};

// -----------------------------------------------------------------------------

inline std::shared_ptr<LifecycleManager> NewManager() {
    return std::make_shared<LifecycleManager>(nullptr);
}

inline std::shared_ptr<LifecycleManager> NewManagerWithLogger(std::shared_ptr<utils::Logger> logger) {
    return std::make_shared<LifecycleManager>(std::move(logger));
}

inline std::shared_ptr<LifecycleManager> new_manager() {
    return NewManager();
}

inline std::shared_ptr<LifecycleManager> new_manager_with_logger(std::shared_ptr<utils::Logger> logger) {
    return NewManagerWithLogger(std::move(logger));
}

} // namespace lifecycle
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_LIFECYCLE_MANAGER_HPP
