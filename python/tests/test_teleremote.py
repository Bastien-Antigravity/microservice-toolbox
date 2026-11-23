#!/usr/bin/env python
# coding:utf-8

import asyncio
import json
import os
import subprocess
from unittest.mock import Mock

import grpc
import pytest
import yaml

from microservice_toolbox.config import LocalTLSConfig, load_config
from microservice_toolbox.network import (
    build_client_ssl_credentials,
    create_aio_channel,
    is_local_address,
    normalize_tls_mode,
    should_use_client_tls,
)
from microservice_toolbox.teleremote.client import Action, TeleClient
from microservice_toolbox.teleremote.grpc_client import teleremote_pb2, teleremote_pb2_grpc


def test_action_and_menu_generation():
    """Verify recursive menu serialization and omitempty parity."""
    client = TeleClient("TestApp", "127.0.0.1", 50051)

    # 1. Leaf command
    h1 = Mock()
    a1 = Action(label="Command 1", callback=h1)

    # 2. Submenu
    h2 = Mock()
    sub_a = Action(label="Sub Command", callback=h2, input_prompt="Enter text:")
    a2 = Action(label="Menu 1", sub_menu=[sub_a])

    client.add_action(a1)
    client.add_action(a2)

    # Check handler registration
    assert "Command 1" in client._handlers
    assert "Sub Command" in client._handlers
    assert "Menu 1" not in client._handlers  # Menu has no callback

    menu_json = client.generate_menu_json()
    menu = json.loads(menu_json)

    # Output structure check
    assert len(menu) == 2
    # Check leaf
    btn1 = menu[0]["buttons"][0]
    assert btn1["label"] == "Command 1"
    assert btn1["cmd_type"] == 99
    assert btn1["payload"] == "Command 1"
    assert "input_prompt" not in btn1
    assert "menu" not in btn1

    # Check submenu
    btn2 = menu[1]["buttons"][0]
    assert btn2["label"] == "Menu 1"
    assert "cmd_type" not in btn2
    assert "payload" not in btn2
    assert "input_prompt" not in btn2
    assert "menu" in btn2

    sub_btn = btn2["menu"][0]["buttons"][0]
    assert sub_btn["label"] == "Sub Command"
    assert sub_btn["input_prompt"] == "Enter text:"
    assert sub_btn["cmd_type"] == 99
    assert sub_btn["payload"] == "Sub Command"


def test_teleclient_integration():
    """End-to-end integration test with a mock gRPC server using asyncio.run."""

    class MockTeleRemoteService(teleremote_pb2_grpc.TeleRemoteServiceServicer):
        def __init__(self):
            self.registrations = []
            self.telemetries = []
            self.commands_to_send = asyncio.Queue()
            self.done = asyncio.Event()

        async def Connect(self, request_iterator, _context):
            async def read_requests():
                try:
                    async for msg in request_iterator:
                        if msg.HasField("registration"):
                            self.registrations.append(msg)
                        elif msg.HasField("telemetry"):
                            self.telemetries.append(msg.telemetry)
                except Exception:
                    pass
                finally:
                    self.done.set()

            task = asyncio.create_task(read_requests())

            try:
                while not self.done.is_set():
                    try:
                        cmd = await asyncio.wait_for(self.commands_to_send.get(), timeout=0.1)
                        if cmd is None:
                            break
                        yield cmd
                        self.commands_to_send.task_done()
                    except asyncio.TimeoutError:
                        continue
            except asyncio.CancelledError:
                pass
            finally:
                task.cancel()

    async def run_test():
        # Find an open port
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()

        # Start mock gRPC server
        server = grpc.aio.server()
        service = MockTeleRemoteService()
        teleremote_pb2_grpc.add_TeleRemoteServiceServicer_to_server(service, server)
        server.add_insecure_port(f"127.0.0.1:{port}")
        await server.start()

        # Set up client callbacks
        cmd1_called = asyncio.Event()
        cmd2_called = asyncio.Event()
        received_input = ""

        async def handle_cmd1(input_str):
            nonlocal received_input
            received_input = input_str
            cmd1_called.set()

        def handle_cmd2(input_str):
            cmd2_called.set()

        client = TeleClient("IntegrationTestApp", "127.0.0.1", port)
        client.add_action(Action("Cmd1", callback=handle_cmd1))
        client.add_action(Action("Cmd2", callback=handle_cmd2))

        # Start client
        await client.start()

        # Wait for registration to reach the server
        for _ in range(30):
            if len(service.registrations) > 0:
                break
            await asyncio.sleep(0.1)

        assert len(service.registrations) == 1
        reg = service.registrations[0]
        assert reg.component_name == "IntegrationTestApp"
        assert reg.host == "127.0.0.1"
        assert reg.port == port
        menu_data = json.loads(reg.registration.menu_json)
        assert menu_data[0]["buttons"][0]["label"] == "Cmd1"

        # Send a telemetry message from client to server
        await client.send_telemetry("Hello Telegram")
        for _ in range(30):
            if len(service.telemetries) > 0:
                break
            await asyncio.sleep(0.1)

        assert service.telemetries == ["Hello Telegram"]

        # Send a command from server to client
        cmd_msg = teleremote_pb2.BotCommand(
            command_type=teleremote_pb2.BotCommand.CUSTOM_COMMAND,
            custom_payload="Cmd1",
            input="some input text"
        )
        await service.commands_to_send.put(cmd_msg)

        # Wait for handler execution
        await asyncio.wait_for(cmd1_called.wait(), timeout=3.0)
        assert received_input == "some input text"

        # Send another command
        cmd_msg_2 = teleremote_pb2.BotCommand(
            command_type=teleremote_pb2.BotCommand.CUSTOM_COMMAND,
            custom_payload="Cmd2",
            input=""
        )
        await service.commands_to_send.put(cmd_msg_2)
        await asyncio.wait_for(cmd2_called.wait(), timeout=3.0)

        # Stop client and server
        await client.close()
        await server.stop(grace=0.1)

    asyncio.run(run_test())


