use std::net::SocketAddr;
use std::str::FromStr;
use tonic::transport::Server;
use tonic::transport::server::Router;
use tonic_reflection::server::Builder;
use crate::connectivity::resolver::new_resolver;

/// GrpcServer is a standardized gRPC server wrapper for the microservice-toolbox.
pub struct GrpcServer {
    pub addr: SocketAddr,
    builder: Router,
}

impl GrpcServer {
    /// Creates a new GrpcServer, resolving the address using Docker Guard logic.
    pub fn new(addr: &str) -> Self {
        let resolver = new_resolver();
        
        // Apply Docker Guard Suppression
        let resolved_addr_str = resolver.resolve_full_bind_addr(addr).unwrap_or_else(|_| addr.to_string());
        
        if resolved_addr_str != addr {
            println!("Toolbox: Docker Guard suppressed bind address {} -> {}", addr, resolved_addr_str);
        }

        let addr_parsed = SocketAddr::from_str(&resolved_addr_str)
            .unwrap_or_else(|_| "0.0.0.0:0".parse().unwrap());

        // Initialize with a simple "base" router.
        let reflection_service = Builder::configure()
            .build_v1()
            .unwrap();

        Self {
            addr: addr_parsed,
            builder: Server::builder().add_service(reflection_service),
        }
    }

    pub fn add_service<S>(mut self, service: S) -> Self
    where
        S: tonic::server::NamedService
            + Clone
            + Send
            + Sync
            + 'static,
        S: tonic::codegen::Service<
            tonic::codegen::http::Request<tonic::body::Body>,
            Response = tonic::codegen::http::Response<tonic::body::Body>,
            Error = std::convert::Infallible,
        >,
        S::Future: Send + 'static,
    {
        self.builder = self.builder.add_service(service);
        self
    }

    pub fn add_reflection(mut self, file_descriptor_set: &[u8]) -> Self {
        let reflection_service = Builder::configure()
            .register_encoded_file_descriptor_set(file_descriptor_set)
            .build_v1()
            .unwrap();
        self.builder = self.builder.add_service(reflection_service);
        self
    }

    pub async fn start(self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        println!("Toolbox: GRPC Server listening on {}", self.addr);
        self.builder.serve(self.addr).await?;
        Ok(())
    }
}
