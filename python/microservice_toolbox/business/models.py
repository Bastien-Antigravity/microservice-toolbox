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

from dataclasses import dataclass as dcDataclass, field as dcField
from enum import Enum as enumEnum
from typing import List as typeList

# -----------------------------------------------------------------------------------------------
# Market Event Standard (L1/L2)
# -----------------------------------------------------------------------------------------------

class MarketEventType(str, enumEnum):
    """Standard identifiers for different types of market data events."""

    TRADE = "trade"
    QUOTE = "quote"
    ORDERBOOK_SNAPSHOT = "orderbookSnapshot"
    ORDERBOOK_UPDATE = "orderbookUpdate"
    HEARTBEAT = "heartbeat"
    CONTROL = "control"


# -----------------------------------------------------------------------------------------------


@dcDataclass
class MarketEvent:
    """The primary envelope for all real-time market data across the fleet."""

    event_id: str
    symbol: str
    exchange: str
    timestamp: int  # ms
    type: MarketEventType
    payload: bytes  # Serialized Trade, Quote, or OrderBook


# -----------------------------------------------------------------------------------------------


class Aggressor(str, enumEnum):
    """Indicates which side initiated the trade (taker side)."""

    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


# -----------------------------------------------------------------------------------------------


@dcDataclass
class Trade:
    """Standardized representation of an individual trade execution."""

    price: float
    size: float
    aggressor: Aggressor
    trade_id: str


# -----------------------------------------------------------------------------------------------


@dcDataclass
class Quote:
    """Standardized representation of a Top-of-Book (L1) quote."""

    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float


# -----------------------------------------------------------------------------------------------


@dcDataclass
class OrderBookLevel:
    """A single price level in an order book."""

    price: float
    size: float


# -----------------------------------------------------------------------------------------------


@dcDataclass
class OrderBook:
    """Standardized representation of a Limit Order Book (L2)."""

    bids: typeList[OrderBookLevel] = dcField(default_factory=list)
    asks: typeList[OrderBookLevel] = dcField(default_factory=list)

# -----------------------------------------------------------------------------------------------
# OHLCV Standard (Time-Series)
# -----------------------------------------------------------------------------------------------

@dcDataclass
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

# -----------------------------------------------------------------------------------------------
# Signal Standard (Trading Strategy)
# -----------------------------------------------------------------------------------------------

class SignalType(str, enumEnum):
    """Standard identifiers for trading signal directions."""

    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    NEUTRAL = "neutral"


# -----------------------------------------------------------------------------------------------


@dcDataclass
class Signal:
    """Standardized structure for strategy-generated trading signals."""

    source: str
    symbol: str
    timestamp: int
    type: SignalType
    strength: float
    price: float
    metadata: str
