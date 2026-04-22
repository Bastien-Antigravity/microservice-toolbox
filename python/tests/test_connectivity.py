from microservice_toolbox.connectivity.resolver import Resolver


def test_resolver_loopback():
    r = Resolver()
    # Check is_loopback logic
    assert r.is_loopback("127.0.0.1") is True
    assert r.is_loopback("127.255.255.255") is True
    assert r.is_loopback("::1") is True
    assert r.is_loopback("localhost") is True
    assert r.is_loopback("1.2.3.4") is False


def test_resolver_resolve_bind_addr_native():
    # Force native mode (not Docker)
    r = Resolver()
    r.is_docker = False

    assert r.resolve_bind_addr("127.0.0.1") == "127.0.0.1"
    assert r.resolve_bind_addr("8.8.8.8") == "8.8.8.8"


def test_resolver_resolve_bind_addr_docker_external():
    # In Docker mode, but external IP is requested
    r = Resolver()
    r.is_docker = True

    assert r.resolve_bind_addr("8.8.8.8") == "8.8.8.8"


# Note: Mocking get_primary_interface_ip would require monkeypatching socket.socket.connect
