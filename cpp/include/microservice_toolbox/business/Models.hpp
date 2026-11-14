// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Defines canonical market domain models (MarketEvent, Trade, Quote, OrderBook,
// OHLCV, Signal) and Base64-compatible JSON serialization helpers across C++17.
//
// DATA FLOW:
// Market Feed <-> Serialize/Deserialize/WrapMarketEvent <-> JSON Byte Vectors
//
// KEY PARAMETERS:
// - MarketEvent: Primary market envelope with Base64-encoded JSON payload.
// - OHLCV: Standardized candlestick bar structure.
// - Signal: Standardized trading strategy signal structure.
// -----------------------------------------------------------------------------

#ifndef MICROSERVICE_TOOLBOX_BUSINESS_MODELS_HPP
#define MICROSERVICE_TOOLBOX_BUSINESS_MODELS_HPP

#include <cctype>
#include <chrono>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>
#include "../config/json.hpp"

namespace microservice_toolbox {
namespace business {

using json = nlohmann::json;

// -----------------------------------------------------------------------------
// RFC 4648 Base64 Codec for MarketEvent.payload Parity (Go/Python/Rust)
// -----------------------------------------------------------------------------

namespace detail {

inline std::string Base64Encode(const std::vector<uint8_t>& input) {
    static constexpr char kTable[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve(((input.size() + 2) / 3) * 4);
    for (size_t i = 0; i < input.size(); i += 3) {
        uint32_t b0 = input[i];
        uint32_t b1 = (i + 1 < input.size()) ? input[i + 1] : 0;
        uint32_t b2 = (i + 2 < input.size()) ? input[i + 2] : 0;
        uint32_t triple = (b0 << 16) | (b1 << 8) | b2;
        out.push_back(kTable[(triple >> 18) & 0x3F]);
        out.push_back(kTable[(triple >> 12) & 0x3F]);
        out.push_back((i + 1 < input.size()) ? kTable[(triple >> 6) & 0x3F] : '=');
        out.push_back((i + 2 < input.size()) ? kTable[triple & 0x3F] : '=');
    }
    return out;
}

inline int Base64CharVal(unsigned char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

inline std::vector<uint8_t> Base64Decode(const std::string& input) {
    std::string clean;
    clean.reserve(input.size());
    for (unsigned char c : input) {
        if (!std::isspace(c)) clean.push_back(static_cast<char>(c));
    }
    if (clean.empty()) return {};
    if (clean.size() % 4 != 0) {
        throw std::runtime_error("business: invalid base64 payload length");
    }
    std::vector<uint8_t> out;
    out.reserve((clean.size() / 4) * 3);
    for (size_t i = 0; i < clean.size(); i += 4) {
        int v0 = Base64CharVal(static_cast<unsigned char>(clean[i]));
        int v1 = Base64CharVal(static_cast<unsigned char>(clean[i + 1]));
        bool pad2 = (clean[i + 2] == '=');
        bool pad3 = (clean[i + 3] == '=');
        int v2 = pad2 ? 0 : Base64CharVal(static_cast<unsigned char>(clean[i + 2]));
        int v3 = pad3 ? 0 : Base64CharVal(static_cast<unsigned char>(clean[i + 3]));
        if (v0 < 0 || v1 < 0 || v2 < 0 || v3 < 0) {
            throw std::runtime_error("business: invalid base64 character in payload");
        }
        uint32_t triple = (static_cast<uint32_t>(v0) << 18) |
                          (static_cast<uint32_t>(v1) << 12) |
                          (static_cast<uint32_t>(v2) << 6) |
                          static_cast<uint32_t>(v3);
        out.push_back(static_cast<uint8_t>((triple >> 16) & 0xFF));
        if (!pad2) out.push_back(static_cast<uint8_t>((triple >> 8) & 0xFF));
        if (!pad3) out.push_back(static_cast<uint8_t>(triple & 0xFF));
    }
    return out;
}

} // namespace detail

// -----------------------------------------------------------------------------
// Market Event Standard (L1/L2)
// -----------------------------------------------------------------------------

enum class MarketEventType {
    Trade,
    Quote,
    OrderBookSnapshot,
    OrderBookUpdate,
    Heartbeat,
    Control
};

inline std::string to_string(MarketEventType t) {
    switch (t) {
        case MarketEventType::Trade: return "trade";
        case MarketEventType::Quote: return "quote";
        case MarketEventType::OrderBookSnapshot: return "orderbookSnapshot";
        case MarketEventType::OrderBookUpdate: return "orderbookUpdate";
        case MarketEventType::Heartbeat: return "heartbeat";
        case MarketEventType::Control: return "control";
        default: return "unknown";
    }
}

inline MarketEventType MarketEventTypeFromString(const std::string& s) {
    if (s == "trade") return MarketEventType::Trade;
    if (s == "quote") return MarketEventType::Quote;
    if (s == "orderbookSnapshot") return MarketEventType::OrderBookSnapshot;
    if (s == "orderbookUpdate") return MarketEventType::OrderBookUpdate;
    if (s == "heartbeat") return MarketEventType::Heartbeat;
    if (s == "control") return MarketEventType::Control;
    throw std::runtime_error("business: unknown MarketEventType: " + s);
}

struct MarketEvent {
    std::string event_id;
    std::string symbol;
    std::string exchange;
    uint64_t timestamp{0};
    MarketEventType type{MarketEventType::Trade};
    std::vector<uint8_t> payload;

    json to_json() const {
        return json{
            {"event_id", event_id},
            {"symbol", symbol},
            {"exchange", exchange},
            {"timestamp", timestamp},
            {"type", to_string(type)},
            {"payload", detail::Base64Encode(payload)}
        };
    }

    json ToJson() const { return to_json(); }

    static MarketEvent from_json(const json& j) {
        MarketEvent e;
        e.event_id = j.value("event_id", "");
        e.symbol = j.value("symbol", "");
        e.exchange = j.value("exchange", "");
        e.timestamp = j.value("timestamp", uint64_t{0});
        if (j.contains("type") && j["type"].is_string()) {
            e.type = MarketEventTypeFromString(j["type"].get<std::string>());
        }
        if (j.contains("payload")) {
            if (j["payload"].is_string()) {
                e.payload = detail::Base64Decode(j["payload"].get<std::string>());
            } else if (j["payload"].is_array()) {
                e.payload = j["payload"].get<std::vector<uint8_t>>();
            }
        }
        return e;
    }

    static MarketEvent FromJson(const json& j) { return from_json(j); }
};

enum class Aggressor {
    Buy,
    Sell,
    Unknown
};

inline std::string to_string(Aggressor a) {
    switch (a) {
        case Aggressor::Buy: return "buy";
        case Aggressor::Sell: return "sell";
        default: return "unknown";
    }
}

inline Aggressor AggressorFromString(const std::string& s) {
    if (s == "buy") return Aggressor::Buy;
    if (s == "sell") return Aggressor::Sell;
    if (s == "unknown") return Aggressor::Unknown;
    throw std::runtime_error("business: unknown Aggressor: " + s);
}

struct Trade {
    double price{0.0};
    double size{0.0};
    Aggressor aggressor{Aggressor::Unknown};
    std::string trade_id;

    json to_json() const {
        return json{
            {"price", price},
            {"size", size},
            {"aggressor", to_string(aggressor)},
            {"trade_id", trade_id}
        };
    }

    json ToJson() const { return to_json(); }

    static Trade from_json(const json& j) {
        Trade t;
        t.price = j.value("price", 0.0);
        t.size = j.value("size", 0.0);
        if (j.contains("aggressor") && j["aggressor"].is_string()) {
            t.aggressor = AggressorFromString(j["aggressor"].get<std::string>());
        }
        t.trade_id = j.value("trade_id", "");
        return t;
    }

    static Trade FromJson(const json& j) { return from_json(j); }
};

struct Quote {
    double bid_price{0.0};
    double bid_size{0.0};
    double ask_price{0.0};
    double ask_size{0.0};

    json to_json() const {
        return json{
            {"bid_price", bid_price},
            {"bid_size", bid_size},
            {"ask_price", ask_price},
            {"ask_size", ask_size}
        };
    }

    json ToJson() const { return to_json(); }

    static Quote from_json(const json& j) {
        Quote q;
        q.bid_price = j.value("bid_price", 0.0);
        q.bid_size = j.value("bid_size", 0.0);
        q.ask_price = j.value("ask_price", 0.0);
        q.ask_size = j.value("ask_size", 0.0);
        return q;
    }

    static Quote FromJson(const json& j) { return from_json(j); }
};

struct OrderBookLevel {
    double price{0.0};
    double size{0.0};

    json to_json() const {
        return json{
            {"price", price},
            {"size", size}
        };
    }

    json ToJson() const { return to_json(); }

    static OrderBookLevel from_json(const json& j) {
        OrderBookLevel lvl;
        lvl.price = j.value("price", 0.0);
        lvl.size = j.value("size", 0.0);
        return lvl;
    }

    static OrderBookLevel FromJson(const json& j) { return from_json(j); }
};

struct OrderBook {
    std::vector<OrderBookLevel> bids;
    std::vector<OrderBookLevel> asks;

    json to_json() const {
        json b = json::array();
        for (const auto& l : bids) b.push_back(l.to_json());
        json a = json::array();
        for (const auto& l : asks) a.push_back(l.to_json());
        return json{
            {"bids", b},
            {"asks", a}
        };
    }

    json ToJson() const { return to_json(); }

    static OrderBook from_json(const json& j) {
        OrderBook ob;
        if (j.contains("bids") && j["bids"].is_array()) {
            for (const auto& item : j["bids"]) {
                ob.bids.push_back(OrderBookLevel::from_json(item));
            }
        }
        if (j.contains("asks") && j["asks"].is_array()) {
            for (const auto& item : j["asks"]) {
                ob.asks.push_back(OrderBookLevel::from_json(item));
            }
        }
        return ob;
    }

    static OrderBook FromJson(const json& j) { return from_json(j); }
};

// -----------------------------------------------------------------------------
// OHLCV Standard (Time-Series)
// -----------------------------------------------------------------------------

struct OHLCV {
    std::string symbol;
    std::string interval;
    uint64_t timestamp{0};
    double open{0.0};
    double high{0.0};
    double low{0.0};
    double close{0.0};
    double volume{0.0};
    double vwap{0.0};
    uint32_t trades{0};

    json to_json() const {
        return json{
            {"symbol", symbol},
            {"interval", interval},
            {"timestamp", timestamp},
            {"open", open},
            {"high", high},
            {"low", low},
            {"close", close},
            {"volume", volume},
            {"vwap", vwap},
            {"trades", trades}
        };
    }

    json ToJson() const { return to_json(); }

    static OHLCV from_json(const json& j) {
        OHLCV c;
        c.symbol = j.value("symbol", "");
        c.interval = j.value("interval", "");
        c.timestamp = j.value("timestamp", uint64_t{0});
        c.open = j.value("open", 0.0);
        c.high = j.value("high", 0.0);
        c.low = j.value("low", 0.0);
        c.close = j.value("close", 0.0);
        c.volume = j.value("volume", 0.0);
        c.vwap = j.value("vwap", 0.0);
        c.trades = j.value("trades", uint32_t{0});
        return c;
    }

    static OHLCV FromJson(const json& j) { return from_json(j); }
};

// -----------------------------------------------------------------------------
// Signal Standard (Trading Strategy)
// -----------------------------------------------------------------------------

enum class SignalType {
    Buy,
    Sell,
    Exit,
    Neutral
};

inline std::string to_string(SignalType s) {
    switch (s) {
        case SignalType::Buy: return "buy";
        case SignalType::Sell: return "sell";
        case SignalType::Exit: return "exit";
        case SignalType::Neutral: return "neutral";
        default: return "unknown";
    }
}

inline SignalType SignalTypeFromString(const std::string& s) {
    if (s == "buy") return SignalType::Buy;
    if (s == "sell") return SignalType::Sell;
    if (s == "exit") return SignalType::Exit;
    if (s == "neutral") return SignalType::Neutral;
    throw std::runtime_error("business: unknown SignalType: " + s);
}

struct Signal {
    std::string source;
    std::string symbol;
    uint64_t timestamp{0};
    SignalType type{SignalType::Neutral};
    float strength{0.0f};
    double price{0.0};
    std::string metadata;

    json to_json() const {
        return json{
            {"source", source},
            {"symbol", symbol},
            {"timestamp", timestamp},
            {"type", to_string(type)},
            {"strength", strength},
            {"price", price},
            {"metadata", metadata}
        };
    }

    json ToJson() const { return to_json(); }

    static Signal from_json(const json& j) {
        Signal sig;
        sig.source = j.value("source", "");
        sig.symbol = j.value("symbol", "");
        sig.timestamp = j.value("timestamp", uint64_t{0});
        if (j.contains("type") && j["type"].is_string()) {
            sig.type = SignalTypeFromString(j["type"].get<std::string>());
        }
        sig.strength = j.value("strength", 0.0f);
        sig.price = j.value("price", 0.0);
        sig.metadata = j.value("metadata", "");
        return sig;
    }

    static Signal FromJson(const json& j) { return from_json(j); }
};

// -----------------------------------------------------------------------------
// ADL JSON Hooks & Ecosystem Helper Functions (Parity with Go/Python/Rust)
// -----------------------------------------------------------------------------

inline void to_json(json& j, const MarketEvent& v) { j = v.to_json(); }
inline void from_json(const json& j, MarketEvent& v) { v = MarketEvent::from_json(j); }
inline void to_json(json& j, const Trade& v) { j = v.to_json(); }
inline void from_json(const json& j, Trade& v) { v = Trade::from_json(j); }
inline void to_json(json& j, const Quote& v) { j = v.to_json(); }
inline void from_json(const json& j, Quote& v) { v = Quote::from_json(j); }
inline void to_json(json& j, const OrderBookLevel& v) { j = v.to_json(); }
inline void from_json(const json& j, OrderBookLevel& v) { v = OrderBookLevel::from_json(j); }
inline void to_json(json& j, const OrderBook& v) { j = v.to_json(); }
inline void from_json(const json& j, OrderBook& v) { v = OrderBook::from_json(j); }
inline void to_json(json& j, const OHLCV& v) { j = v.to_json(); }
inline void from_json(const json& j, OHLCV& v) { v = OHLCV::from_json(j); }
inline void to_json(json& j, const Signal& v) { j = v.to_json(); }
inline void from_json(const json& j, Signal& v) { v = Signal::from_json(j); }

inline uint64_t SystemTimestamp() {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count());
}

inline uint64_t system_timestamp() { return SystemTimestamp(); }

template <typename T>
inline std::vector<uint8_t> Serialize(const T& obj) {
    std::string dumped = json(obj).dump();
    return std::vector<uint8_t>(dumped.begin(), dumped.end());
}

template <typename T>
inline std::vector<uint8_t> serialize(const T& obj) {
    return Serialize(obj);
}

template <typename T>
inline T Deserialize(const std::vector<uint8_t>& data) {
    std::string raw(data.begin(), data.end());
    return T::from_json(json::parse(raw));
}

template <typename T>
inline T deserialize(const std::vector<uint8_t>& data) {
    return Deserialize<T>(data);
}

template <typename T>
inline MarketEvent WrapMarketEvent(
    const std::string& symbol,
    const std::string& exchange,
    MarketEventType eventType,
    const T& payload) {
    uint64_t ts = SystemTimestamp();
    MarketEvent ev;
    ev.event_id = symbol + "-" + std::to_string(ts);
    ev.symbol = symbol;
    ev.exchange = exchange;
    ev.timestamp = ts;
    ev.type = eventType;
    ev.payload = Serialize(payload);
    return ev;
}

template <typename T>
inline MarketEvent wrap_market_event(
    const std::string& symbol,
    const std::string& exchange,
    MarketEventType event_type,
    const T& payload) {
    return WrapMarketEvent(symbol, exchange, event_type, payload);
}

} // namespace business
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_BUSINESS_MODELS_HPP