# ---- Network TLS Policy & Credentials ----

def test_normalize_tls_mode():
    assert normalize_tls_mode("") == "auto"
    assert normalize_tls_mode("   ") == "auto"
    assert normalize_tls_mode("AUTO") == "auto"
    assert normalize_tls_mode(" Strict ") == "strict"
    assert normalize_tls_mode("REMOTE_ONLY") == "remote_only"
    assert normalize_tls_mode("disabled") == "disabled"


def test_is_local_address():
    assert is_local_address("localhost") is True
    assert is_local_address("LOCALHOST") is True
    assert is_local_address("127.0.0.1") is True
    assert is_local_address("127.0.0.2") is True
    assert is_local_address("::1") is True
    assert is_local_address("[::1]") is True
    assert is_local_address("10.0.0.5") is False
    assert is_local_address("example.internal") is False
    assert is_local_address("") is False


def test_should_use_client_tls():
    # disabled -> always False
    assert should_use_client_tls("10.0.0.5:1863", True, "disabled") is False
    assert should_use_client_tls("127.0.0.1:1863", True, "disabled") is False

    # strict / required -> always True
    assert should_use_client_tls("127.0.0.1:1863", False, "strict") is True
    assert should_use_client_tls("localhost:1863", False, "required") is True
    assert should_use_client_tls("[::1]:1863", False, "strict") is True

    # auto / local_plaintext -> TLS only on remote when tls_enabled=True
    assert should_use_client_tls("10.0.0.5:1863", False, "auto") is False
    assert should_use_client_tls("127.0.0.1:1863", True, "auto") is False
    assert should_use_client_tls("localhost:1863", True, "local_plaintext") is False
    assert should_use_client_tls("[::1]:1863", True, "") is False
    assert should_use_client_tls("10.0.0.5:1863", True, "auto") is True
    assert should_use_client_tls("[2001:db8::1]:1863", True, "auto") is True

    # remote_only -> TLS on remote even when tls_enabled=False, plaintext on local
    assert should_use_client_tls("127.0.0.1:1863", False, "remote_only") is False
    assert should_use_client_tls("10.0.0.5:1863", False, "remote_only") is True


def _resolve_config_tool_path() -> str:
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "distributed-config",
            "bin",
            "config-tool",
        )
    )


