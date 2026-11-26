// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Cross-service and cross-brain mission trace correlation (X-Bastien-Mission-ID)
// for C++17 microservices. Sanitizes, extracts, injects, and binds mission_id
// into structured Logger metadata.
//
// DATA FLOW:
// Inbound HTTP / NATS Header / Env -> SanitizeMissionId -> Logger::AddMetadata("mission_id")
//
// KEY PARAMETERS:
// - kHeaderMissionId: Canonical wire header ("X-Bastien-Mission-ID").
// - kMetadataKey: Canonical universal-logger metadata slot ("mission_id").
// - kEnvMissionId: Process environment seed ("X_BASTIEN_MISSION_ID").
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_TRACE_MISSION_TRACE_HPP
#define MICROSERVICE_TOOLBOX_TRACE_MISSION_TRACE_HPP

#include <cstdlib>
#include <map>
#include <memory>
#include <string>

#include "../logger/Logger.hpp"

namespace microservice_toolbox {
namespace trace {

// -----------------------------------------------------------------------------

constexpr const char* kHeaderMissionId = "X-Bastien-Mission-ID";
constexpr const char* kMetadataKey = "mission_id";
constexpr const char* kEnvMissionId = "X_BASTIEN_MISSION_ID";
constexpr std::size_t kMaxMissionIdLen = 128;

// -----------------------------------------------------------------------------

inline std::string SanitizeMissionId(const std::string& raw) {
    const auto first = raw.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }
    const auto last = raw.find_last_not_of(" \t\r\n");
    std::string trimmed = raw.substr(first, last - first + 1);
    if (trimmed.empty() || trimmed.size() > kMaxMissionIdLen) {
        return "";
    }
    for (unsigned char ch : trimmed) {
        if (ch < 0x21 || ch > 0x7E) {
            return "";
        }
    }
    return trimmed;
}

// -----------------------------------------------------------------------------

inline std::string ResolveEnvMissionId() {
    const char* raw = std::getenv(kEnvMissionId);
    if (raw == nullptr) {
        return "";
    }
    return SanitizeMissionId(std::string(raw));
}

// -----------------------------------------------------------------------------

inline void BindLoggerMission(const std::shared_ptr<logger::Logger>& log, const std::string& mission_id) {
    if (!log) {
        return;
    }
    const std::string clean = SanitizeMissionId(mission_id);
    if (!clean.empty()) {
        log->AddMetadata(kMetadataKey, clean);
    }
}

// -----------------------------------------------------------------------------

inline void InjectHeaders(std::map<std::string, std::string>& headers, const std::string& mission_id) {
    const std::string clean = SanitizeMissionId(mission_id);
    if (!clean.empty()) {
        headers[kHeaderMissionId] = clean;
    }
}

} // namespace trace
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_TRACE_MISSION_TRACE_HPP
