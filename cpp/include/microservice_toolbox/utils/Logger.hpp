#ifndef MICROSERVICE_TOOLBOX_UTILS_LOGGER_HPP
#define MICROSERVICE_TOOLBOX_UTILS_LOGGER_HPP

#include <string>
#include <iostream>
#include <memory>

namespace microservice_toolbox {
namespace utils {

/**
 * Basic Logger interface to match Toolbox pattern across Go, Python, and Rust.
 */
class Logger {
public:
    virtual ~Logger() = default;
    
    virtual void Debug(const std::string& msg) = 0;
    virtual void Info(const std::string& msg) = 0;
    virtual void Warning(const std::string& msg) = 0;
    virtual void Error(const std::string& msg) = 0;
    virtual void Critical(const std::string& msg) = 0;
    
    // Domain-specific methods
    virtual void Logon(const std::string& msg) = 0;
    virtual void Logout(const std::string& msg) = 0;
    virtual void Trade(const std::string& msg) = 0;
    virtual void Schedule(const std::string& msg) = 0;
    virtual void Report(const std::string& msg) = 0;
    virtual void Stream(const std::string& msg) = 0;
    virtual void AddMetadata(const std::string& key, const std::string& value) = 0;
};

class NoOpLogger : public Logger {
public:
    void Debug(const std::string&) override {}
    void Info(const std::string&) override {}
    void Warning(const std::string&) override {}
    void Error(const std::string&) override {}
    void Critical(const std::string&) override {}
    void Logon(const std::string&) override {}
    void Logout(const std::string&) override {}
    void Trade(const std::string&) override {}
    void Schedule(const std::string&) override {}
    void Report(const std::string&) override {}
    void Stream(const std::string&) override {}
    void AddMetadata(const std::string&, const std::string&) override {}
};

/**
 * Standard output logger for debugging and CLI tools.
 */
class StdOutLogger : public Logger {
public:
    void Debug(const std::string& msg) override { std::cout << "[DEBUG] " << msg << std::endl; }
    void Info(const std::string& msg) override { std::cout << "[INFO] " << msg << std::endl; }
    void Warning(const std::string& msg) override { std::cout << "[WARN] " << msg << std::endl; }
    void Error(const std::string& msg) override { std::cerr << "[ERROR] " << msg << std::endl; }
    void Critical(const std::string& msg) override { std::cerr << "[CRIT] " << msg << std::endl; }
    
    void Logon(const std::string& msg) override { std::cout << "[LOGON] " << msg << std::endl; }
    void Logout(const std::string& msg) override { std::cout << "[LOGOUT] " << msg << std::endl; }
    void Trade(const std::string& msg) override { std::cout << "[TRADE] " << msg << std::endl; }
    void Schedule(const std::string& msg) override { std::cout << "[SCHED] " << msg << std::endl; }
    void Report(const std::string& msg) override { std::cout << "[REPORT] " << msg << std::endl; }
    void Stream(const std::string& msg) override { std::cout << "[STREAM] " << msg << std::endl; }
    void AddMetadata(const std::string& key, const std::string& value) override {
        std::cout << "[META] " << key << "=" << value << std::endl;
    }
};

inline std::shared_ptr<Logger> EnsureSafeLogger(std::shared_ptr<Logger> logger) {
    if (logger) return logger;
    return std::make_shared<NoOpLogger>();
}

} // namespace utils
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_UTILS_LOGGER_HPP
