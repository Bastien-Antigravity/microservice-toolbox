package business

// -----------------------------------------------------------------------------
// Market Event Standard (L1/L2)
// -----------------------------------------------------------------------------

type MarketEventType string

const (
	TypeTrade             MarketEventType = "trade"
	TypeQuote             MarketEventType = "quote"
	TypeOrderBookSnapshot MarketEventType = "orderbookSnapshot"
	TypeOrderBookUpdate   MarketEventType = "orderbookUpdate"
	TypeHeartbeat         MarketEventType = "heartbeat"
)

type MarketEvent struct {
	EventID   string          `json:"event_id"`
	Symbol    string          `json:"symbol"`
	Exchange  string          `json:"exchange"`
	Timestamp uint64          `json:"timestamp"`
	Type      MarketEventType `json:"type"`
	Payload   []byte          `json:"payload"` // Serialized Trade, Quote, or OrderBook
}

type Aggressor string

const (
	AggressorBuy     Aggressor = "buy"
	AggressorSell    Aggressor = "sell"
	AggressorUnknown Aggressor = "unknown"
)

type Trade struct {
	Price     float64   `json:"price"`
	Size      float64   `json:"size"`
	Aggressor Aggressor `json:"aggressor"` // taker, trade initiator...
	TradeID   string    `json:"trade_id"`
}

type Quote struct {
	BidPrice float64 `json:"bid_price"`
	BidSize  float64 `json:"bid_size"`
	AskPrice float64 `json:"ask_price"`
	AskSize  float64 `json:"ask_size"`
}

type OrderBookLevel struct {
	Price float64 `json:"price"`
	Size  float64 `json:"size"`
}

type OrderBook struct {
	Bids []OrderBookLevel `json:"bids"`
	Asks []OrderBookLevel `json:"asks"`
}

// -----------------------------------------------------------------------------
// OHLCV Standard (Time-Series)
// -----------------------------------------------------------------------------

type OHLCV struct {
	Symbol    string  `json:"symbol"`
	Interval  string  `json:"interval"`
	Timestamp uint64  `json:"timestamp"`
	Open      float64 `json:"open"`
	High      float64 `json:"high"`
	Low       float64 `json:"low"`
	Close     float64 `json:"close"`
	Volume    float64 `json:"volume"`
	VWAP      float64 `json:"vwap"`
	Trades    uint32  `json:"trades"`
}

// -----------------------------------------------------------------------------
// Signal Standard (Trading Strategy)
// -----------------------------------------------------------------------------

type SignalType string

const (
	SignalBuy     SignalType = "buy"
	SignalSell    SignalType = "sell"
	SignalExit    SignalType = "exit"
	SignalNeutral SignalType = "neutral"
)

type Signal struct {
	Source    string     `json:"source"`
	Symbol    string     `json:"symbol"`
	Timestamp uint64     `json:"timestamp"`
	Type      SignalType `json:"type"`
	Strength  float32    `json:"strength"`
	Price     float64    `json:"price"`
	Metadata  string     `json:"metadata"`
}
