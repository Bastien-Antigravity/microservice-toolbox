package network

import (
	"fmt"
	"net"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/utils"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// GRPCServer is a standardized wrapper for gRPC servers in the toolbox.
type GRPCServer struct {
	Server *grpc.Server
	Addr   string
	Logger utils.Logger
}

// NewGRPCServer creates a new gRPC server wrapper with default logging.
func NewGRPCServer(addr string, opts ...grpc.ServerOption) *GRPCServer {
	return NewGRPCServerWithLogger(addr, nil, opts...)
}

// NewGRPCServerWithLogger creates a new gRPC server wrapper with an explicit logger.
func NewGRPCServerWithLogger(addr string, logger utils.Logger, opts ...grpc.ServerOption) *GRPCServer {
	s := grpc.NewServer(opts...)
	reflection.Register(s) // Enable reflection by default for debugging
	return &GRPCServer{
		Server: s,
		Addr:   addr,
		Logger: utils.EnsureSafeLogger(logger),
	}
}

// Start begins listening and serving.
func (s *GRPCServer) Start() error {
	lis, err := net.Listen("tcp", s.Addr)
	if err != nil {
		return fmt.Errorf("failed to listen: %v", err)
	}
	s.Logger.Info("Toolbox: GRPC Server listening on %s", s.Addr)
	return s.Server.Serve(lis)
}

// Stop performs a graceful shutdown.
func (s *GRPCServer) Stop() {
	s.Logger.Info("Toolbox: Stopping GRPC Server...")
	s.Server.GracefulStop()
}
