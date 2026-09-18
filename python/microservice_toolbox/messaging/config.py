#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Configuration data structures for NATS Core and JetStream messaging connections.

DATA FLOW:
1. Input: Capability configuration dictionary or application options.
2. Logic: Typed mapping to connection parameters, retention policies, and timeout constraints.
3. Output: Validated NatsConfig and JetStreamConfig instances used by connector.

KEY PARAMETERS:
- servers: List of NATS broker endpoints.
- client_id: Unique client identifier for telemetry and connection tracking.
- jetstream: Optional JetStream stream and consumer configuration.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# -----------------------------------------------------------------------------------------------
# ### JETSTREAM CONFIGURATION ###
# -----------------------------------------------------------------------------------------------

@dataclass
class JetStreamConfig:
    """
    Configuration parameters for NATS JetStream persistence and consumer policies.
    """
    enabled: bool = False
    stream_name: str = ""
    subjects: List[str] = field(default_factory=list)
    retention: str = "limits"
    storage: str = "file"
    replicas: int = 1
    max_age: float = 259200.0  # 72 hours in seconds
    max_msgs: int = -1
    max_bytes: int = -1
    max_msg_size: int = -1
    durable_consumer: str = ""
    ack_wait: float = 30.0  # seconds

# -----------------------------------------------------------------------------------------------
# ### NATS CONFIGURATION ###
# -----------------------------------------------------------------------------------------------

@dataclass
class NatsConfig:
    """
    Configuration parameters for core NATS client connections and reconnect policies.
    """
    servers: List[str] = field(default_factory=list)
    subject: str = ""
    cluster_id: str = ""
    client_id: str = ""
    connect_timeout: float = 2.0  # seconds
    reconnect_wait: float = 2.0  # seconds
    max_reconnects: int = 60
    flush_timeout: float = 10.0  # seconds
    subject_prefix: str = ""
    jetstream: Optional[JetStreamConfig] = None
