@0xb3e59211faccaa44;

struct OHLCV {
  symbol    @0 :Text;
  interval  @1 :Text;    # e.g., "1m", "5m", "1h"
  timestamp @2 :UInt64;  # Start of the bar
  open      @3 :Float64;
  high      @4 :Float64;
  low       @5 :Float64;
  close     @6 :Float64;
  volume    @7 :Float64;
  vwap      @8 :Float64;
  trades    @9 :UInt32;
}
