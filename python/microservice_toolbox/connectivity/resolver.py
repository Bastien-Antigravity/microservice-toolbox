#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Resolver handles network address validation and resolution strictly from AppConfig.

DATA FLOW:
1. Receives pre-validated address or host:port from AppConfig.
2. Preserves configured bind IP verbatim without injecting hardcoded defaults (fail-fast on empty).

KEY PARAMETERS:
- requested_ip: The IP address provided by configuration.
"""

from os import getenv as osGetenv
from os.path import exists as osPathExists
from socket import (
    AF_INET as socketAF_INET,
    getaddrinfo as socketGetAddrInfo,
    gethostname as socketGetHostName,
)

# -----------------------------------------------------------------------------------------------


class Resolver:
    """
    Resolver handles config-driven network address resolution with zero hardcoded defaults.
    """

    Name = "Resolver"

    # -----------------------------------------------------------------------------------------------

    def __init__(self):
        # Detect Docker environment
        self.is_docker = osPathExists("/.dockerenv") or osGetenv("DOCKER_ENV") == "true"

    # -----------------------------------------------------------------------------------------------

    def resolve_bind_addr(self, requested_ip: str) -> str:
        """
        Validates and returns the configured IP directly (fail-fast if empty, no hardcoded fallback).
        """
        if not requested_ip or not requested_ip.strip():
            raise ValueError("{0}.resolve_bind_addr: configured bind IP must not be empty (FAIL-FAST)".format(self.Name))
        return requested_ip

    # -----------------------------------------------------------------------------------------------

    def resolve_full_bind_addr(self, addr: str) -> str:
        """
        Validates and returns a configured "host:port", "[ipv6]:port", or bare host string.
        """
        if not addr or not addr.strip():
            raise ValueError("{0}.resolve_full_bind_addr: configured bind address must not be empty (FAIL-FAST)".format(self.Name))

        if addr.startswith("[") and "]:" in addr:
            host_bracketed, port = addr.rsplit(":", 1)
            if not port.strip():
                raise ValueError("{0}.resolve_full_bind_addr: configured port must not be empty (FAIL-FAST)".format(self.Name))
            resolved_host = self.resolve_bind_addr(host_bracketed[1:-1])
            formatted_host = f"[{resolved_host}]" if ":" in resolved_host else resolved_host
            return f"{formatted_host}:{port}"
        if addr.count(":") == 1:
            host, port = addr.split(":", 1)
            if not port.strip():
                raise ValueError("{0}.resolve_full_bind_addr: configured port must not be empty (FAIL-FAST)".format(self.Name))
            return f"{self.resolve_bind_addr(host)}:{port}"
        return self.resolve_bind_addr(addr)

    # -----------------------------------------------------------------------------------------------

    def is_docker_env(self) -> bool:
        """Returns whether the resolver detected a Docker container environment."""
        return bool(self.is_docker)

    # -----------------------------------------------------------------------------------------------

    def is_loopback(self, ip: str) -> bool:
        """
        Checks if the IP is a loopback address.
        """
        return ip.startswith("127.") or ip == "::1" or ip.lower() == "localhost"

    # -----------------------------------------------------------------------------------------------

    def get_primary_interface_ip(self) -> str:
        """
        Finds the first non-loopback IPv4 address for the local host without hardcoded probe IPs.
        """
        try:
            infos = socketGetAddrInfo(socketGetHostName(), None, socketAF_INET)
            for info in infos:
                ip = info[4][0]
                if ip and not self.is_loopback(ip):
                    return ip
        except OSError:
            pass
        raise RuntimeError("{0} : no primary network interface found".format(self.Name))


# -----------------------------------------------------------------------------------------------


def new_resolver() -> Resolver:
    """Factory method for Resolver."""
    return Resolver()
