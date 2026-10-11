// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Cargo build script compiling Protocol Buffer definitions for teleremote & notification.
//
// DATA FLOW:
// *.proto -> tonic-build -> Generated Rust gRPC client stubs in OUT_DIR
//
// KEY PARAMETERS:
// - teleremote.proto, notif_service.proto
// -----------------------------------------------------------------------------

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let teleremote_proto = "../go/pkg/teleremote/teleremote.proto";
    let teleremote_dir = "../go/pkg/teleremote";
    let notif_proto = "../go/pkg/notification/proto/notif_service.proto";
    let notif_dir = "../go/pkg/notification/proto";

    println!("cargo:rerun-if-changed={}", teleremote_proto);
    println!("cargo:rerun-if-changed={}", notif_proto);

    tonic_prost_build::configure()
        .build_transport(false)
        .compile_protos(
            &[teleremote_proto, notif_proto],
            &[teleremote_dir, notif_dir],
        )?;
    Ok(())
}
