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
    pub conf: Option<String>,

    #[arg(long)]
    pub log_level: Option<String>,

    /// Specific arguments in KEY=VALUE format
    #[arg(short, long)]
    pub extra: Vec<String>,
}

#[derive(Debug, Default)]
pub struct ToolboxArgs {
    pub name: Option<String>,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub conf: Option<String>,
    pub log_level: Option<String>,
    pub extras: HashMap<String, String>,
}

impl ToolboxArgs {
    pub fn parse() -> Self {
        let raw = RawArgs::parse();
        let mut result = ToolboxArgs::default();

        // Docker Guard
        let is_docker = Path::new("/.dockerenv").exists() || std::env::var("DOCKER_ENV").is_ok();

        result.name = raw.name;
        result.conf = raw.conf;
        result.log_level = raw.log_level;

        if is_docker {
            if raw.host.is_some() || raw.port.is_some() {
                println!("Toolbox (Rust): Running in Docker. Ignoring CLI overrides for --host and --port to preserve network-aware resolution.");
            }
            result.host = None;
            result.port = None;
        } else {
            result.host = raw.host;
            result.port = raw.port;
        }

        for item in raw.extra {
            if let Some((k, v)) = item.split_once('=') {
                result.extras.insert(k.to_string(), v.to_string());
            }
        }

        result
    }
}
