#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Standardized gRPC server wrapper for the microservice-toolbox.
Provides lifecycle management for gRPC services with consistent binding and logging.

DATA FLOW:
1. Receives a listen address and worker configuration.
2. Services are registered via add_service().
3. Server starts listening and blocks until termination.

KEY PARAMETERS:
- addr: The address to bind the gRPC server (e.g., '0.0.0.0:50051').
- max_workers: Number of threads in the gRPC pool.
"""

from concurrent import futures
from typing import Any, Callable, Optional

import grpc

from ..utils.logger import Logger, ensure_safe_logger

# -----------------------------------------------------------------------------------------------


class GRPCServer:
    """
    Standardized gRPC server wrapper for the microservice-toolbox.
    Provides basic start/stop functionality with consistent logging.
    """

    Name = "GRPCServer"

    # -----------------------------------------------------------------------------------------------

    def __init__(self, addr: str, max_workers: int = 10, logger: Optional[Logger] = None):
        self.addr = addr
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        self.logger = ensure_safe_logger(logger)
        self._stopped = False

    # -----------------------------------------------------------------------------------------------

    def add_service(self, add_func: Callable[[Any, Any], None], servicer: Any) -> None:
        """
        Add a service to the gRPC server.
        Example: server.add_service(msg_pb2_grpc.add_LogServiceServicer_to_server, MyServicer())
        """
        add_func(servicer, self.server)

    # -----------------------------------------------------------------------------------------------

    def start(self) -> None:
        """Start the gRPC server."""
        self.logger.info("{0} : listening on {1}".format(self.Name, self.addr))
        self.server.add_insecure_port(self.addr)
        self.server.start()

    # -----------------------------------------------------------------------------------------------

    def wait_for_termination(self) -> None:
        """Block until the server is terminated."""
        try:
            self.server.wait_for_termination()
        except KeyboardInterrupt:
            self.stop()

    # -----------------------------------------------------------------------------------------------

    def stop(self, grace: int = 5) -> None:
        """Stop the gRPC server gracefully."""
        if not self._stopped:
            self.logger.info("{0} : Stopping server (grace: {1}s)...".format(self.Name, grace))
            self.server.stop(grace)
            self._stopped = True
