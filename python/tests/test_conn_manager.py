import time
from unittest.mock import MagicMock

import pytest

from microservice_toolbox.conn_manager.manager import new_network_manager


def test_network_manager_connect_blocking():
    nm = new_network_manager(max_retries=1, base_delay_ms=10)

    # Mock establish_connection
    mock_conn = MagicMock()
    nm.establish_connection = MagicMock(return_value=mock_conn)

    mc = nm.connect_blocking("127.0.0.1", "8080", "1.2.3.4", "test")

    assert mc.current_conn == mock_conn
    assert nm.establish_connection.called


def test_network_manager_retry_logic():
    nm = new_network_manager(max_retries=2, base_delay_ms=10)

    # Mock establish_connection to fail twice then succeed
    mock_conn = MagicMock()
    nm.establish_connection = MagicMock(side_effect=[Exception("Fail 1"), Exception("Fail 2"), mock_conn])

    # This should succeed on the 3rd attempt (after 2 retries)
    mc = nm.connect_blocking("127.0.0.1", "8080", "1.2.3.4", "test")
    assert mc.current_conn == mock_conn
    assert nm.establish_connection.call_count == 3


def test_network_manager_connect_non_blocking():
    nm = new_network_manager(max_retries=1, base_delay_ms=10)

    # Mock establish_connection with a delay
    mock_conn = MagicMock()

    def slow_connect(*_args, **_kwargs):
        time.sleep(0.1)
        return mock_conn

    nm.establish_connection = MagicMock(side_effect=slow_connect)

    mc = nm.connect_non_blocking("127.0.0.1", "8080", "1.2.3.4", "test")

    # Should return immediately with no connection yet
    assert mc.current_conn is None

    # Wait for background thread
    time.sleep(0.2)
    assert mc.current_conn == mock_conn


def test_managed_connection_write_failure_retry():
    nm = new_network_manager(max_retries=1, base_delay_ms=10)
    mock_conn_1 = MagicMock()
    mock_conn_2 = MagicMock()

    # First connection success, then write failure, then reconnection success
    nm.establish_connection = MagicMock(side_effect=[mock_conn_1, mock_conn_2])
    mock_conn_1.send.side_effect = Exception("Write failed")
    mock_conn_2.send.return_value = 10

    mc = nm.connect_blocking("127.0.0.1", "8080", "1.2.3.4", "test")

    # Writing should trigger reconnection and retry
    bytes_sent = mc.write(b"hello")

    assert bytes_sent == 10
    assert nm.establish_connection.call_count == 2
    assert mock_conn_1.close.called


def test_on_error_unified_hook():
    attempts = []
    errors = []

    def on_error(attempt, err, _source, _msg):
        attempts.append(attempt)
        errors.append(err)

    nm = new_network_manager(max_retries=2, base_delay_ms=10, on_error=on_error)
    nm.establish_connection = MagicMock(side_effect=Exception("Connection failed"))

    with pytest.raises(Exception):
        nm.connect_with_retry("127.0.0.1", "8080", "1.2.3.4", "test")

    assert attempts == [1, 2]
    assert len(errors) == 2
    assert str(errors[0]) == "Connection failed"


def test_strategies_presets():
    from microservice_toolbox.conn_manager.manager import (
        new_critical_strategy,
        new_performance_strategy,
        new_standard_strategy,
    )

    nm_crit = new_critical_strategy()
    assert nm_crit.max_retries == -1
    assert nm_crit.jitter == 0.2

    nm_std = new_standard_strategy()
    assert nm_std.max_retries == 10

    nm_perf = new_performance_strategy()
    assert nm_perf.base_delay == 0.1


def test_unified_connect():
    from microservice_toolbox.conn_manager.manager import ConnectionMode

    nm = new_network_manager(max_retries=1, base_delay_ms=10)
    mock_conn = MagicMock()
    nm.establish_connection = MagicMock(return_value=mock_conn)

    # Test BLOCKING
    mc = nm.connect("127.0.0.1", "8080", "1.2.3.4", "test", ConnectionMode.BLOCKING)
    assert mc.current_conn == mock_conn

    # Test NON_BLOCKING
    nm.establish_connection.reset_mock()
    mc_async = nm.connect("127.0.0.1", "8080", "1.2.3.4", "test", ConnectionMode.NON_BLOCKING)
    time.sleep(0.1)
    assert nm.establish_connection.called
    assert mc_async.current_conn == mock_conn

    # Test INDEFINITE
    error_count = 0

    def on_error(attempt, err, _source, _msg):
        nonlocal error_count
        error_count += 1

    nm_indef = new_network_manager(max_retries=2, base_delay_ms=10)
    nm_indef.on_error = on_error
    nm_indef.establish_connection = MagicMock(side_effect=Exception("Fail"))

    # Indefinite should continue past max_retries
    import threading

    thread = threading.Thread(
        target=nm_indef.connect, args=("127.0.0.1", "8080", "1.2.3.4", "test", ConnectionMode.INDEFINITE), daemon=True
    )
    thread.start()

    time.sleep(0.1)
    assert error_count > 2


