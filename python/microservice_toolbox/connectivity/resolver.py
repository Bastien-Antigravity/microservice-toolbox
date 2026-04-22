#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Resolver handles environment-aware network address translation.
Specifically manages Docker-specific IP translation to ensure fleet reachability.

DATA FLOW:
1. Detects Docker environment upon initialization.
2. Translates loopback addresses (127.0.0.1) to primary interface IPs if in Docker.

KEY PARAMETERS:
- requested_ip: The IP address provided by configuration or user.
"""

from os.path import exists as osPathExists
from os import getenv as osGetenv
from socket import socket as socketSocket, AF_INET as socketAF_INET, SOCK_DGRAM as socketSOCK_DGRAM, gethostbyname as socketGetHostByName, gethostname as socketGetHostName

#-----------------------------------------------------------------------------------------------

class Resolver:
    """
    Resolver handles environment-aware network address translation.
    """
    Name = "Resolver"

    #-----------------------------------------------------------------------------------------------

    def __init__(self):
        # Detect Docker environment
        self.is_docker = osPathExists('/.dockerenv') or osGetenv('DOCKER_ENV') == 'true'

    #-----------------------------------------------------------------------------------------------

    def resolve_bind_addr(self, requested_ip: str) -> str:
        """
        Resolves the requested IP into an actual address to bind to.
        """
        requested_ip = requested_ip.strip('"')

        # If not in Docker, or if the IP isn't a loopback placeholder, use it directly.
        if not self.is_docker or not self.is_loopback(requested_ip):
            return requested_ip

        # In Docker, we need the internal container IP (e.g., eth0) for other containers to reach us.
        try:
            return self._get_primary_interface_ip()
        except Exception as e:
            # Fallback or re-raise depending on criticality. Matching Go's error handling.
            raise RuntimeError("{0} : failed to resolve container IP for bind: {1}".format(self.Name, e))

    #-----------------------------------------------------------------------------------------------

    def is_loopback(self, ip: str) -> bool:
        """
        Checks if the IP is a loopback address.
        """
        return ip.startswith('127.') or ip == '::1' or ip.lower() == 'localhost'

    #-----------------------------------------------------------------------------------------------

    def _get_primary_interface_ip(self) -> str:
        """
        Finds the first non-loopback IP address using a UDP socket trick.
        """
        s = socketSocket(socketAF_INET, socketSOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
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

#-----------------------------------------------------------------------------------------------

def new_resolver() -> Resolver:
    """Factory method for Resolver."""
    return Resolver()
