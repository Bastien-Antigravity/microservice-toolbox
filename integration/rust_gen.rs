use microservice_toolbox::serializers::{Serializer, JsonSerializer, BinSerializer};
use serde::Serialize;
use std::io::{self, Write};
use std::env;

#[derive(Serialize)]
struct IntegrationData {
    name: String,
    value: i32,
}

fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let args: Vec<String> = env::args().collect();
    let format = args.get(1).map(|s| s.as_str()).unwrap_or("msgpack");

    let data = IntegrationData {
        name: "Integration".to_string(),
        value: 100,
    };

    let bytes = if format == "json" {
        JsonSerializer.marshal(&data)?
    } else {
        BinSerializer.marshal(&data)?
    };

    io::stdout().write_all(&bytes)?;
    Ok(())
}
