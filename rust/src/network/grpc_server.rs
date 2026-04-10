use std::net::SocketAddr;
use tonic::transport::Server;
use tonic_reflection::server::Builder;

pub struct GrpcServer {
    pub addr: SocketAddr,
}

impl GrpcServer {
    pub fn new(addr: &str) -> Self {
        let addr = addr.parse().expect("Invalid address for GRPC Server");
        Self { addr }
    }

    pub async fn start<S, B>(self, service: S, descriptor_set: &'static [u8]) -> Result<(), Box<dyn std::error::Error>>
    where
        S: tonic::server::NamedService + Clone + Send + 'static,
        S: tonic::codegen::Service<http::Request<tonic::body::BoxBody>, Response = http::Response<B>> + Send + 'static,
        B: tonic::codegen::Body + Send + 'static,
        B::Error: Into<Box<dyn std::error::Error + Send + Sync>> + Send + 'static,
    {
        println!("Toolbox: GRPC Server listening on {}", self.addr);

        let reflection_service = Builder::configure()
            .register_encoded_file_descriptor_set(descriptor_set)
            .build()?;

        Server::builder()
            .add_service(reflection_service)
            .add_service(service)
            .serve(self.addr)
            .await?;

        Ok(())
    }
}
