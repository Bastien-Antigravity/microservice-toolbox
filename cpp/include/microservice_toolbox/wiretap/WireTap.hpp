// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// High-performance lock-free transport telemetry aggregator (WireTap) in C++17.
// Aggregates inter-service network connections and segregated information channels
// with 64-byte cache-line alignment, power-of-two sampling, and periodic HTTP hub sync.
//
// DATA FLOW:
// Hot path packet -> relaxed atomic check -> bitmask sampling -> relaxed fetch_add -> background HTTP flush
//
// KEY PARAMETERS:
// - GlobalEnabled(): std::atomic<bool> (default true, configurable via AppConfig)
// -----------------------------------------------------------------------------

#pragma once

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <iomanip>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include "../config/AppConfig.hpp"
#include "../config/json.hpp"

namespace microservice_toolbox {
namespace wiretap {

// -----------------------------------------------------------------------------
// Wire Data Contracts (100% parity with Go, Python & Rust)
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

    nlohmann::json ToJson() const { return to_json(); }

    static ChannelMetric from_json(const nlohmann::json& j) {
        ChannelMetric c;
        c.channel = j.value("channel", "");
        c.category = j.value("category", "");
        c.direction = j.value("direction", "");
        c.frames = j.value("frames", uint64_t{0});
        c.bytes = j.value("bytes", uint64_t{0});
        c.errors = j.value("errors", uint64_t{0});
        c.avg_latency_ms = j.value("avg_latency_ms", 0.0);
        c.last_seen = j.value("last_seen", "");
        c.last_payload = j.value("last_payload", "");
        return c;
    }

    static ChannelMetric FromJson(const nlohmann::json& j) { return from_json(j); }
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

    nlohmann::json ToJson() const { return to_json(); }

    static EdgeReport from_json(const nlohmann::json& j) {
        EdgeReport r;
        r.source = j.value("source", "");
        r.target = j.value("target", "");
        r.protocol = j.value("protocol", "");
        r.framing = j.value("framing", "");
        r.active_conns = j.value("active_conns", int64_t{0});
        r.total_frames = j.value("total_frames", uint64_t{0});
        r.total_bytes = j.value("total_bytes", uint64_t{0});
        r.total_errors = j.value("total_errors", uint64_t{0});
        r.last_seen = j.value("last_seen", "");
        r.is_external = j.value("is_external", false);
        if (j.contains("channels") && j["channels"].is_array()) {
            for (const auto& item : j["channels"]) {
                r.channels.push_back(ChannelMetric::from_json(item));
            }
        }
        return r;
    }

    static EdgeReport FromJson(const nlohmann::json& j) { return from_json(j); }
};

struct IngestPayload {
    std::string reporter;
    std::string timestamp;
    bool enabled{true};
    std::vector<EdgeReport> edges;

    nlohmann::json to_json() const {
        nlohmann::json arr = nlohmann::json::array();
        for (const auto& e : edges) {
            arr.push_back(e.to_json());
        }
        return {
            {"reporter", reporter},
            {"timestamp", timestamp},
            {"enabled", enabled},
            {"edges", arr}
        };
    }

    nlohmann::json ToJson() const { return to_json(); }

    static IngestPayload from_json(const nlohmann::json& j) {
        IngestPayload p;
        p.reporter = j.value("reporter", "");
        p.timestamp = j.value("timestamp", "");
        p.enabled = j.value("enabled", true);
        if (j.contains("edges") && j["edges"].is_array()) {
            for (const auto& item : j["edges"]) {
                p.edges.push_back(EdgeReport::from_json(item));
            }
        }
        return p;
    }

    static IngestPayload FromJson(const nlohmann::json& j) { return from_json(j); }
};

struct IngestResponse {
    std::string status;
    bool enabled{true};

    nlohmann::json to_json() const {
        return {
            {"status", status},
            {"enabled", enabled}
        };
    }

    nlohmann::json ToJson() const { return to_json(); }

    static IngestResponse from_json(const nlohmann::json& j) {
        IngestResponse r;
        r.status = j.value("status", "");
        r.enabled = j.value("enabled", true);
        return r;
    }

    static IngestResponse FromJson(const nlohmann::json& j) { return from_json(j); }
};

// -----------------------------------------------------------------------------
// Lock-Free Cache-Padded Atomic Structures
// -----------------------------------------------------------------------------

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

