#// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\
#       // ! \\         Canonical Ecosystem Logger Cap'n Proto Schema (SSoT)     // ! \\
#       // ! \\         No underscore in label field name !!!                    // ! \\
#       // ! \\         field name camelCase                                     // ! \\
#       // ! \\         field number start = 0                                   // ! \\
#       // ! \\         enum number start = position                             // ! \\
#// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\

using Go = import "/go.capnp";
@0xfc867d59c4f2e15c;
$Go.package("logger");
$Go.import("github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/schemas/logger");

enum Level {
  notset @0;
  debug @1;
  stream @2;
  info @3;
  logon @4;
  logout @5;
  trade @6;
  schedule @7;
  report @8;
  warning @9;
  error @10;
  critical @11;
}

struct LoggerMsg {
  timestamp @0 :Text;
  hostname @1 :Text;
  loggerName @2 :Text;
  module @3 :Text;
  level @4 :Level;
  filename @5 :Text;
  functionName @6 :Text;
  lineNumber @7 :Text;
  message @8 :Text;
  pathName @9 :Text;
  processId @10 :Text;
  processName @11 :Text;
  threadId @12 :Text;
  threadName @13 :Text;
  serviceName @14 :Text;
  stackTrace @15 :Text;
}