def test_build_client_ssl_credentials_and_create_aio_channel(tmp_path, monkeypatch):
    config_tool = _resolve_config_tool_path()
    subprocess.run(
        [config_tool, "tlsgen", "--dir", str(tmp_path), "--ca", "--service", "test-client"],
        check=True,
        capture_output=True,
        text=True,
    )
    ca_file = str(tmp_path / "ca.crt")
    cert_file = str(tmp_path / "test-client.crt")
    key_file = str(tmp_path / "test-client.key")

    # 1. Valid mTLS credentials
    mtls_cfg = LocalTLSConfig(cert_file=cert_file, key_file=key_file, ca_file=ca_file)
    mtls_creds = build_client_ssl_credentials(mtls_cfg)
    assert isinstance(mtls_creds, grpc.ChannelCredentials)

    # 2. Valid CA-only TLS credentials
    ca_only_cfg = LocalTLSConfig(ca_file=ca_file)
    ca_creds = build_client_ssl_credentials(ca_only_cfg)
    assert isinstance(ca_creds, grpc.ChannelCredentials)

    # 3. Missing ca_file -> fail fast
    with pytest.raises(ValueError, match="ca_file"):
        build_client_ssl_credentials(LocalTLSConfig())

    # 4. Non-existent ca_file -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        build_client_ssl_credentials(LocalTLSConfig(ca_file=str(tmp_path / "missing-ca.crt")))

    # 5. Half-configured cert/key -> fail fast
    with pytest.raises(ValueError, match="both cert_file and key_file"):
        build_client_ssl_credentials(LocalTLSConfig(ca_file=ca_file, cert_file=cert_file))
    with pytest.raises(ValueError, match="both cert_file and key_file"):
        build_client_ssl_credentials(LocalTLSConfig(ca_file=ca_file, key_file=key_file))

    # 6. create_aio_channel selection: local plaintext vs remote TLS vs explicit credentials
    calls = []

    def fake_insecure(target, *args, **kwargs):
        calls.append(("insecure", target))
        return "INSECURE_CHANNEL"

    def fake_secure(target, creds, *args, **kwargs):
        calls.append(("secure", target, creds))
        return "SECURE_CHANNEL"

    monkeypatch.setattr(grpc.aio, "insecure_channel", fake_insecure)
    monkeypatch.setattr(grpc.aio, "secure_channel", fake_secure)

    ch_local = create_aio_channel("127.0.0.1:1863", "127.0.0.1", mtls_cfg, True, "auto")
    assert ch_local == "INSECURE_CHANNEL"

    ch_remote = create_aio_channel("10.0.0.5:1863", "10.0.0.5", mtls_cfg, True, "auto")
    assert ch_remote == "SECURE_CHANNEL"

    explicit = grpc.ssl_channel_credentials()
    ch_explicit = create_aio_channel("127.0.0.1:1863", "127.0.0.1", LocalTLSConfig(), False, "disabled", explicit)
    assert ch_explicit == "SECURE_CHANNEL"

    assert calls[0] == ("insecure", "127.0.0.1:1863")
    assert calls[1][0] == "secure" and calls[1][1] == "10.0.0.5:1863"
    assert isinstance(calls[1][2], grpc.ChannelCredentials)
    assert calls[2] == ("secure", "127.0.0.1:1863", explicit)


# ---- TeleClient Priority, Ordering, Config & Auth Metadata ----

def test_generate_menu_json_priority_and_order():
    client = TeleClient("OrderedApp", "127.0.0.1", 50051)
    cb = Mock()
    sub = Action(label="Sub1", order=3, callback=cb)
    a1 = Action(label="First", order=1, callback=cb)
    a2 = Action(label="Unordered", callback=cb)
    a3 = Action(label="Group", order=2, sub_menu=[sub])

    client.add_action(a1)
    client.add_action(a2)
    client.add_action(a3)

    # Without priority (> 0): bare JSON array for backwards compatibility
    raw = json.loads(client.generate_menu_json())
    assert isinstance(raw, list)
    assert raw[0]["order"] == 1
    assert raw[0]["buttons"][0]["order"] == 1
    assert "order" not in raw[1]
    assert "order" not in raw[1]["buttons"][0]
    assert raw[2]["order"] == 2
    assert raw[2]["buttons"][0]["order"] == 2
    assert raw[2]["buttons"][0]["menu"][0]["order"] == 3
    assert raw[2]["buttons"][0]["menu"][0]["buttons"][0]["order"] == 3

    # With priority > 0: envelope with {"priority": ..., "rows": [...]}
    ret = client.set_priority(10)
    assert ret is client
    enveloped = json.loads(client.generate_menu_json())
    assert isinstance(enveloped, dict)
    assert enveloped["priority"] == 10
    assert enveloped["rows"] == raw

    # Resetting priority <= 0 reverts to bare array
    client.set_priority(0)
    assert isinstance(json.loads(client.generate_menu_json()), list)


