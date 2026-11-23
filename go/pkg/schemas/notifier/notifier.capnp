#// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\
#       // ! \\         Canonical Ecosystem Notifier Cap'n Proto Schema (SSoT)   // ! \\
#       // ! \\         No underscore in label field name !!!                    // ! \\
#       // ! \\         field name lowercase                                     // ! \\
#       // ! \\         field number start = 0                                   // ! \\
#       // ! \\         enum number start = 0                                    // ! \\
#// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\// ! \\

using Go = import "/go.capnp";
@0xcd0e7dad96752db7;
$Go.package("notifier");
$Go.import("github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/schemas/notifier");

struct NotifierMsg {
  message @0 :Text;
  attachment @1 :Text = "";
  tags @2 :List(Text) = ["telegram"];
  level @3 :Text = "";
}

