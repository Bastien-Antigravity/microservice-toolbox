package trace

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
)

type captureMetaLogger struct {
	mu   sync.Mutex
	meta map[string]string
}

func (c *captureMetaLogger) Debug(string, ...any)    {}
func (c *captureMetaLogger) Info(string, ...any)     {}
func (c *captureMetaLogger) Warning(string, ...any)  {}
func (c *captureMetaLogger) Error(string, ...any)    {}
func (c *captureMetaLogger) Critical(string, ...any) {}
func (c *captureMetaLogger) Logon(string, ...any)    {}
func (c *captureMetaLogger) Logout(string, ...any)   {}
func (c *captureMetaLogger) Trade(string, ...any)    {}
func (c *captureMetaLogger) Schedule(string, ...any) {}
func (c *captureMetaLogger) Report(string, ...any)   {}
func (c *captureMetaLogger) Stream(string, ...any)   {}
func (c *captureMetaLogger) AddMetadata(k, v string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.meta == nil {
		c.meta = make(map[string]string)
	}
	c.meta[k] = v
}

func TestMissionIDMiddlewareAndPropagation(t *testing.T) {
	log := &captureMetaLogger{}
	var observedCtxID string

	handler := HTTPMiddleware(log, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		observedCtxID = FromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/status", nil)
	req.Header.Set(HeaderMissionID, "mission-alpha-001")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if observedCtxID != "mission-alpha-001" {
		t.Fatalf("expected context mission_id 'mission-alpha-001', got %q", observedCtxID)
	}
	if got := rec.Header().Get(HeaderMissionID); got != "mission-alpha-001" {
		t.Fatalf("expected response header 'mission-alpha-001', got %q", got)
	}
	if got := log.meta[MetadataKey]; got != "mission-alpha-001" {
		t.Fatalf("expected logger metadata mission_id 'mission-alpha-001', got %q", got)
	}

	ctx := WithMissionID(context.Background(), "mission-beta-002")
	outReq := httptest.NewRequest(http.MethodPost, "/api/v1/exec", nil)
	InjectHTTPHeader(ctx, outReq)
	if got := outReq.Header.Get(HeaderMissionID); got != "mission-beta-002" {
		t.Fatalf("expected outbound HTTP header 'mission-beta-002', got %q", got)
	}

	natsHeaders := make(map[string]string)
	InjectMapHeaders(ctx, natsHeaders)
	if got := ExtractMapHeaders(natsHeaders); got != "mission-beta-002" {
		t.Fatalf("expected extracted map header 'mission-beta-002', got %q", got)
	}
}

func TestMissionIDSanitizeRejectsMalformedInput(t *testing.T) {
	if got := Sanitize("bad\r\nheader-injection"); got != "" {
		t.Fatalf("expected control chars rejected, got %q", got)
	}
	if got := Sanitize("has space"); got != "" {
		t.Fatalf("expected whitespace rejected, got %q", got)
	}
}