def test_managed_connection_reconnect_max_retries():
    from microservice_toolbox.conn_manager.errors import MaxRetriesReachedError

    nm = new_network_manager(max_retries=2, base_delay_ms=10)
    nm.establish_connection = MagicMock(side_effect=Exception("Connection failed"))

    mc = nm.connect_blocking("127.0.0.1", "8080", "1.2.3.4", "test")

    with pytest.raises(MaxRetriesReachedError):
        mc.write(b"hello")

    # First reconnect() inside connect_blocking: i=0 (fail), i=1 (fail), i=2 (raises, caught in connect_blocking)
    # Second reconnect() inside write(): i=0 (fail), i=1 (fail), i=2 (raises)
    # Total calls: 6
    assert nm.establish_connection.call_count == 6


def test_network_manager_connect_capability_resolution():
    mock_ac = MagicMock()
    mock_ac.profile = "prod"
    mock_ac.config.common.public_ip = "198.51.100.1"
    mock_ac.get_listen_addr.return_value = "10.0.0.15:7070"

    from microservice_toolbox.conn_manager.manager import new_network_manager_with_config

    nm = new_network_manager_with_config(mock_ac)

    mock_conn = MagicMock()
    nm.establish_connection = MagicMock(return_value=mock_conn)

    mc = nm.connect_capability("log-server")
    assert mc.current_conn == mock_conn
    assert mc.get_endpoint() == ("10.0.0.15", "7070")
    assert mc.capability == "log-server"
    assert mc.app_config == mock_ac
    nm.establish_connection.assert_called_once_with("10.0.0.15", "7070", "198.51.100.1", "prod")


def test_network_manager_connect_capability_live_config_refresh():
    addresses = ["10.0.0.15:7070", "10.0.0.15:7070", "10.0.0.25:8080"]
    call_idx = 0

    def mock_get_listen_addr(_cap):
        nonlocal call_idx
        addr = addresses[min(call_idx, len(addresses) - 1)]
        call_idx += 1
        return addr

    mock_ac = MagicMock()
    mock_ac.profile = "test"
    mock_ac.config.common.public_ip = "1.2.3.4"
    mock_ac.get_listen_addr = MagicMock(side_effect=mock_get_listen_addr)

    from microservice_toolbox.conn_manager.manager import new_network_manager

    nm = new_network_manager(max_retries=4, base_delay_ms=5, app_config=mock_ac)

    mock_conn = MagicMock()
    dialed = []

    def mock_establish(ip, port, _pub, _prof):
        addr = f"{ip}:{port}"
        dialed.append(addr)
        if addr == "10.0.0.25:8080":
            return mock_conn
        raise Exception(f"down at {addr}")

    nm.establish_connection = MagicMock(side_effect=mock_establish)

    mc = nm.connect_capability("log-server")
    assert mc.current_conn == mock_conn
    assert mc.get_endpoint() == ("10.0.0.25", "8080")
    assert dialed == ["10.0.0.15:7070", "10.0.0.25:8080"]


def test_realworld_dynamic_failover():
    from microservice_toolbox.conn_manager.manager import new_network_manager

    server1_alive = True
    server1_payloads = []
    server2_payloads = []

    class MockSocket:
        def __init__(self, name, payloads):
            self.name = name
            self.payloads = payloads
            self.closed = False

        def send(self, data):
            if self.name == "server1" and not server1_alive:
                raise Exception("Broken pipe: server1 died")
            self.payloads.append(data)
            return len(data)

        def close(self):
            self.closed = True

    s1_sock = MockSocket("server1", server1_payloads)
    s2_sock = MockSocket("server2", server2_payloads)

    current_cap_addr = "127.0.0.1:9001"

    mock_ac = MagicMock()
    mock_ac.profile = "tcp"
    mock_ac.config.common.public_ip = ""
    mock_ac.get_listen_addr = MagicMock(side_effect=lambda cap: current_cap_addr)

    nm = new_network_manager(max_retries=10, base_delay_ms=5, max_delay_ms=20, app_config=mock_ac)

    def mock_establish(ip_or_ep, port=None, _pub="", _prof=""):
        p = ip_or_ep.port if hasattr(ip_or_ep, "port") else port
        if p == "9001":
            if not server1_alive:
                raise Exception("Connection refused: server1 is dead")
            return s1_sock
        elif p == "9002":
            return s2_sock
        raise Exception(f"Unknown port: {p}")

    nm.establish_connection = MagicMock(side_effect=mock_establish)

    # 1. Connect to capability
    mc = nm.connect_capability("trade-engine")
    assert mc.get_endpoint() == ("127.0.0.1", "9001")

    # 2. Write order-1 to Server 1
    mc.write(b"order-1")
    assert server1_payloads == [b"order-1"]

    # 3. Kill Server 1 and update LiveConfig in AppConfig
    server1_alive = False
    current_cap_addr = "127.0.0.1:9002"

    # 4. Write order-2 -> write fails -> reconnect immediately reads updated AppConfig -> dials Server 2 -> retries write!
    mc.write(b"order-2")

    assert server2_payloads == [b"order-2"]
    assert mc.get_endpoint() == ("127.0.0.1", "9002")




