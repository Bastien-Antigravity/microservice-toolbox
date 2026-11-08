// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-performance lock-free transport telemetry aggregator (WireTap) in C++17.
// Aggregates inter-service network connections and segregated information channels
// with 64-byte cache-line alignment to eliminate False Sharing and power-of-two sampling.
//
// DATA FLOW:
// Hot path packet -> relaxed atomic check -> bitmask sampling -> relaxed fetch_add -> snapshot
//
// KEY PARAMETERS:
// - GlobalEnabled(): std::atomic<bool>
// -----------------------------------------------------------------------------

#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#include "../config/json.hpp"

namespace microservice_toolbox {
namespace wiretap {

// -----------------------------------------------------------------------------
// Wire Data Contracts (100% parity with Go, Python, and Rust)
// -----------------------------------------------------------------------------

struct ChannelMetric {
    std::string channel;
    std::string category;
    std::string direction;
    uint64_t frames{0};
    uint64_t bytes{0};
    uint64_t errors{0};
    double avg_latency_ms{0.0};
    std::string last_seen;
    std::string last_payload;

    nlohmann::json to_json() const {
        nlohmann::json j = {
            {"channel", channel},
            {"category", category},
            {"direction", direction},
            {"frames", frames},
            {"bytes", bytes},
            {"errors", errors},
            {"avg_latency_ms", avg_latency_ms},
            {"last_seen", last_seen}
        };
        if (!last_payload.empty()) {
            j["last_payload"] = last_payload;
        }
        return j;
    }
};

struct EdgeReport {
    std::string source;
    std::string target;
    std::string protocol;
    std::string framing;
    int64_t active_conns{0};
    uint64_t total_frames{0};
    uint64_t total_bytes{0};
    uint64_t total_errors{0};
    std::string last_seen;
    bool is_external{false};
    std::vector<ChannelMetric> channels;

    nlohmann::json to_json() const {
        nlohmann::json ch_arr = nlohmann::json::array();
        for (const auto& ch : channels) {
            ch_arr.push_back(ch.to_json());
        }
        return {
            {"source", source},
            {"target", target},
            {"protocol", protocol},
            {"framing", framing},
            {"active_conns", active_conns},
            {"total_frames", total_frames},
            {"total_bytes", total_bytes},
            {"total_errors", total_errors},
            {"last_seen", last_seen},
            {"is_external", is_external},
            {"channels", ch_arr}
        };
    }
};

// -----------------------------------------------------------------------------
// Lock-Free Cache-Padded Atomic Structures
// -----------------------------------------------------------------------------

// Aligned to 64 bytes to prevent False Sharing across CPU cores on multi-threaded execution
struct alignas(64) AtomicChannelEntry {
    std::string channel;
    std::string category;
    std::string direction;

    std::atomic<uint64_t> frames{0};
    std::atomic<uint64_t> bytes{0};
    std::atomic<uint64_t> errors{0};
    std::atomic<uint64_t> total_lat_us{0};
    std::atomic<uint64_t> lat_samples{0};
    std::atomic<int64_t>  last_seen_ms{0};

    mutable std::shared_mutex payload_mutex;
    std::string last_payload;

    AtomicChannelEntry(std::string ch, std::string cat, std::string dir)
        : channel(std::move(ch)), category(std::move(cat)), direction(std::move(dir)) {}

    inline void Record(uint64_t byte_count, double lat_ms, bool is_error, const std::string& payload, int64_t now_ms) noexcept {
        frames.fetch_add(1, std::memory_order_relaxed);
        if (byte_count > 0) {
            bytes.fetch_add(byte_count, std::memory_order_relaxed);
        }
        if (is_error) {
            errors.fetch_add(1, std::memory_order_relaxed);
        }
        if (lat_ms > 0.0) {
            total_lat_us.fetch_add(static_cast<uint64_t>(lat_ms * 1000.0), std::memory_order_relaxed);
            lat_samples.fetch_add(1, std::memory_order_relaxed);
        }
        last_seen_ms.store(now_ms, std::memory_order_relaxed);

        if (!payload.empty()) {
            std::unique_lock<std::shared_mutex> lock(payload_mutex);
            last_payload = payload;
        }
    }
};

struct alignas(64) AtomicEdgeEntry {
    std::string source;
    std::string target;
    std::string protocol;
    std::string framing;

    std::atomic<bool>     is_external{false};
    std::atomic<int64_t>  active_conns{0};
    std::atomic<uint64_t> total_frames{0};
    std::atomic<uint64_t> total_bytes{0};
    std::atomic<uint64_t> total_errors{0};
    std::atomic<int64_t>  last_seen_ms{0};

