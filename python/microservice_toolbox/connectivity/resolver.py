#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Resolver handles environment-aware network address translation.
Implements the 'Docker Guard' policy to ensure fleet reachability.

DATA FLOW:
1. Detects Docker environment upon initialization.
2. If in Docker, forces bind addresses to 0.0.0.0 to support container orchestration.

KEY PARAMETERS:
- requested_ip: The IP address provided by configuration or user.
"""

from os import getenv as osGetenv
from os.path import exists as osPathExists
from socket import AF_INET as socketAF_INET
from socket import SOCK_DGRAM as socketSOCK_DGRAM
from socket import gethostbyname as socketGetHostByName
from socket import gethostname as socketGetHostName
from socket import socket as socketSocket

# -----------------------------------------------------------------------------------------------


class Resolver:
    """
    Resolver handles environment-aware network address translation.
    """

    Name = "Resolver"

    # -----------------------------------------------------------------------------------------------

    def __init__(self):
        # Detect Docker environment
        self.is_docker = osPathExists("/.dockerenv") or osGetenv("DOCKER_ENV") == "true"

    # -----------------------------------------------------------------------------------------------

    def resolve_bind_addr(self, requested_ip: str) -> str:
        """
        Resolves the requested IP into an actual address to bind to.

        Docker Guard Logic:
        If running in a Docker container, this method suppresses the requested IP
        and forces a bind to 0.0.0.0. This ensures that the container port mapping
        (Docker/K8s) works regardless of what was specified in the configuration.
        """
        requested_ip = requested_ip.strip('"')

        # If not in Docker, use the requested IP directly.
        if not self.is_docker:
            return requested_ip

        # In Docker, we force 0.0.0.0 to ensure orchestrated networking works.
        # This "suppresses" any manual IP overrides.
        return "0.0.0.0"

    # -----------------------------------------------------------------------------------------------

    def resolve_full_bind_addr(self, addr: str) -> str:
        """
        Takes a "host:port" string and returns a resolved "host:port"
        using the Docker Guard logic.
        """
        if ":" not in addr:
            return self.resolve_bind_addr(addr)

        host, port = addr.rsplit(":", 1)
        resolved_host = self.resolve_bind_addr(host)
        return f"{resolved_host}:{port}"

    # -----------------------------------------------------------------------------------------------

    def is_loopback(self, ip: str) -> bool:
        """
        Checks if the IP is a loopback address.
        """
        return ip.startswith("127.") or ip == "::1" or ip.lower() == "localhost"

    # -----------------------------------------------------------------------------------------------

    def get_primary_interface_ip(self) -> str:
        """
        Finds the first non-loopback IP address using a UDP socket trick.
        Keep as utility for potential client-side discovery.
        """
        s = socketSocket(socketAF_INET, socketSOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip and not self.is_loopback(ip):
                return ip
        except Exception:
            pass
        finally:
            s.close()

        # Fallback to hostname resolution
        try:
            return socketGetHostByName(socketGetHostName())
        except Exception:
            raise RuntimeError("{0} : no primary network interface found".format(self.Name))


# -----------------------------------------------------------------------------------------------


def new_resolver() -> Resolver:
    """Factory method for Resolver."""
    return Resolver()
