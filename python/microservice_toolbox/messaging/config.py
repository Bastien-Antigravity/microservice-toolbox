#!/usr/bin/env python
# coding:utf-8

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class JetStreamConfig:
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

@dataclass
class NatsConfig:
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
