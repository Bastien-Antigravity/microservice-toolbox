@0xd96f9211fbccdd55;

struct MarketEvent {
  eventId   @0 :Text;
  symbol    @1 :Text;
  exchange  @2 :Text;
  timestamp @3 :UInt64;
  type      @4 :EventType;
  payload   @5 :Data;   # Serialized Trade, Quote, or OrderBook message
}

enum EventType {
  trade              @0;
  quote              @1;
  orderbookSnapshot  @2;
  orderbookUpdate    @3;
  heartbeat          @4;
  control            @5;
}

struct Trade {
  price     @0 :Float64;
  size      @1 :Float64;
  aggressor @2 :Aggressor;
  tradeId   @3 :Text;
}

enum Aggressor {
  buy     @0;
  sell    @1;
  unknown @2;
}

struct Quote {
  bidPrice @0 :Float64;
  bidSize  @1 :Float64;
  askPrice @2 :Float64;
  askSize  @3 :Float64;
}

struct OrderBookLevel {
  price @0 :Float64;
  size  @1 :Float64;
}

struct OrderBook {
  bids @0 :List(OrderBookLevel);
  asks @1 :List(OrderBookLevel);
}
