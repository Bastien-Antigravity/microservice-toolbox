// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Cargo build script compiling Protocol Buffer definitions for teleremote.
//
// DATA FLOW:
// teleremote.proto -> tonic-build -> Generated Rust gRPC client stubs in OUT_DIR
//
// KEY PARAMETERS:
// - proto_path: Relative path to teleremote.proto.
// -----------------------------------------------------------------------------

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_path = "../go/pkg/teleremote/teleremote.proto";
    let proto_dir = "../go/pkg/teleremote";
    println!("cargo:rerun-if-changed={}", proto_path);
    tonic_prost_build::configure()
        .build_transport(false)
        .compile_protos(&[proto_path], &[proto_dir])?;
    Ok(())
}
