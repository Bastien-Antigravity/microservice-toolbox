#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for Python WireTap thread-safe telemetry store, sampling, and snapshot merge.
"""

from microservice_toolbox import wiretap


def test_wiretap_basic_sampling_and_merge():
    wiretap.reset()
    assert wiretap.is_enabled() is True

    wiretap.set_local_service("py-svc")
    assert wiretap.get_local_service() == "py_svc"
    wiretap.set_web_hub_url("http://127.0.0.1:5000/")
    assert wiretap.get_web_hub_url() == "http://127.0.0.1:5000"

    wiretap.record_event("py-svc", "nats-broker", "NATS", "raw", "events.tick", bytes_count=128)
    wiretap.record_event("py-svc", "nats-broker", "NATS", "NATS JetStream", "events.tick", bytes_count=256)
    snap = wiretap.snapshot()
    assert len(snap) == 1
    assert snap[0]["target"] == "nats"
    assert snap[0]["framing"] == "NATS JetStream"
    assert "last_payload" not in snap[0]["channels"][0]

    assert wiretap.should_sample(0) is True
    hits = sum(1 for _ in range(16) if wiretap.should_sample(0x3))
    assert hits == 4

    wiretap.merge_remote_snapshot([{
        "source": "ext-client",
        "target": "rag_mcp",
        "protocol": "SSE",
        "framing": "FastMCP",
        "active_conns": 1,
        "total_frames": 3,
        "total_bytes": 100,
        "total_errors": 0,
        "is_external": True,
        "channels": [{"channel": "mcp:tool:ping", "category": "mcp_tool", "direction": "inbound", "frames": 3, "bytes": 100}],
    }])
    assert len(wiretap.snapshot()) == 2
    wiretap.reset()

