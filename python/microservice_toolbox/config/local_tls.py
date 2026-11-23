#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Defines the LocalTLSConfig model and extraction helpers for service-private X.509 TLS/mTLS paths.
Strictly reads from the 'local:' configuration namespace and never from shared 'capabilities:'.

DATA FLOW:
YAML local.<service>.tls / local.tls -> extract_local_tls_config() -> LocalTLSConfig

KEY PARAMETERS:
- cert_file: Path to the service X.509 certificate PEM file.
- key_file: Path to the service X.509 private key PEM file.
- ca_file: Path to the Fleet Root CA certificate PEM file.
- verify_client: Optional explicit override for mTLS client certificate verification.
"""

from dataclasses import dataclass as dataclassesDataclass
from typing import Any as typeAny, Dict as typeDict, Optional as typeOptional

# -----------------------------------------------------------------------------------------------


@dataclassesDataclass
class LocalTLSConfig:
    """Service-private X.509 TLS/mTLS file paths from the local: configuration section."""

    cert_file: str = ""
    key_file: str = ""
    ca_file: str = ""
    verify_client: typeOptional[bool] = None

    # -------------------------------------------------------------------------------------------

    def should_verify_client(self) -> bool:
        """
        Returns True when mTLS client verification is active.
        Defaults to True whenever ca_file is configured and verify_client is not explicitly False.
        """
        if self.verify_client is not None:
            return self.verify_client
        return bool(self.ca_file.strip())

    # -------------------------------------------------------------------------------------------

    def is_empty(self) -> bool:
        """Returns True when all path fields are empty and verify_client is unset."""
        return (
            not self.cert_file.strip()
            and not self.key_file.strip()
            and not self.ca_file.strip()
            and self.verify_client is None
        )


# -----------------------------------------------------------------------------------------------


def _extract_trimmed_string(raw: typeAny) -> str:
    if isinstance(raw, str):
        return raw.strip()
    return ""


# -----------------------------------------------------------------------------------------------


def _extract_local_tls_from_map(mapping: typeDict[typeAny, typeAny]) -> LocalTLSConfig:
    cfg = LocalTLSConfig(
        cert_file=_extract_trimmed_string(mapping.get("cert_file")),
        key_file=_extract_trimmed_string(mapping.get("key_file")),
        ca_file=_extract_trimmed_string(mapping.get("ca_file")),
    )

    if "verify_client" in mapping and mapping["verify_client"] is not None:
        raw_verify = mapping["verify_client"]
        if isinstance(raw_verify, bool):
            cfg.verify_client = raw_verify
        elif isinstance(raw_verify, str):
            lowered = raw_verify.strip().lower()
            if lowered == "true":
                cfg.verify_client = True
            elif lowered == "false":
                cfg.verify_client = False

    return cfg


# -----------------------------------------------------------------------------------------------


def extract_local_tls_config(raw: typeAny) -> LocalTLSConfig:
    """Normalizes a raw dict or LocalTLSConfig instance into a trimmed LocalTLSConfig."""
    if raw is None:
        return LocalTLSConfig()

    if isinstance(raw, LocalTLSConfig):
        return LocalTLSConfig(
            cert_file=raw.cert_file.strip(),
            key_file=raw.key_file.strip(),
            ca_file=raw.ca_file.strip(),
            verify_client=raw.verify_client,
        )

    if isinstance(raw, dict):
        return _extract_local_tls_from_map(raw)

    return LocalTLSConfig()
