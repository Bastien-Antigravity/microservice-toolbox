package wiretap

// =============================================================================
// ESSENTIAL PROCESS:
// Provides a distinct, lock-free atomic switchable NATS telemetry wrapper to
// track real-time NATS broker connections and segregated subject publications
// and subscriptions across the microservice fleet.
//
// DATA FLOW:
// 1. Input: NATS connection lifecycle or Publish/Subscribe calls.
// 2. Logic: Lock-free `IsEnabled()` check. When enabled, records segregated
//    subject telemetry (`nats:subject:<subject>`) and connection state.
// 3. Output: Real-time NATS edge and subject channels in WireTap store.
//
// KEY PARAMETERS:
// - clientID: Microservice NATS client identifier.
// =============================================================================

import (
	"github.com/nats-io/nats.go"
)

// RecordNATSConnect records a live NATS broker connection event if WireTap is enabled.
func RecordNATSConnect(clientID string, brokerURL string) {
	if !IsEnabled() {
		return
	}
	src := NormalizeServiceID(clientID)
	if src == "" || src == "generic_client" {
		src = GetLocalService()
	}
	RecordEventWithConnDelta(
		src,
		"nats",
		"NATS",
		"NATS JetStream ("+brokerURL+")",
		"nats:lifecycle",
		"lifecycle",
		"outbound",
		"connected",
		0,
		0,
		false,
		false,
		1,
	)
}

// RecordNATSDisconnect records a NATS broker disconnect event if WireTap is enabled.
func RecordNATSDisconnect(clientID string, hasErr bool) {
	if !IsEnabled() {
		return
	}
	src := NormalizeServiceID(clientID)
	if src == "" || src == "generic_client" {
		src = GetLocalService()
	}
	RecordEventWithConnDelta(
		src,
		"nats",
		"NATS",
		"NATS JetStream",
		"nats:lifecycle",
		"lifecycle",
		"outbound",
		"disconnected",
		0,
		0,
		hasErr,
		false,
		-1,
	)
}

// PublishNATS wraps nc.Publish with lock-free atomic segregated subject tracking.
func PublishNATS(nc *nats.Conn, subject string, data []byte) error {
	err := nc.Publish(subject, data)
	if IsEnabled() {
		RecordEvent(
			GetLocalService(),
			"nats",
			"NATS",
			"NATS JetStream",
			"nats:pub:"+subject,
			"pubsub:publish",
			"outbound",
			subject,
			len(data),
			0,
			err != nil,
			false,
		)
	}
	return err
}

// SubscribeNATS wraps nc.Subscribe with lock-free atomic segregated subject tracking.
func SubscribeNATS(nc *nats.Conn, subject string, cb nats.MsgHandler) (*nats.Subscription, error) {
	wrappedCB := func(msg *nats.Msg) {
		if IsEnabled() && msg != nil {
			RecordEvent(
				"nats",
				GetLocalService(),
				"NATS",
				"NATS JetStream",
				"nats:sub:"+msg.Subject,
				"pubsub:subscribe",
				"inbound",
				msg.Subject,
				len(msg.Data),
				0,
				false,
				false,
			)
		}
		if cb != nil {
			cb(msg)
		}
	}
	return nc.Subscribe(subject, wrappedCB)
}

