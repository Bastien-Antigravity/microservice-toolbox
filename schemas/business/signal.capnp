@0xafc99211f1ccdd11;

struct Signal {
  source    @0 :Text;     # Name of the generating service
  symbol    @1 :Text;
  timestamp @2 :UInt64;
  type      @3 :SignalType;
  strength  @4 :Float32;  # 0.0 to 1.0
  price     @5 :Float64;  # Suggested entry/exit price
  metadata  @6 :Text;     # Optional JSON string for extra context
}

enum SignalType {
  buy    @0;
  sell   @1;
  exit   @2;
  neutral @3;
}
