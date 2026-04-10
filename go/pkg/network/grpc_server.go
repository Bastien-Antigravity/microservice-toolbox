package network

import (
	"fmt"
	"net"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// GRPCServer is a standardized wrapper for gRPC servers in the toolbox.
type GRPCServer struct {
	Server *grpc.Server
	Addr   string
}

// NewGRPCServer creates a new gRPC server wrapper.
func NewGRPCServer(addr string, opts ...grpc.ServerOption) *GRPCServer {
	s := grpc.NewServer(opts...)
	reflection.Register(s) // Enable reflection by default for debugging
	return &GRPCServer{
		Server: s,
		Addr:   addr,
	}
}

// Start begins listening and serving.
func (s *GRPCServer) Start() error {
	lis, err := net.Listen("tcp", s.Addr)
	if err != nil {
		return fmt.Errorf("failed to listen: %v", err)
	}
	fmt.Printf("Toolbox: GRPC Server listening on %s\n", s.Addr)
	return s.Server.Serve(lis)
}

// Stop performs a graceful shutdown.
func (s *GRPCServer) Stop() {
	fmt.Println("Toolbox: Stopping GRPC Server...")
	s.Server.GracefulStop()
}