    mutable std::shared_mutex channels_mutex;
    std::unordered_map<std::string, std::shared_ptr<AtomicChannelEntry>> channels;

    AtomicEdgeEntry(std::string src, std::string tgt, std::string proto, std::string fr)
        : source(std::move(src)), target(std::move(tgt)), protocol(std::move(proto)), framing(std::move(fr)) {}
};

// -----------------------------------------------------------------------------
// Global Telemetry State & Thread-Local Bitmask Sampling
// -----------------------------------------------------------------------------

inline std::atomic<bool>& GlobalEnabled() noexcept {
    static std::atomic<bool> g_enabled{true};
    return g_enabled;
}

inline bool IsEnabled() noexcept {
    return GlobalEnabled().load(std::memory_order_relaxed);
}

inline void SetEnabled(bool on) noexcept {
    GlobalEnabled().store(on, std::memory_order_relaxed);
}

// Power-of-two sampling check (thread-local counter, zero mutex)
inline bool ShouldSample(uint32_t mask) noexcept {
    if (mask == 0) return true;
    thread_local uint32_t counter = 0;
    return (++counter & mask) == 0;
}

inline std::string NormalizeServiceID(const std::string& raw) {
    std::string s = raw;
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
        return c == '-' ? '_' : static_cast<char>(std::tolower(c));
    });
    if (s == "09_rag_engine" || s == "rag_service" || s == "obsidian_rag") return "rag_engine";
    if (s == "08_squad_agent" || s == "squad_agent") return "agent_squad";
    if (s == "nats_server" || s == "nats_broker") return "nats";
    if (s == "postgres" || s == "postgresql" || s == "timescaledb") return "timescale_db";
    if (s == "vector_db") return "chromadb";
    return s;
}

inline std::shared_mutex& GetRegistryMutex() noexcept {
    static std::shared_mutex m;
    return m;
}

inline std::unordered_map<std::string, std::shared_ptr<AtomicEdgeEntry>>& GetEdgeRegistry() noexcept {
    static std::unordered_map<std::string, std::shared_ptr<AtomicEdgeEntry>> reg;
    return reg;
}

// -----------------------------------------------------------------------------
// Hot-Path Event Recording
// -----------------------------------------------------------------------------

inline void RecordEvent(
    const std::string& source,
    const std::string& target,
    const std::string& protocol = "TCP",
    const std::string& framing = "raw",
    const std::string& channel = "",
    const std::string& category = "data",
    const std::string& direction = "outbound",
    const std::string& payload_summary = "",
    uint64_t bytes_count = 0,
    double latency_ms = 0.0,
    bool is_err = false,
    bool is_external = false,
    int64_t conn_delta = 0
) {
    if (!IsEnabled()) {
        return;
    }

    std::string src_norm = NormalizeServiceID(source);
    std::string tgt_norm = NormalizeServiceID(target);
    if (src_norm.empty() || tgt_norm.empty()) {
        return;
    }

    std::string proto_upper = protocol;
    std::transform(proto_upper.begin(), proto_upper.end(), proto_upper.begin(), ::toupper);
    if (proto_upper.empty()) proto_upper = "TCP";

    std::string ch_name = channel;
    if (ch_name.empty()) {
        std::string p_lower = proto_upper;
        std::transform(p_lower.begin(), p_lower.end(), p_lower.begin(), ::tolower);
        ch_name = p_lower + ":default";
    }

    std::string edge_key = src_norm + "|" + tgt_norm + "|" + proto_upper;
    auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    std::shared_ptr<AtomicEdgeEntry> edge_ptr;
    {
        std::shared_lock<std::shared_mutex> rlock(GetRegistryMutex());
        auto it = GetEdgeRegistry().find(edge_key);
        if (it != GetEdgeRegistry().end()) {
            edge_ptr = it->second;
        }
    }
    if (!edge_ptr) {
        std::unique_lock<std::shared_mutex> wlock(GetRegistryMutex());
        auto& slot = GetEdgeRegistry()[edge_key];
        if (!slot) {
            slot = std::make_shared<AtomicEdgeEntry>(src_norm, tgt_norm, proto_upper, framing.empty() ? "raw" : framing);
        }
        edge_ptr = slot;
    }

    if (is_external) {
        edge_ptr->is_external.store(true, std::memory_order_relaxed);
    }
    if (conn_delta != 0) {
        int64_t new_c = edge_ptr->active_conns.fetch_add(conn_delta, std::memory_order_relaxed) + conn_delta;
        if (new_c < 0) edge_ptr->active_conns.store(0, std::memory_order_relaxed);
    } else if (edge_ptr->active_conns.load(std::memory_order_relaxed) == 0) {
        edge_ptr->active_conns.store(1, std::memory_order_relaxed);
    }

    edge_ptr->total_frames.fetch_add(1, std::memory_order_relaxed);
    if (bytes_count > 0) {
        edge_ptr->total_bytes.fetch_add(bytes_count, std::memory_order_relaxed);
    }
    if (is_err) {
        edge_ptr->total_errors.fetch_add(1, std::memory_order_relaxed);
    }
    edge_ptr->last_seen_ms.store(now_ms, std::memory_order_relaxed);

    // Channel entry retrieval/creation
    std::shared_ptr<AtomicChannelEntry> ch_ptr;
    {
        std::shared_lock<std::shared_mutex> rlock(edge_ptr->channels_mutex);
        auto it = edge_ptr->channels.find(ch_name);
        if (it != edge_ptr->channels.end()) {
            ch_ptr = it->second;
        }
    }
    if (!ch_ptr) {
        std::unique_lock<std::shared_mutex> wlock(edge_ptr->channels_mutex);
        auto& slot = edge_ptr->channels[ch_name];
        if (!slot) {
            slot = std::make_shared<AtomicChannelEntry>(
                ch_name,
                category.empty() ? "data" : category,
                direction.empty() ? "outbound" : direction
            );
        }
        ch_ptr = slot;
    }

    ch_ptr->Record(bytes_count, latency_ms, is_err, payload_summary, now_ms);
}

