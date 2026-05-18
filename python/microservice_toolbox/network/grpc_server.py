#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Standardized gRPC server wrapper for the microservice-toolbox.
Provides lifecycle management for gRPC services with consistent binding and logging.

DATA FLOW:
1. Receives bind address and optional logger.
2. Resolves address using Docker Guard (via connectivity.Resolver).
3. Starts the gRPC server and blocks until stopped.

KEY PARAMETERS:
- addr: The requested bind address (e.g. "127.0.0.1:50051").
- logger: Optional logger for reporting status.
"""

from concurrent import futures
from typing import Any, Optional

import grpc

from ..connectivity.resolver import new_resolver
from ..utils.logger import Logger, ensure_safe_logger

# -----------------------------------------------------------------------------------------------


class GRPCServer:
    """
    Standardized gRPC server wrapper with Docker Guard and consistent logging.
    """

    Name = "GRPCServer"

    # -----------------------------------------------------------------------------------------------

    def __init__(self, addr: str, logger: Optional[Logger] = None, max_workers: int = 10):
        self.logger = ensure_safe_logger(logger)
        self.resolver = new_resolver()

        # Apply Docker Guard Suppression
        resolved_addr = self.resolver.resolve_full_bind_addr(addr)
        if resolved_addr != addr:
            self.logger.info(
                "{0} : Docker Guard suppressed bind address {1} -> {2}".format(self.Name, addr, resolved_addr)
            )

        self.addr = resolved_addr
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        self._stopped = False

    # -----------------------------------------------------------------------------------------------

    def start(self) -> None:
        """Starts the gRPC server and blocks."""
        port = self.server.add_insecure_port(self.addr)
        self.logger.info("{0} : Listening on {1} (assigned port: {2})".format(self.Name, self.addr, port))
        self.server.start()

    # -----------------------------------------------------------------------------------------------

    def stop(self, grace: int = 5) -> None:
        """Stop the gRPC server gracefully."""
        if not self._stopped:
            self.logger.info("{0} : Stopping server (grace: {1}s)...".format(self.Name, grace))
            self.server.stop(grace)
            self._stopped = True
