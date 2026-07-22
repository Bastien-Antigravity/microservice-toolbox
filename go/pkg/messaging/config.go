package messaging

import "time"

// NatsConfig holds configuration for the NATS client connection.
type NatsConfig struct {
	Servers   []string `yaml:"servers" json:"servers"`
	Subject   string   `yaml:"subject" json:"subject"`
	ClusterID string   `yaml:"cluster_id" json:"cluster_id"`
	ClientID  string   `yaml:"client_id" json:"client_id"`

	// Connection tuning
	ConnectTimeout time.Duration `yaml:"connect_timeout" json:"connect_timeout"`
	ReconnectWait  time.Duration `yaml:"reconnect_wait" json:"reconnect_wait"`
	MaxReconnects  int           `yaml:"max_reconnects" json:"max_reconnects"`
	FlushTimeout   time.Duration `yaml:"flush_timeout" json:"flush_timeout"`

	SubjectPrefix string `yaml:"subject_prefix" json:"subject_prefix"`

	// JetStream Configuration
	JetStream *JetStreamConfig `yaml:"jetstream" json:"jetstream"`
}

// JetStreamConfig holds specific settings for stream creation and publishing.
type JetStreamConfig struct {
	Enabled    bool   `yaml:"enabled" json:"enabled"`
	StreamName string `yaml:"stream_name" json:"stream_name"`

	// Stream configuration
	Subjects        []string      `yaml:"subjects" json:"subjects"`
	RetentionPolicy string        `yaml:"retention" json:"retention"`
	Storage         string        `yaml:"storage" json:"storage"`
	Replicas        int           `yaml:"replicas" json:"replicas"`
	MaxAge          time.Duration `yaml:"max_age" json:"max_age"`
	MaxMsgs         int64         `yaml:"max_msgs" json:"max_msgs"`
	MaxBytes        int64         `yaml:"max_bytes" json:"max_bytes"`
	MaxMsgSize      int32         `yaml:"max_msg_size" json:"max_msg_size"`

	// Consumer configuration
	DurableConsumer string        `yaml:"durable_consumer" json:"durable_consumer"`
	AckWait         time.Duration `yaml:"ack_wait" json:"ack_wait"`
}