def test_configure_from_app_config_and_live_reload(tmp_path):
    client = TeleClient("ConfigApp", "10.0.0.5", 1863)

    with pytest.raises(ValueError, match="non-nil AppConfig"):
        client.configure_from_app_config(None, "config-app")

    config_file = tmp_path / "tele_cfg.yaml"
    data = {
        "capabilities": {
            "tele_remote": {
                "tls_enabled": "true",
                "tls_mode": "remote_only",
                "auth_token": "ENC(secret-cipher)",
            }
        },
        "local": {
            "config_app": {
                "tls": {
                    "cert_file": "/etc/tls/app.crt",
                    "key_file": "/etc/tls/app.key",
                    "ca_file": "/etc/tls/ca.crt",
                }
            }
        },
    }
    with open(config_file, "w") as f:
        yaml.dump(data, f)

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("tele_cfg", input_args=[])
        live_callbacks = []
        ac.on_live_conf_update = lambda cb: live_callbacks.append(cb)
        ac.decrypt_secret = lambda s: "decrypted-token" if s == "ENC(secret-cipher)" else s

        ret = client.configure_from_app_config(ac, "config-app")
        assert ret is client
        assert client._tls_enabled is True
        assert client._tls_mode == "remote_only"
        assert client._auth_token == "decrypted-token"
        assert client._local_tls.cert_file == "/etc/tls/app.crt"
        assert client._local_tls.ca_file == "/etc/tls/ca.crt"
        assert len(live_callbacks) == 1

        # Simulate dynamic live-config update
        ac.data["capabilities"]["tele_remote"]["tls_enabled"] = False
        ac.data["capabilities"]["tele_remote"]["tls_mode"] = "strict"
        ac.data["capabilities"]["tele_remote"]["auth_token"] = "rotated-plain-token"
        ac.data["local"]["config_app"]["tls"]["ca_file"] = "/etc/tls/ca-v2.crt"
        live_callbacks[0]({})

        assert client._tls_enabled is False
        assert client._tls_mode == "strict"
        assert client._auth_token == "rotated-plain-token"
        assert client._local_tls.ca_file == "/etc/tls/ca-v2.crt"

        # Invalid runtime reload must log warning and keep previous valid state without crashing
        ac.data["capabilities"]["tele_remote"]["tls_enabled"] = "not-a-bool"
        live_callbacks[0]({})
        assert client._tls_mode == "strict"
        assert client._auth_token == "rotated-plain-token"

        # Invalid initial tls_enabled fails fast on cold path
        with pytest.raises(ValueError, match="invalid tele_remote.tls_enabled"):
            client.configure_from_app_config(ac, "config-app")
    finally:
        os.chdir(old_cwd)


