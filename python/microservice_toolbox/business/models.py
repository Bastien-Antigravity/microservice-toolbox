from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Any
import json
import time

# -----------------------------------------------------------------------------
# Market Event Standard (L1/L2)
# -----------------------------------------------------------------------------

class MarketEventType(str, Enum):
    TRADE = "trade"
    QUOTE = "quote"
    ORDERBOOK_SNAPSHOT = "orderbookSnapshot"
    ORDERBOOK_UPDATE = "orderbookUpdate"
    HEARTBEAT = "heartbeat"

@dataclass
class MarketEvent:
    event_id: str
    symbol: str
    exchange: str
    timestamp: int  # ms
    type: MarketEventType
    payload: bytes  # Serialized Trade, Quote, or OrderBook

class Aggressor(str, Enum):
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"

@dataclass
class Trade:
    price: float
    size: float
    aggressor: Aggressor
    trade_id: str

@dataclass
class Quote:
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float

@dataclass
class OrderBookLevel:
    price: float
    size: float

@dataclass
class OrderBook:
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)

# -----------------------------------------------------------------------------
# OHLCV Standard (Time-Series)
# -----------------------------------------------------------------------------

@dataclass
class OHLCV:
    symbol: str
    interval: str
    timestamp: int  # ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float
    trades: int

# -----------------------------------------------------------------------------
# Signal Standard (Trading Strategy)
# -----------------------------------------------------------------------------

class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    NEUTRAL = "neutral"

@dataclass
class Signal:
    source: str
    symbol: str
    timestamp: int
    type: SignalType
    strength: float
    price: float
    metadata: str
