// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Top-level logger module providing uniform logging interfaces and safe loggers.
//
// DATA FLOW:
// Log Calls (Debug, Info, Warning, Error, Critical) -> Dispatcher Sink
//
// KEY PARAMETERS:
// - Logger: Abstract interface matching ecosystem universal logging contract.
// - EnsureSafeLogger: Fallback to NoOpLogger if passed nullptr.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_LOGGER_LOGGER_HPP
#define MICROSERVICE_TOOLBOX_LOGGER_LOGGER_HPP

#include "../utils/Logger.hpp"

namespace microservice_toolbox {
namespace logger {

// -----------------------------------------------------------------------------

using Logger = utils::Logger;
using NoOpLogger = utils::NoOpLogger;
using StdOutLogger = utils::StdOutLogger;

inline std::shared_ptr<Logger> EnsureSafeLogger(std::shared_ptr<Logger> l) {
    return utils::EnsureSafeLogger(l);
}

// -----------------------------------------------------------------------------

} // namespace logger
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_LOGGER_LOGGER_HPP
