use microservice_toolbox::serializers::{Serializer, JsonSerializer, BinSerializer};
use serde::Deserialize;
use std::io::{self, Read};
use std::env;
use std::process;

#[derive(Deserialize, Debug, PartialEq)]
struct IntegrationData {
    name: String,
    value: i32,
}

fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let args: Vec<String> = env::args().collect();
    let format = args.get(1).map(|s| s.as_str()).unwrap_or("msgpack");

    let mut buffer = Vec::new();
    io::stdin().read_to_end(&mut buffer)?;

    let decoded: IntegrationData = if format == "json" {
        JsonSerializer.unmarshal(&buffer)?
    } else {
        BinSerializer.unmarshal(&buffer)?
    };

    let expected = IntegrationData {
        name: "Integration".to_string(),
        value: 100,
    };

    if decoded == expected {
        eprintln!("Rust: Success ({})", format);
        process::exit(0);
    } else {
        eprintln!("Rust: Data mismatch ({}) - Got {:?}", format, decoded);
        process::exit(1);
    }
}