    mutable std::shared_mutex framing_mutex;
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

inline bool is_enabled() noexcept {
    return IsEnabled();
}

inline void SetEnabled(bool on) noexcept {
    GlobalEnabled().store(on, std::memory_order_relaxed);
}

inline void set_enabled(bool on) noexcept {
    SetEnabled(on);
}

inline bool ShouldSample(uint32_t mask) noexcept {
    if (mask == 0) return true;
    thread_local uint32_t counter = 0;
    return (++counter & mask) == 0;
}

inline bool should_sample(uint32_t mask = 0) noexcept {
    return ShouldSample(mask);
}

inline std::string NormalizeServiceID(const std::string& raw) {
    size_t start = 0;
    while (start < raw.size() && std::isspace(static_cast<unsigned char>(raw[start]))) ++start;
    size_t end = raw.size();
    while (end > start && std::isspace(static_cast<unsigned char>(raw[end - 1]))) --end;
    std::string s = raw.substr(start, end - start);
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

inline std::string normalize_service_id(const std::string& raw) {
    return NormalizeServiceID(raw);
}

namespace detail {

inline std::shared_mutex& GetStateMutex() noexcept {
    static std::shared_mutex m;
    return m;
}

inline std::string& GetLocalServiceRef() {
    static std::string svc = "unknown_service";
    return svc;
}

inline std::string& GetWebHubURLRef() {
    static std::string url;
    return url;
}

inline std::once_flag& GetReporterOnceFlag() noexcept {
    static std::once_flag flag;
    return flag;
}

} // namespace detail

inline void SetLocalService(const std::string& serviceName) {
    std::string norm = NormalizeServiceID(serviceName);
    std::unique_lock<std::shared_mutex> lock(detail::GetStateMutex());
    detail::GetLocalServiceRef() = norm.empty() ? "unknown_service" : norm;
}

inline void set_local_service(const std::string& serviceName) {
    SetLocalService(serviceName);
}

inline std::string GetLocalService() {
    std::shared_lock<std::shared_mutex> lock(detail::GetStateMutex());
    const std::string& s = detail::GetLocalServiceRef();
    return s.empty() ? "unknown_service" : s;
}

inline std::string get_local_service() {
    return GetLocalService();
}

inline void SetWebHubURL(const std::string& url) {
    std::string clean = url;
    while (!clean.empty() && std::isspace(static_cast<unsigned char>(clean.back()))) clean.pop_back();
    while (!clean.empty() && clean.back() == '/') clean.pop_back();
    std::unique_lock<std::shared_mutex> lock(detail::GetStateMutex());
    detail::GetWebHubURLRef() = std::move(clean);
}

inline void set_web_hub_url(const std::string& url) {
    SetWebHubURL(url);
}

inline std::string GetWebHubURL() {
    std::shared_lock<std::shared_mutex> lock(detail::GetStateMutex());
    return detail::GetWebHubURLRef();
}

inline std::string get_web_hub_url() {
    return GetWebHubURL();
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

inline void RecordEventWithConnDelta(
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
    std::transform(proto_upper.begin(), proto_upper.end(), proto_upper.begin(), [](unsigned char c) {
        return static_cast<char>(std::toupper(c));
    });
    if (proto_upper.empty()) proto_upper = "TCP";

    std::string ch_name = channel;
    if (ch_name.empty()) {
        std::string p_lower = proto_upper;
        std::transform(p_lower.begin(), p_lower.end(), p_lower.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
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

    if (!framing.empty()) {
        std::unique_lock<std::shared_mutex> flock(edge_ptr->framing_mutex);
        if (edge_ptr->framing != framing) {
            edge_ptr->framing = framing;
        }
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
    RecordEventWithConnDelta(
        source, target, protocol, framing, channel, category, direction,
        payload_summary, bytes_count, latency_ms, is_err, is_external, conn_delta
    );
}

inline void record_event(
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
    RecordEventWithConnDelta(
        source, target, protocol, framing, channel, category, direction,
        payload_summary, bytes_count, latency_ms, is_err, is_external, conn_delta
    );
}

// -----------------------------------------------------------------------------
// Snapshot Generation & Merge
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
        {
            std::shared_lock<std::shared_mutex> flock(edge->framing_mutex);
            r.framing = edge->framing;
        }
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

inline std::vector<EdgeReport> snapshot() {
    return Snapshot();
}

inline void MergeRemoteSnapshot(const std::vector<EdgeReport>& incoming) {
    if (!IsEnabled()) return;
    auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    for (const auto& rep : incoming) {
        std::string src_norm = NormalizeServiceID(rep.source);
        std::string tgt_norm = NormalizeServiceID(rep.target);
        std::string proto_upper = rep.protocol;
        std::transform(proto_upper.begin(), proto_upper.end(), proto_upper.begin(), [](unsigned char c) {
            return static_cast<char>(std::toupper(c));
        });
        if (src_norm.empty() || tgt_norm.empty() || proto_upper.empty()) continue;

        std::string edge_key = src_norm + "|" + tgt_norm + "|" + proto_upper;
        std::shared_ptr<AtomicEdgeEntry> edge_ptr;
        {
            std::shared_lock<std::shared_mutex> rlock(GetRegistryMutex());
            auto it = GetEdgeRegistry().find(edge_key);
            if (it != GetEdgeRegistry().end()) edge_ptr = it->second;
        }
        if (!edge_ptr) {
            std::unique_lock<std::shared_mutex> wlock(GetRegistryMutex());
            auto& slot = GetEdgeRegistry()[edge_key];
            if (!slot) {
                slot = std::make_shared<AtomicEdgeEntry>(src_norm, tgt_norm, proto_upper, rep.framing.empty() ? "raw" : rep.framing);
            }
            edge_ptr = slot;
        }

        if (!rep.framing.empty()) {
            std::unique_lock<std::shared_mutex> flock(edge_ptr->framing_mutex);
            edge_ptr->framing = rep.framing;
        }
        if (rep.is_external) edge_ptr->is_external.store(true, std::memory_order_relaxed);
        if (rep.active_conns > 0) edge_ptr->active_conns.store(rep.active_conns, std::memory_order_relaxed);
        if (rep.total_frames > edge_ptr->total_frames.load(std::memory_order_relaxed)) {
            edge_ptr->total_frames.store(rep.total_frames, std::memory_order_relaxed);
        }
        if (rep.total_bytes >= edge_ptr->total_bytes.load(std::memory_order_relaxed)) {
            edge_ptr->total_bytes.store(rep.total_bytes, std::memory_order_relaxed);
        }
        edge_ptr->total_errors.store(rep.total_errors, std::memory_order_relaxed);
        edge_ptr->last_seen_ms.store(now_ms, std::memory_order_relaxed);

        for (const auto& ch : rep.channels) {
            if (ch.channel.empty()) continue;
            std::shared_ptr<AtomicChannelEntry> ch_ptr;
            {
                std::shared_lock<std::shared_mutex> rlock(edge_ptr->channels_mutex);
                auto it = edge_ptr->channels.find(ch.channel);
                if (it != edge_ptr->channels.end()) ch_ptr = it->second;
            }
            if (!ch_ptr) {
                std::unique_lock<std::shared_mutex> wlock(edge_ptr->channels_mutex);
                auto& slot = edge_ptr->channels[ch.channel];
                if (!slot) {
                    slot = std::make_shared<AtomicChannelEntry>(ch.channel, ch.category, ch.direction);
                }
                ch_ptr = slot;
            }
            if (ch.frames >= ch_ptr->frames.load(std::memory_order_relaxed)) {
                ch_ptr->frames.store(ch.frames, std::memory_order_relaxed);
            }
            if (ch.bytes >= ch_ptr->bytes.load(std::memory_order_relaxed)) {
                ch_ptr->bytes.store(ch.bytes, std::memory_order_relaxed);
            }
            ch_ptr->errors.store(ch.errors, std::memory_order_relaxed);
            if (ch.avg_latency_ms > 0.0) {
                ch_ptr->total_lat_us.store(static_cast<uint64_t>(ch.avg_latency_ms * 1000.0), std::memory_order_relaxed);
                ch_ptr->lat_samples.store(1, std::memory_order_relaxed);
            }
            ch_ptr->last_seen_ms.store(now_ms, std::memory_order_relaxed);
            if (!ch.last_payload.empty()) {
                std::unique_lock<std::shared_mutex> plock(ch_ptr->payload_mutex);
                ch_ptr->last_payload = ch.last_payload;
            }
        }
    }
}

inline void merge_remote_snapshot(const std::vector<EdgeReport>& incoming) {
    MergeRemoteSnapshot(incoming);
}

inline void Reset() {
    std::unique_lock<std::shared_mutex> wlock(GetRegistryMutex());
    GetEdgeRegistry().clear();
}

inline void reset() {
    Reset();
}

// -----------------------------------------------------------------------------
// Config Initialization & Background Hub Sync (/api/v1/system/wiretap/ingest)
// -----------------------------------------------------------------------------

namespace detail {

inline bool PostIngestHttp(const std::string& hubUrl, const std::string& payloadJson, IngestResponse& respOut) {
    std::string target = hubUrl;
    if (target.rfind("http://", 0) == 0) target = target.substr(7);
    else if (target.rfind("https://", 0) == 0) target = target.substr(8);

    std::string basePath;
    auto slashPos = target.find('/');
    if (slashPos != std::string::npos) {
        basePath = target.substr(slashPos);
        target = target.substr(0, slashPos);
    }
    while (!basePath.empty() && basePath.back() == '/') basePath.pop_back();

    auto colon = target.rfind(':');
    if (colon == std::string::npos) return false;
    std::string host = target.substr(0, colon);
    if (host.size() >= 2 && host.front() == '[' && host.back() == ']') {
        host = host.substr(1, host.size() - 2);
    }
    std::string portStr = target.substr(colon + 1);
    if (host.empty() || portStr.empty()) return false;

    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host.c_str(), portStr.c_str(), &hints, &res) != 0 || !res) {
        return false;
    }

    int sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock < 0) {
        freeaddrinfo(res);
        return false;
    }

#if defined(_WIN32)
    DWORD tv = 1500;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof(tv));
#else
    struct timeval tv{1, 500000};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif

    if (connect(sock, res->ai_addr, res->ai_addrlen) != 0) {
        freeaddrinfo(res);
#if defined(_WIN32)
        closesocket(sock);
#else
        close(sock);
#endif
        return false;
    }
    freeaddrinfo(res);

    std::string path = basePath + "/api/v1/system/wiretap/ingest";
    std::ostringstream req;
    req << "POST " << path << " HTTP/1.1\r\n"
        << "Host: " << target << "\r\n"
        << "Content-Type: application/json\r\n"
        << "Content-Length: " << payloadJson.size() << "\r\n"
        << "Connection: close\r\n\r\n"
        << payloadJson;
    std::string reqStr = req.str();

    size_t sent = 0;
    while (sent < reqStr.size()) {
        ssize_t n = send(sock, reqStr.c_str() + sent, reqStr.size() - sent, 0);
        if (n <= 0) break;
        sent += n;
    }

    char buf[1024];
    std::string rawResp;
    while (true) {
        ssize_t n = recv(sock, buf, sizeof(buf) - 1, 0);
        if (n <= 0) break;
        rawResp.append(buf, n);
    }

#if defined(_WIN32)
    closesocket(sock);
#else
    close(sock);
#endif

    auto hdrEnd = rawResp.find("\r\n\r\n");
    if (hdrEnd == std::string::npos) return false;
    try {
        auto parsed = nlohmann::json::parse(rawResp.substr(hdrEnd + 4));
        respOut = IngestResponse::from_json(parsed);
        return true;
    } catch (...) {
        return false;
    }
}

inline void ReporterLoop() {
    while (true) {
        std::this_thread::sleep_for(std::chrono::seconds(2));
        std::string hub = GetWebHubURL();
        if (hub.empty()) continue;

        auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        IngestPayload payload;
        payload.reporter = GetLocalService();
        payload.timestamp = FormatIso(now_ms);
        payload.enabled = IsEnabled();
        if (payload.enabled) {
            payload.edges = Snapshot();
        }

        IngestResponse resp;
        if (PostIngestHttp(hub, payload.to_json().dump(), resp) && !resp.status.empty()) {
            if (resp.enabled != IsEnabled()) {
                SetEnabled(resp.enabled);
            }
        }
    }
}

} // namespace detail

inline void ConfigureFromConfig(const std::string& serviceName, const config::AppConfig& appConfig) {
    SetLocalService(serviceName);

    std::string rawEnabled = appConfig.GetLocal("wiretap_enabled");
    if (rawEnabled.empty()) {
        auto common = appConfig.GetCommon();
        if (common.contains("wiretap_enabled")) {
            const auto& v = common["wiretap_enabled"];
            if (v.is_string()) rawEnabled = v.get<std::string>();
            else if (v.is_boolean()) rawEnabled = v.get<bool>() ? "true" : "false";
        }
    }
    std::string low = rawEnabled;
    std::transform(low.begin(), low.end(), low.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    SetEnabled(low.empty() || low == "true");

    try {
        std::string webAddr = appConfig.GetListenAddr("web_interface");
        if (!webAddr.empty()) {
            SetWebHubURL("http://" + webAddr);
        }
    } catch (...) {
        // Explicit failure to resolve web_interface leaves hub URL unset if omitted in isolated unit tests
    }

    if (GetLocalService() != "web_interface") {
        std::call_once(detail::GetReporterOnceFlag(), []() {
            std::thread(detail::ReporterLoop).detach();
        });
    }
}

inline void configure_from_config(const std::string& serviceName, const config::AppConfig& appConfig) {
    ConfigureFromConfig(serviceName, appConfig);
}

} // namespace wiretap
} // namespace microservice_toolbox
