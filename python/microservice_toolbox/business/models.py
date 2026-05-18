#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Defines the core data structures and enums for the microservice ecosystem.
Enforces a standardized schema for Market Events, Trades, Quotes, and OHLCV data
to ensure cross-language compatibility between Python, Go, and Rust.

DATA FLOW:
1. Components instantiate these dataclasses to represent business state.
2. Serializers use these definitions to produce protocol-compliant payloads.

KEY PARAMETERS:
- MarketEvent: The primary envelope for all real-time market data.
- Signal: Standardized structure for trading strategy outputs.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List

# -----------------------------------------------------------------------------
# Market Event Standard (L1/L2)
# -----------------------------------------------------------------------------

class MarketEventType(str, Enum):
    """Standard identifiers for different types of market data events."""

    TRADE = "trade"
    QUOTE = "quote"
    ORDERBOOK_SNAPSHOT = "orderbookSnapshot"
    ORDERBOOK_UPDATE = "orderbookUpdate"
    HEARTBEAT = "heartbeat"


# -----------------------------------------------------------------------------------------------


@dataclass
class MarketEvent:
    """The primary envelope for all real-time market data across the fleet."""

    event_id: str
    symbol: str
    exchange: str
    timestamp: int  # ms
    type: MarketEventType
    payload: bytes  # Serialized Trade, Quote, or OrderBook


# -----------------------------------------------------------------------------------------------


class Aggressor(str, Enum):
    """Indicates which side initiated the trade (taker side)."""

    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


# -----------------------------------------------------------------------------------------------


@dataclass
class Trade:
    """Standardized representation of an individual trade execution."""

    price: float
    size: float
    aggressor: Aggressor
    trade_id: str


# -----------------------------------------------------------------------------------------------


@dataclass
class Quote:
    """Standardized representation of a Top-of-Book (L1) quote."""

    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float


# -----------------------------------------------------------------------------------------------


@dataclass
class OrderBookLevel:
    """A single price level in an order book."""

    price: float
    size: float


# -----------------------------------------------------------------------------------------------


@dataclass
class OrderBook:
    """Standardized representation of a Limit Order Book (L2)."""

    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)

# -----------------------------------------------------------------------------
# OHLCV Standard (Time-Series)
# -----------------------------------------------------------------------------

@dataclass
class OHLCV:
    """Standardized representation of a candlestick (Time-Series data)."""

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
    """Standard identifiers for trading signal directions."""

    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    NEUTRAL = "neutral"


# -----------------------------------------------------------------------------------------------


@dataclass
class Signal:
    """Standardized structure for strategy-generated trading signals."""

    source: str
    symbol: str
    timestamp: int
    type: SignalType
    strength: float
    price: float
    metadata: str