def test_teleclient_x_tele_auth_metadata_and_tls_channel(monkeypatch):
    async def run_test():
        connect_calls = []
        channel_calls = []

        class FakeStream:
            def __init__(self):
                self.writes = []
                self.cancelled = False

            async def write(self, msg):
                self.writes.append(msg)

            def cancel(self):
                self.cancelled = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                await asyncio.sleep(0.05)
                raise StopAsyncIteration

        class FakeChannel:
            async def close(self):
                pass

        class FakeStub:
            def __init__(self, _channel):
                pass

            def Connect(self, **kwargs):
                connect_calls.append(kwargs)
                return FakeStream()

        def fake_create_aio_channel(**kwargs):
            channel_calls.append(kwargs)
            return FakeChannel()

        import microservice_toolbox.teleremote.client as client_mod

        monkeypatch.setattr(client_mod, "create_aio_channel", fake_create_aio_channel)
        monkeypatch.setattr(teleremote_pb2_grpc, "TeleRemoteServiceStub", FakeStub)

        # 1. With auth_token + TLS policy
        tls_cfg = LocalTLSConfig(ca_file="/tmp/ca.crt")
        client = (
            TeleClient("AuthApp", "10.0.0.9", 1863)
            .set_auth_token("  secret-123  ")
            .set_local_tls(tls_cfg)
            .set_tls_policy(True, "strict")
        )
        await client.start()
        for _ in range(20):
            if connect_calls:
                break
            await asyncio.sleep(0.02)
        await client.close()

        assert len(channel_calls) >= 1
        assert channel_calls[0]["target_ip"] == "10.0.0.9"
        assert channel_calls[0]["tls_enabled"] is True
        assert channel_calls[0]["tls_mode"] == "strict"
        assert channel_calls[0]["local_tls"].ca_file == "/tmp/ca.crt"
        assert connect_calls[0] == {"metadata": [("x-tele-auth", "secret-123")]}

        # 2. Without auth_token
        connect_calls.clear()
        client2 = TeleClient("PlainApp", "127.0.0.1", 1863)
        await client2.start()
        for _ in range(20):
            if connect_calls:
                break
            await asyncio.sleep(0.02)
        await client2.close()
        assert connect_calls[0] == {}

    asyncio.run(run_test())


def test_teleclient_e2e_mtls_and_auth_metadata(tmp_path):
    """End-to-end real X.509 mTLS handshake + x-tele-auth + OpenMFE priority/order test."""
    config_tool = _resolve_config_tool_path()
    subprocess.run(
        [config_tool, "tlsgen", "--dir", str(tmp_path), "--ca"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            config_tool,
            "tlsgen",
            "--dir",
            str(tmp_path),
            "--service",
            "tele_remote",
            "--hosts",
            "127.0.0.1,localhost",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            config_tool,
            "tlsgen",
            "--dir",
            str(tmp_path),
            "--service",
            "py_client",
            "--hosts",
            "127.0.0.1,localhost",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    ca_pem = (tmp_path / "ca.crt").read_bytes()
    srv_cert = (tmp_path / "tele_remote.crt").read_bytes()
    srv_key = (tmp_path / "tele_remote.key").read_bytes()

    class SecureMockTeleRemoteService(teleremote_pb2_grpc.TeleRemoteServiceServicer):
        def __init__(self):
            self.received_auth = None
            self.registrations = []

        async def Connect(self, request_iterator, context):
            md = dict(context.invocation_metadata())
            self.received_auth = md.get("x-tele-auth")
            if self.received_auth != "py-mtls-secret":
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "invalid x-tele-auth")
            async for msg in request_iterator:
                if msg.HasField("registration"):
                    self.registrations.append(msg)
                    break
            if False:
                yield teleremote_pb2.BotCommand()

    async def run_test():
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        server = grpc.aio.server()
        service = SecureMockTeleRemoteService()
        teleremote_pb2_grpc.add_TeleRemoteServiceServicer_to_server(service, server)
        server_creds = grpc.ssl_server_credentials(
            [(srv_key, srv_cert)],
            root_certificates=ca_pem,
            require_client_auth=True,
        )
        server.add_secure_port(f"127.0.0.1:{port}", server_creds)
        await server.start()

        client = (
            TeleClient("PySecureApp", "127.0.0.1", port)
            .set_priority(7)
            .set_auth_token("  py-mtls-secret  ")
            .set_tls_policy(True, "strict")
            .set_local_tls(
                LocalTLSConfig(
                    ca_file=str(tmp_path / "ca.crt"),
                    cert_file=str(tmp_path / "py_client.crt"),
                    key_file=str(tmp_path / "py_client.key"),
                    verify_client=True,
                )
            )
        )
        client.add_action(Action(label="PingSecure", order=4, callback=Mock()))

        await client.start()
        for _ in range(30):
            if service.registrations:
                break
            await asyncio.sleep(0.1)

        await client.close()
        await server.stop(grace=0.1)

        assert service.received_auth == "py-mtls-secret"
        assert len(service.registrations) == 1
        menu = json.loads(service.registrations[0].registration.menu_json)
        assert menu["priority"] == 7
        assert menu["rows"][0]["order"] == 4
        assert menu["rows"][0]["buttons"][0]["label"] == "PingSecure"
        assert menu["rows"][0]["buttons"][0]["order"] == 4

    asyncio.run(run_test())
