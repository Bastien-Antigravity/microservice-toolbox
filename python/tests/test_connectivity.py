import pytest

from microservice_toolbox.connectivity.resolver import Resolver


def test_resolver_loopback():
    r = Resolver()
    # Check is_loopback logic
    assert r.is_loopback("127.0.0.1") is True
    assert r.is_loopback("127.255.255.255") is True
    assert r.is_loopback("::1") is True
    assert r.is_loopback("localhost") is True
    assert r.is_loopback("LocalHost") is True
    assert r.is_loopback("1.2.3.4") is False


def test_resolver_resolve_bind_addr_native():
    # Native mode preserves configured IP verbatim
    r = Resolver()
    r.is_docker = False

    assert r.resolve_bind_addr("127.0.0.1") == "127.0.0.1"
    assert r.resolve_bind_addr("8.8.8.8") == "8.8.8.8"


def test_resolver_preserves_config_in_docker_and_fails_fast_when_empty():
    # Even when is_docker=True, configured IPs are preserved verbatim (no hardcoded 0.0.0.0)
    r = Resolver()
    r.is_docker = True

    assert r.resolve_bind_addr("10.1.2.3") == "10.1.2.3"
    assert r.resolve_full_bind_addr("[::1]:8080") == "[::1]:8080"
    assert r.resolve_full_bind_addr("::1") == "::1"

    with pytest.raises(ValueError):
        r.resolve_bind_addr("")
    with pytest.raises(ValueError):
        r.resolve_full_bind_addr(":8080")
    with pytest.raises(ValueError):
        r.resolve_full_bind_addr("127.0.0.1:")


def test_resolver_detects_docker_env_only_from_env_var(monkeypatch):
    monkeypatch.delenv("DOCKER_ENV", raising=False)
    assert Resolver().is_docker_env() is False

    monkeypatch.setenv("DOCKER_ENV", "true")
    assert Resolver().is_docker_env() is True
