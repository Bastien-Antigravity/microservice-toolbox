#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides reusable X.509 TLS/mTLS client policy helpers and grpc.aio channel constructors
mirroring the Go microservice-toolbox network/tls package.

DATA FLOW:
LocalTLSConfig + TLS Policy (enabled, mode, target_ip) -> SSL Credentials -> grpc.aio Channel

KEY PARAMETERS:
- local_tls: Service-private X.509 cert_file, key_file, ca_file, and verify_client.
- tls_enabled: Fleet capability toggle for TLS on non-local links.
- tls_mode: Policy mode ("auto", "local_plaintext", "remote_only", "strict", "required", "disabled").
"""

from ipaddress import ip_address as ipaddressIpAddress
from typing import Optional as typeOptional

from grpc import (
    ChannelCredentials as grpcChannelCredentials,
    aio as grpcAio,
    ssl_channel_credentials as grpcSslChannelCredentials,
)

from ..config.local_tls import LocalTLSConfig

# -----------------------------------------------------------------------------------------------


def normalize_tls_mode(mode: str) -> str:
    """Canonicalizes a TLS policy mode string, defaulting empty values to 'auto'."""
    normalized = mode.strip().lower() if mode else ""
    if not normalized:
        return "auto"
    return normalized


# -----------------------------------------------------------------------------------------------


def is_local_address(host: str) -> bool:
    """Reports whether host represents a loopback or localhost address."""
    cleaned = host.strip().strip("[]") if host else ""
    if not cleaned:
        return False
    if cleaned.lower() == "localhost":
        return True
    try:
        return bool(ipaddressIpAddress(cleaned).is_loopback)
    except ValueError:
        return False


# -----------------------------------------------------------------------------------------------


def _extract_host(target: str) -> str:
    host = target.strip() if target else ""
    if not host:
        return ""
    if host.startswith("[") and "]" in host:
        return host[1:host.index("]")]
    if host.count(":") == 1:
        host_part, _ = host.split(":", 1)
        return host_part
    return host


# -----------------------------------------------------------------------------------------------


def should_use_client_tls(target_ip: str, tls_enabled: bool, tls_mode: str) -> bool:
    """
    Determines whether an outbound gRPC client connection to target_ip must use TLS
    according to target locality and fleet TLS policy.
    """
    mode = normalize_tls_mode(tls_mode)
    host = _extract_host(target_ip)

    if mode == "disabled":
        return False
    if mode in ("strict", "required"):
        return True
    return (bool(tls_enabled) or mode == "remote_only") and not is_local_address(host)


# -----------------------------------------------------------------------------------------------


def build_client_ssl_credentials(local_tls: LocalTLSConfig) -> grpcChannelCredentials:
    """
    Loads and validates X.509 client TLS/mTLS credentials on the cold path.
    Requires ca_file; if either cert_file or key_file is set, requires both for mTLS.
    """
    ca_file = local_tls.ca_file.strip()
    cert_file = local_tls.cert_file.strip()
    key_file = local_tls.key_file.strip()

    if not ca_file:
        raise ValueError("TLS client config requires ca_file")

    with open(ca_file, "rb") as ca_handle:
        ca_bytes = ca_handle.read()
    if not ca_bytes.strip():
        raise ValueError(f"TLS CA file is empty: {ca_file}")

    cert_bytes: typeOptional[bytes] = None
    key_bytes: typeOptional[bytes] = None
    if cert_file or key_file:
        if not cert_file or not key_file:
            raise ValueError("TLS client mTLS identity requires both cert_file and key_file")
        with open(cert_file, "rb") as cert_handle:
            cert_bytes = cert_handle.read()
        if not cert_bytes.strip():
            raise ValueError(f"TLS client certificate file is empty: {cert_file}")
        with open(key_file, "rb") as key_handle:
            key_bytes = key_handle.read()
        if not key_bytes.strip():
            raise ValueError(f"TLS client private key file is empty: {key_file}")

    return grpcSslChannelCredentials(
        root_certificates=ca_bytes,
        private_key=key_bytes,
        certificate_chain=cert_bytes,
    )


# -----------------------------------------------------------------------------------------------


def create_aio_channel(
    addr: str,
    target_ip: str,
    local_tls: LocalTLSConfig,
    tls_enabled: bool,
    tls_mode: str,
    explicit_credentials: typeOptional[grpcChannelCredentials] = None,
) -> grpcAio.Channel:
    """
    Creates an async gRPC channel matching target locality and TLS policy.
    Uses explicit_credentials when provided, TLS/mTLS when policy requires it, else insecure.
    """
    if explicit_credentials is not None:
        return grpcAio.secure_channel(addr, explicit_credentials)
    if should_use_client_tls(target_ip, tls_enabled, tls_mode):
        creds = build_client_ssl_credentials(local_tls)
        return grpcAio.secure_channel(addr, creds)
    return grpcAio.insecure_channel(addr)
