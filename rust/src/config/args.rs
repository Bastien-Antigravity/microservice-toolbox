use clap::Parser;
use std::collections::HashMap;
use std::path::Path;

#[derive(Parser, Debug)]
#[command(author, version, about = "Microservice Toolbox CLI Parser", long_about = None)]
pub struct RawArgs {
    #[arg(long)]
    pub name: Option<String>,

    #[arg(long)]
    pub host: Option<String>,

    #[arg(long)]
    pub port: Option<u16>,

    #[arg(long)]
    pub grpc_host: Option<String>,

    #[arg(long)]
    pub grpc_port: Option<u16>,

    #[arg(long)]
    pub conf: Option<String>,

    #[arg(long)]
    pub log_level: Option<String>,

    #[arg(long)]
    pub key: Option<String>,

    /// Specific arguments in KEY=VALUE format
    #[arg(short, long)]
    pub extra: Vec<String>,
}

#[derive(Debug, Default)]
/// ToolboxArgs provides a standardized CLI interface for microservices.
/// 
/// Security & Reliability (Docker Guard):
/// If DOCKER_ENV=true, settings for host, port, grpc_host, and grpc_port 
/// are strictly IGNORED. This prevents brittle hardcoded overrides from breaking 
/// internal network-aware resolution in dynamic container environments.
pub struct ToolboxArgs {
    pub name: Option<String>,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub grpc_host: Option<String>,
    pub grpc_port: Option<u16>,
    pub conf: Option<String>,
    pub log_level: Option<String>,
    pub key: Option<String>,
    pub extras: HashMap<String, String>,
}

impl ToolboxArgs {
    pub fn parse_cli_args() -> Self {
        let raw = RawArgs::parse();
        let mut result = ToolboxArgs::default();

        // Docker Guard
        let is_docker = Path::new("/.dockerenv").exists()
            || std::env::var("DOCKER_ENV").is_ok_and(|v| v == "true");

        result.name = raw.name;
        result.conf = raw.conf;
        result.log_level = raw.log_level;
        result.key = raw.key;

        // If key provided, set it as ENV override for the decryption engine
        if let Some(k) = &result.key {
            unsafe {
                std::env::set_var("BASTIEN_PRIVATE_KEY_PATH", k);
            }
        }

        if is_docker {
            if raw.host.is_some() || raw.port.is_some() || raw.grpc_host.is_some() || raw.grpc_port.is_some() {
                println!("Toolbox (Rust): Running in Docker. Ignoring CLI network overrides to preserve network-aware resolution.");
            }
            result.host = None;
            result.port = None;
            result.grpc_host = None;
            result.grpc_port = None;
        } else {
            result.host = raw.host;
            result.port = raw.port;
            result.grpc_host = raw.grpc_host;
            result.grpc_port = raw.grpc_port;
        }

        for item in raw.extra {
            if let Some((k, v)) = item.split_once('=') {
                result.extras.insert(k.to_string(), v.to_string());
            }
        }

        result
    }
}
