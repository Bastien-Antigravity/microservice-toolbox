#ifndef MICROSERVICE_TOOLBOX_BUSINESS_MODELS_HPP
#define MICROSERVICE_TOOLBOX_BUSINESS_MODELS_HPP

#include <string>
#include <vector>
#include <cstdint>
#include "../config/json.hpp"

namespace microservice_toolbox {
namespace business {

using json = nlohmann::json;

// -----------------------------------------------------------------------------
// Market Event Standard (L1/L2)
// -----------------------------------------------------------------------------

enum class MarketEventType {
    Trade,
    Quote,
    OrderBookSnapshot,
    OrderBookUpdate,
    Heartbeat
};

// Helper to convert MarketEventType to string for JSON
inline std::string to_string(MarketEventType t) {
    switch (t) {
        case MarketEventType::Trade: return "trade";
        case MarketEventType::Quote: return "quote";
        case MarketEventType::OrderBookSnapshot: return "orderbookSnapshot";
        case MarketEventType::OrderBookUpdate: return "orderbookUpdate";
        case MarketEventType::Heartbeat: return "heartbeat";
        default: return "unknown";
    }
}

struct MarketEvent {
    std::string event_id;
    std::string symbol;
    std::string exchange;
    uint64_t timestamp;
    MarketEventType type;
    std::vector<uint8_t> payload;

    json to_json() const {
        return json{
            {"eventId", event_id},
            {"symbol", symbol},
            {"exchange", exchange},
            {"timestamp", timestamp},
            {"type", to_string(type)},
            {"payload", payload}
        };
    }
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

struct Trade {
    double price;
    double size;
    Aggressor aggressor;
    std::string trade_id;

    json to_json() const {
        return json{
            {"price", price},
            {"size", size},
            {"aggressor", to_string(aggressor)},
            {"tradeId", trade_id}
        };
    }
};

// -----------------------------------------------------------------------------
// OHLCV Standard (Time-Series)
// -----------------------------------------------------------------------------

struct OHLCV {
    std::string symbol;
    std::string interval;
    uint64_t timestamp;
    double open;
    double high;
    double low;
    double close;
    double volume;
    double vwap;
    uint32_t trades;

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

struct Signal {
    std::string source;
    std::string symbol;
    uint64_t timestamp;
    SignalType type;
    float strength;
    double price;
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
};

} // namespace business
} // namespace microservice_toolbox

#endif // MICROSERVICE_TOOLBOX_BUSINESS_MODELS_HPP
