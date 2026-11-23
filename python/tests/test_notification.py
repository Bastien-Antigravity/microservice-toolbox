#!/usr/bin/env python
# coding:utf-8

"""
# -----------------------------------------------------------------------------
# ESSENTIAL PROCESS:
# Unit and integration tests for Python NotificationClient facade in microservice-toolbox.
#
# DATA FLOW:
# Test -> NotificationClient -> Mock gRPC Server -> Assertion Verification
# -----------------------------------------------------------------------------
"""

import asyncio
import concurrent.futures
import threading
from typing import Optional

import grpc
import grpc.aio
import pytest

from microservice_toolbox.notification import (
    NotificationClient,
)
from microservice_toolbox.notification.grpc_client import (
    notif_service_pb2,
    notif_service_pb2_grpc,
)


class MockNotifService(notif_service_pb2_grpc.NotifServiceServicer):
    def __init__(self, success: bool = True):
        self.success = success
        self.received_req: Optional[notif_service_pb2.NotifRequest] = None

    def SendNotification(self, request, _context):
        self.received_req = request
        return notif_service_pb2.NotifResponse(success=self.success)


def start_mock_server(success: bool = True):
    server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=4))
    service = MockNotifService(success=success)
    notif_service_pb2_grpc.add_NotifServiceServicer_to_server(service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    addr = f"127.0.0.1:{port}"

    def cleanup():
        server.stop(grace=0)

    return service, addr, cleanup


def test_notification_send_success():
    async def run_test():
        service, addr, cleanup = start_mock_server(success=True)
        try:
            client = NotificationClient(addr)
            await client.send("Hello from Python L2 service", "telegram", "discord")

            assert service.received_req is not None
            assert service.received_req.message == "Hello from Python L2 service"
            assert list(service.received_req.tags) == ["telegram", "discord"]
            assert service.received_req.level == ""
            await client.close()
        finally:
            cleanup()

    asyncio.run(run_test())


def test_notification_send_alert():
    async def run_test():
        service, addr, cleanup = start_mock_server(success=True)
        try:
            client = NotificationClient(addr)
            await client.send_alert("TRADE", "Filled order #1092: Sold 2.5 BTC", "trade_channel")

            assert service.received_req is not None
            assert service.received_req.message == "Filled order #1092: Sold 2.5 BTC"
            assert service.received_req.level == "TRADE"
            assert list(service.received_req.tags) == ["trade_channel"]
            await client.close()
        finally:
            cleanup()

    asyncio.run(run_test())


def test_notification_send_with_attachment():
    async def run_test():
        service, addr, cleanup = start_mock_server(success=True)
        try:
            client = NotificationClient(addr)
            await client.send_with_attachment("REPORT", "Daily PnL", "/tmp/report.pdf", "finance")

            assert service.received_req is not None
            assert service.received_req.message == "Daily PnL"
            assert service.received_req.level == "REPORT"
            assert service.received_req.attachment == "/tmp/report.pdf"
            assert list(service.received_req.tags) == ["finance"]
            await client.close()
        finally:
            cleanup()

    asyncio.run(run_test())


def test_notification_server_rejection():
    async def run_test():
        _, addr, cleanup = start_mock_server(success=False)
        try:
            client = NotificationClient(addr)
            with pytest.raises(RuntimeError, match="notification server rejected message"):
                await client.send("Test message")
            await client.close()
        finally:
            cleanup()

    asyncio.run(run_test())


def test_notification_closed_client():
    async def run_test():
        client = NotificationClient("127.0.0.1:9999")
        await client.close()
        with pytest.raises(RuntimeError, match="closed"):
            await client.send("Should fail")

    asyncio.run(run_test())


def test_notification_send_sync():
    service, addr, cleanup = start_mock_server(success=True)
    try:
        client = NotificationClient(addr)
        client.send_sync("Sync test message", "telegram")

        assert service.received_req is not None
        assert service.received_req.message == "Sync test message"
        assert list(service.received_req.tags) == ["telegram"]
        client.close_sync()
    finally:
        cleanup()


def test_notification_nil_app_config():
    with pytest.raises(ValueError, match="app_config cannot be None"):
        NotificationClient.from_config(None)


def test_notification_from_config_resolution():
    class DummyAppConfig:
        def get_grpc_listen_addr(self, cap: str) -> str:
            if cap == "notif_server":
                return "127.0.0.1:1027"
            return ""

    client = NotificationClient.from_config(DummyAppConfig())
    assert client.target_addr == "127.0.0.1:1027"


def test_notification_missing_capability_fails_fast():
    class EmptyAppConfig:
        def get_grpc_listen_addr(self, cap: str) -> str:
            raise KeyError(f"capability {cap} not found")

    with pytest.raises(ValueError, match="failed to resolve notif_server gRPC address"):
        NotificationClient.from_config(EmptyAppConfig())


def test_notification_logs_strictly_on_caller_thread():
    """Verify libunilog/logger calls never execute inside the libnotif worker thread pool."""
    caller_tid = threading.get_ident()
    logged_tids = []

    class ThreadRecordingLogger:
        def debug(self, msg, *args, **kwargs):
            logged_tids.append(("debug", threading.get_ident()))

        def info(self, msg, *args, **kwargs):
            logged_tids.append(("info", threading.get_ident()))

        def warning(self, msg, *args, **kwargs):
            logged_tids.append(("warning", threading.get_ident()))

        def error(self, msg, *args, **kwargs):
            logged_tids.append(("error", threading.get_ident()))

        def critical(self, msg, *args, **kwargs):
            logged_tids.append(("critical", threading.get_ident()))

    async def run_test():
        _, ok_addr, cleanup_ok = start_mock_server(success=True)
        _, fail_addr, cleanup_fail = start_mock_server(success=False)
        try:
            ok_client = NotificationClient(ok_addr, logger=ThreadRecordingLogger())
            await ok_client.send("ok message", "telegram")
            await ok_client.close()

            fail_client = NotificationClient(fail_addr, logger=ThreadRecordingLogger())
            with pytest.raises(RuntimeError, match="SendNotification failed"):
                await fail_client.send("fail message", "telegram")
            await fail_client.close()
        finally:
            cleanup_ok()
            cleanup_fail()

    asyncio.run(run_test())
    assert ("debug", caller_tid) in logged_tids
    assert ("warning", caller_tid) in logged_tids
    assert all(tid == caller_tid for _, tid in logged_tids)
