package wiretap

// =============================================================================
// ESSENTIAL PROCESS:
// Provides distinct, lock-free atomic switchable gRPC client and server
// interceptors (Unary and Streaming) to track real-time gRPC connections and
// segregated RPC methods (e.g., /teleremote.TeleRemoteService/Connect,
// /notification.NotifService/SendNotification) across the microservice fleet.
//
// DATA FLOW:
// 1. Input: gRPC Unary or Stream invocation (Client or Server).
// 2. Logic: Lock-free `IsEnabled()` check. When enabled, injects/reads
//    `x-source-service` metadata, wraps bidirectional streams, and records
//    per-method frame, byte, and latency telemetry.
// 3. Output: Segregated gRPC channel telemetry in WireTap store.
//
// KEY PARAMETERS:
// - targetServiceHint: Optional explicit peer service identifier.
// =============================================================================

import (
	"context"
	"strings"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/proto"
)

const metadataSourceServiceKey = "x-source-service"

// ClientDialOptions returns gRPC DialOptions with the lock-free switchable
// WireTap Unary and Stream client interceptors pre-configured.
func ClientDialOptions(targetServiceHint string) []grpc.DialOption {
	return []grpc.DialOption{
		grpc.WithChainUnaryInterceptor(UnaryClientInterceptor(targetServiceHint)),
		grpc.WithChainStreamInterceptor(StreamClientInterceptor(targetServiceHint)),
	}
}

// ServerOptions returns gRPC ServerOptions with the lock-free switchable
// WireTap Unary and Stream server interceptors pre-configured.
func ServerOptions() []grpc.ServerOption {
	return []grpc.ServerOption{
		grpc.ChainUnaryInterceptor(UnaryServerInterceptor()),
		grpc.ChainStreamInterceptor(StreamServerInterceptor()),
	}
}

// UnaryClientInterceptor returns a gRPC UnaryClientInterceptor guarded by the
// lock-free atomic switch.
func UnaryClientInterceptor(targetServiceHint string) grpc.UnaryClientInterceptor {
	return func(
		ctx context.Context,
		method string,
		req, reply any,
		cc *grpc.ClientConn,
		invoker grpc.UnaryInvoker,
		opts ...grpc.CallOption,
	) error {
		self := GetLocalService()
		if self != "" && self != "unknown_service" {
			ctx = metadata.AppendToOutgoingContext(ctx, metadataSourceServiceKey, self)
		}

		if !IsEnabled() {
			return invoker(ctx, method, req, reply, cc, opts...)
		}

		start := time.Now()
		err := invoker(ctx, method, req, reply, cc, opts...)
		latMs := float64(time.Since(start).Microseconds()) / 1000.0

		target := resolveGRPCTarget(targetServiceHint, cc.Target(), method)
		bytesCount := estimateProtoSize(req) + estimateProtoSize(reply)

		RecordEvent(
			self,
			target,
			"GRPC",
			"HTTP/2 Protobuf (Unary)",
			method,
			"rpc:unary",
			"outbound",
			method,
			bytesCount,
			latMs,
			err != nil,
			false,
		)
		return err
	}
}

// StreamClientInterceptor returns a gRPC StreamClientInterceptor guarded by the
// lock-free atomic switch, decorating bidirectional streams (such as tele-remote).
func StreamClientInterceptor(targetServiceHint string) grpc.StreamClientInterceptor {
	return func(
		ctx context.Context,
		desc *grpc.StreamDesc,
		cc *grpc.ClientConn,
		method string,
		streamer grpc.Streamer,
		opts ...grpc.CallOption,
	) (grpc.ClientStream, error) {
		self := GetLocalService()
		if self != "" && self != "unknown_service" {
			ctx = metadata.AppendToOutgoingContext(ctx, metadataSourceServiceKey, self)
		}

		start := time.Now()
		clientStream, err := streamer(ctx, desc, cc, method, opts...)
		latMs := float64(time.Since(start).Microseconds()) / 1000.0

		target := resolveGRPCTarget(targetServiceHint, cc.Target(), method)

		if IsEnabled() {
			connDelta := int64(1)
			if err != nil {
				connDelta = 0
			}
			RecordEventWithConnDelta(
				self,
				target,
				"GRPC",
				"HTTP/2 Protobuf (Stream)",
				method,
				"rpc:stream",
				"bidirectional",
				"stream:open",
				0,
				latMs,
				err != nil,
				false,
				connDelta,
			)
		}

		if err != nil || clientStream == nil {
			return clientStream, err
		}

		return &wiretapClientStream{
			ClientStream: clientStream,
			source:       self,
			target:       target,
			method:       method,
		}, nil
	}
}