// -----------------------------------------------------------------------------
// Snapshot Generation
// -----------------------------------------------------------------------------

inline std::string FormatIso(int64_t ms) {
    if (ms <= 0) return "";
    auto secs = ms / 1000;
    std::time_t t = static_cast<std::time_t>(secs);
    std::tm tm_buf{};
#if defined(_WIN32)
    gmtime_s(&tm_buf, &t);
#else
    gmtime_r(&t, &tm_buf);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
    return ss.str();
}

inline std::vector<EdgeReport> Snapshot() {
    std::vector<EdgeReport> reports;
    std::shared_lock<std::shared_mutex> rlock(GetRegistryMutex());

    for (const auto& pair : GetEdgeRegistry()) {
        const auto& edge = pair.second;
        EdgeReport r;
        r.source = edge->source;
        r.target = edge->target;
        r.protocol = edge->protocol;
        r.framing = edge->framing;
        r.active_conns = edge->active_conns.load(std::memory_order_relaxed);
        r.total_frames = edge->total_frames.load(std::memory_order_relaxed);
        r.total_bytes = edge->total_bytes.load(std::memory_order_relaxed);
        r.total_errors = edge->total_errors.load(std::memory_order_relaxed);
        r.is_external = edge->is_external.load(std::memory_order_relaxed);
        r.last_seen = FormatIso(edge->last_seen_ms.load(std::memory_order_relaxed));

        {
            std::shared_lock<std::shared_mutex> ch_lock(edge->channels_mutex);
            for (const auto& ch_pair : edge->channels) {
                const auto& ce = ch_pair.second;
                ChannelMetric cm;
                cm.channel = ce->channel;
                cm.category = ce->category;
                cm.direction = ce->direction;
                cm.frames = ce->frames.load(std::memory_order_relaxed);
                cm.bytes = ce->bytes.load(std::memory_order_relaxed);
                cm.errors = ce->errors.load(std::memory_order_relaxed);
                auto samples = ce->lat_samples.load(std::memory_order_relaxed);
                cm.avg_latency_ms = samples > 0 ? (ce->total_lat_us.load(std::memory_order_relaxed) / static_cast<double>(samples)) / 1000.0 : 0.0;
                cm.last_seen = FormatIso(ce->last_seen_ms.load(std::memory_order_relaxed));
                {
                    std::shared_lock<std::shared_mutex> p_lock(ce->payload_mutex);
                    cm.last_payload = ce->last_payload;
                }
                r.channels.push_back(std::move(cm));
            }
        }

        std::sort(r.channels.begin(), r.channels.end(), [](const ChannelMetric& a, const ChannelMetric& b) {
            return a.channel < b.channel;
        });
        reports.push_back(std::move(r));
    }

    std::sort(reports.begin(), reports.end(), [](const EdgeReport& a, const EdgeReport& b) {
        if (a.source != b.source) return a.source < b.source;
        if (a.target != b.target) return a.target < b.target;
        return a.protocol < b.protocol;
    });

    return reports;
}

inline void Reset() {
    std::unique_lock<std::shared_mutex> wlock(GetRegistryMutex());
    GetEdgeRegistry().clear();
}

} // namespace wiretap
} // namespace microservice_toolbox

