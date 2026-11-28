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

from dataclasses import dataclass as dcDataclass, field as dcField
from typing import List as typeList, Optional as typeOptional

# -----------------------------------------------------------------------------------------------
# ### JETSTREAM CONFIGURATION ###
# -----------------------------------------------------------------------------------------------

@dcDataclass
class JetStreamConfig:
    """
    Configuration parameters for NATS JetStream persistence and consumer policies.
    """
    enabled: bool = False
    stream_name: str = ""
    subjects: typeList[str] = dcField(default_factory=list)
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

@dcDataclass
class NatsConfig:
    """
    Configuration parameters for core NATS client connections and reconnect policies.
    """
    servers: typeList[str] = dcField(default_factory=list)
    subject: str = ""
    cluster_id: str = ""
    client_id: str = ""
    connect_timeout: float = 2.0  # seconds
    reconnect_wait: float = 2.0  # seconds
    max_reconnects: int = 60
    flush_timeout: float = 10.0  # seconds
    subject_prefix: str = ""
    jetstream: typeOptional[JetStreamConfig] = None
    tls: typeOptional["TLSConfig"] = None

# -----------------------------------------------------------------------------------------------
# ### TLS CONFIGURATION ###
# -----------------------------------------------------------------------------------------------

@dcDataclass
class TLSConfig:
    """
    Configuration parameters for NATS TLS wire encryption and mutual authentication.
    """
    enabled: bool = False
    cert_file: str = ""
    key_file: str = ""
    ca_file: str = ""
    verify_client: bool = False
    insecure_skip_verify: bool = False