type wiretapClientStream struct {
	grpc.ClientStream
	source string
	target string
	method string
}

func (w *wiretapClientStream) SendMsg(m any) error {
	err := w.ClientStream.SendMsg(m)
	if IsEnabled() {
		RecordEvent(
			w.source,
			w.target,
			"GRPC",
			"HTTP/2 Protobuf (Stream)",
			w.method,
			"rpc:stream:send",
			"outbound",
			"stream:send",
			estimateProtoSize(m),
			0,
			err != nil,
			false,
		)
	}
	return err
}

func (w *wiretapClientStream) RecvMsg(m any) error {
	err := w.ClientStream.RecvMsg(m)
	if IsEnabled() {
		connDelta := int64(0)
		if err != nil {
			connDelta = -1
		}
		RecordEventWithConnDelta(
			w.source,
			w.target,
			"GRPC",
			"HTTP/2 Protobuf (Stream)",
			w.method,
			"rpc:stream:recv",
			"inbound",
			"stream:recv",
			estimateProtoSize(m),
			0,
			err != nil,
			false,
			connDelta,
		)
	}
	return err
}

// UnaryServerInterceptor returns a gRPC UnaryServerInterceptor guarded by the
// lock-free atomic switch.
func UnaryServerInterceptor() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req any,
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (any, error) {
		if !IsEnabled() {
			return handler(ctx, req)
		}

		start := time.Now()
		resp, err := handler(ctx, req)
		latMs := float64(time.Since(start).Microseconds()) / 1000.0

		caller := extractCallerFromContext(ctx)
		self := GetLocalService()
		bytesCount := estimateProtoSize(req) + estimateProtoSize(resp)

		RecordEvent(
			caller,
			self,
			"GRPC",
			"HTTP/2 Protobuf (Unary)",
			info.FullMethod,
			"rpc:unary",
			"inbound",
			info.FullMethod,
			bytesCount,
			latMs,
			err != nil,
			false,
		)
		return resp, err
	}
}

// StreamServerInterceptor returns a gRPC StreamServerInterceptor guarded by the
// lock-free atomic switch.
func StreamServerInterceptor() grpc.StreamServerInterceptor {
	return func(
		srv any,
		ss grpc.ServerStream,
		info *grpc.StreamServerInfo,
		handler grpc.StreamHandler,
	) error {
		caller := extractCallerFromContext(ss.Context())
		self := GetLocalService()

		if IsEnabled() {
			RecordEventWithConnDelta(
				caller,
				self,
				"GRPC",
				"HTTP/2 Protobuf (Stream)",
				info.FullMethod,
				"rpc:stream",
				"bidirectional",
				"stream:accept",
				0,
				0,
				false,
				false,
				1,
			)
		}

		err := handler(srv, ss)

		if IsEnabled() {
			RecordEventWithConnDelta(
				caller,
				self,
				"GRPC",
				"HTTP/2 Protobuf (Stream)",
				info.FullMethod,
				"rpc:stream",
				"bidirectional",
				"stream:close",
				0,
				0,
				err != nil,
				false,
				-1,
			)
		}
		return err
	}
}

func resolveGRPCTarget(hint, ccTarget, method string) string {
	if hint != "" {
		return NormalizeServiceID(hint)
	}
	if byAddr := ResolveServiceByAddr(ccTarget); byAddr != "" {
		return byAddr
	}
	mLower := strings.ToLower(method)
	switch {
	case strings.Contains(mLower, "teleremote"):
		return "tele_remote"
	case strings.Contains(mLower, "notif"):
		return "notif_server"
	case strings.Contains(mLower, "rag"):
		return "rag_engine"
	case strings.Contains(mLower, "config"):
		return "config_server"
	case strings.Contains(mLower, "log"):
		return "log_server"
	case strings.Contains(mLower, "squad"):
		return "agent_squad"
	}
	return "grpc_peer"
}

func extractCallerFromContext(ctx context.Context) string {
	if md, ok := metadata.FromIncomingContext(ctx); ok {
		if vals := md.Get(metadataSourceServiceKey); len(vals) > 0 && vals[0] != "" {
			return NormalizeServiceID(vals[0])
		}
	}
	return "grpc_client"
}

func estimateProtoSize(msg any) int {
	if msg == nil {
		return 0
	}
	if pm, ok := msg.(proto.Message); ok {
		return proto.Size(pm)
	}
	return 0
}

