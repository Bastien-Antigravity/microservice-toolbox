use std::net::SocketAddr;
use tonic::transport::{Server, server::Router};
use tonic_reflection::server::Builder;
use tonic::body::BoxBody;

pub struct GrpcServer {
    pub addr: SocketAddr,
    builder: Router,
}

impl GrpcServer {
    pub fn new(addr: &str, descriptor_set: &'static [u8]) -> Self {
        let addr = addr.parse().expect("Invalid address for GRPC Server");
        
        let reflection_service = Builder::configure()
            .register_encoded_file_descriptor_set(descriptor_set)
            .build()
            .expect("Failed to build reflection service");

        let builder = Server::builder()
            .add_service(reflection_service);

        Self { addr, builder }
    }

    pub fn add_service<S>(mut self, service: S) -> Self 
    where
        S: tonic::server::NamedService + Clone + Send + 'static,
        S: tonic::codegen::Service<tonic::codegen::http::Request<BoxBody>, Response = tonic::codegen::http::Response<BoxBody>, Error = std::convert::Infallible> + Send + 'static,
        S::Future: Send + 'static,
    {
        self.builder = self.builder.add_service(service);
        self
    }

    pub async fn start(self) -> Result<(), Box<dyn std::error::Error>> {
        println!("Toolbox: GRPC Server listening on {}", self.addr);
        self.builder.serve(self.addr).await?;
        Ok(())
    }
}
