import unittest
from microservice_toolbox.business import (
    Trade, Aggressor, MarketEventType, 
    wrap_market_event, serialize, deserialize,
    OHLCV, Signal, SignalType, MarketEvent
)

class TestBusinessModels(unittest.TestCase):
    def test_market_event_serialization(self):
        trade = Trade(
            price=100.50,
            size=1.5,
            aggressor=Aggressor.BUY,
            trade_id="T12345"
        )

        event = wrap_market_event("BTC/USD", "Binance", MarketEventType.TRADE, trade)
        self.assertEqual(event.symbol, "BTC/USD")

        data = serialize(event)
        self.assertIsInstance(data, bytes)

        decoded_event = deserialize(data, MarketEvent)
        self.assertEqual(decoded_event.type, MarketEventType.TRADE)

        decoded_trade = deserialize(decoded_event.payload, Trade)
        self.assertEqual(decoded_trade.price, 100.50)
        self.assertEqual(decoded_trade.aggressor, Aggressor.BUY)

    def test_ohlcv_serialization(self):
        bar = OHLCV(
            symbol="ETH/USD",
            interval="1m",
            timestamp=1620000000000,
            open=2500.0,
            high=2510.0,
            low=2495.0,
            close=2505.0,
            volume=100.0,
            vwap=2502.0,
            trades=50
        )

        data = serialize(bar)
        decoded_bar = deserialize(data, OHLCV)
        self.assertEqual(decoded_bar.symbol, "ETH/USD")
        self.assertEqual(decoded_bar.trades, 50)

    def test_signal_serialization(self):
        sig = Signal(
            source="technical-analysis",
            symbol="SOL/USD",
            timestamp=1620000000000,
            type=SignalType.BUY,
            strength=0.85,
            price=150.0,
            metadata='{"reason": "RSI"}'
        )

        data = serialize(sig)
        decoded_sig = deserialize(data, Signal)
        self.assertEqual(decoded_sig.type, SignalType.BUY)
        self.assertEqual(decoded_sig.strength, 0.85)

if __name__ == '__main__':
    unittest.main()
