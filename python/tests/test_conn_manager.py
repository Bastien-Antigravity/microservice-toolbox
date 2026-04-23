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

    def slow_connect(*args, **kwargs):
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

    def on_error(attempt, err, source, msg):
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

    def on_error(attempt, err, source, msg):
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
