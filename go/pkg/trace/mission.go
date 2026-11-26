// -----------------------------------------------------------------------------
// ESSENTIAL PROCESS:
// Cross-service and cross-brain mission trace correlation (X-Bastien-Mission-ID).
// Extracts, propagates, and binds mission_id across HTTP requests, NATS headers,
// Go context.Context, and universal-logger structured metadata with zero per-service
// boilerplate.
//
// DATA FLOW:
// Inbound HTTP / NATS Header / Env -> Context & Logger.AddMetadata("mission_id") -> Outbound Headers
//
// KEY PARAMETERS:
// - HeaderMissionID: Canonical wire header ("X-Bastien-Mission-ID").
// - MetadataKey: Canonical universal-logger metadata slot ("mission_id").
// - EnvMissionID: Process environment seed ("X_BASTIEN_MISSION_ID").
// -----------------------------------------------------------------------------

package trace

import (
	"context"
	"net/http"
	"os"
	"strings"

	"github.com/Bastien-Antigravity/microservice-toolbox/go/pkg/logger"
)

// -----------------------------------------------------------------------------

const (
	// HeaderMissionID is the canonical HTTP/NATS/gRPC header carrying mission correlation IDs.
	HeaderMissionID = "X-Bastien-Mission-ID"
	// MetadataKey is the structured logger metadata key persisted to log-server and TimescaleDB.
	MetadataKey = "mission_id"
	// EnvMissionID is the optional cold-start environment seed injected by 08-Squad-Agent.
	EnvMissionID = "X_BASTIEN_MISSION_ID"
	maxMissionIDLen = 128
)

type missionCtxKey struct{}

// -----------------------------------------------------------------------------

// Sanitize validates and trims a raw mission identifier, rejecting control characters or oversized values.
func Sanitize(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || len(trimmed) > maxMissionIDLen {
		return ""
	}
	for i := 0; i < len(trimmed); i++ {
		ch := trimmed[i]
		if ch < 0x21 || ch > 0x7E {
			return ""
		}
	}
	return trimmed
}

// -----------------------------------------------------------------------------

// WithMissionID returns a derived context carrying the sanitized mission ID.
func WithMissionID(ctx context.Context, missionID string) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	clean := Sanitize(missionID)
	if clean == "" {
		return ctx
	}
	return context.WithValue(ctx, missionCtxKey{}, clean)
}

// -----------------------------------------------------------------------------

// FromContext extracts the active mission ID from ctx, falling back to X_BASTIEN_MISSION_ID if set.
func FromContext(ctx context.Context) string {
	if ctx != nil {
		if val, ok := ctx.Value(missionCtxKey{}).(string); ok && val != "" {
			return val
		}
	}
	return Sanitize(os.Getenv(EnvMissionID))
}

// -----------------------------------------------------------------------------

// BindLogger attaches mission_id metadata to a toolbox/universal logger when non-empty.
func BindLogger(l logger.Logger, missionID string) {
	clean := Sanitize(missionID)
	if clean == "" || l == nil {
		return
	}
	l.AddMetadata(MetadataKey, clean)
}

// -----------------------------------------------------------------------------

// BindFromEnv binds X_BASTIEN_MISSION_ID to logger at cold bootstrap when present.
func BindFromEnv(l logger.Logger) string {
	clean := Sanitize(os.Getenv(EnvMissionID))
	if clean != "" && l != nil {
		l.AddMetadata(MetadataKey, clean)
	}
	return clean
}

// -----------------------------------------------------------------------------

// HTTPMiddleware extracts X-Bastien-Mission-ID from inbound HTTP requests, binds context & logger,
// and echoes X-Bastien-Mission-ID on the HTTP response.
func HTTPMiddleware(l logger.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		missionID := Sanitize(r.Header.Get(HeaderMissionID))
		if missionID == "" {
			missionID = Sanitize(os.Getenv(EnvMissionID))
		}
		if missionID != "" {
			w.Header().Set(HeaderMissionID, missionID)
			BindLogger(l, missionID)
			r = r.WithContext(WithMissionID(r.Context(), missionID))
		}
		next.ServeHTTP(w, r)
	})
}

// -----------------------------------------------------------------------------

// InjectHTTPHeader propagates the active mission ID from ctx onto an outbound http.Request.
func InjectHTTPHeader(ctx context.Context, req *http.Request) {
	if req == nil {
		return
	}
	if missionID := FromContext(ctx); missionID != "" {
		req.Header.Set(HeaderMissionID, missionID)
	}
}

// -----------------------------------------------------------------------------

// InjectMapHeaders writes X-Bastien-Mission-ID into a generic string header map (e.g. NATS/gRPC metadata).
func InjectMapHeaders(ctx context.Context, headers map[string]string) {
	if headers == nil {
		return
	}
	if missionID := FromContext(ctx); missionID != "" {
		headers[HeaderMissionID] = missionID
	}
}

// -----------------------------------------------------------------------------

// ExtractMapHeaders reads X-Bastien-Mission-ID (case-insensitively) from a generic header map.
func ExtractMapHeaders(headers map[string]string) string {
	if len(headers) == 0 {
		return ""
	}
	if v, ok := headers[HeaderMissionID]; ok {
		return Sanitize(v)
	}
	for k, v := range headers {
		if strings.EqualFold(k, HeaderMissionID) {
			return Sanitize(v)
		}
	}
	return ""
}
