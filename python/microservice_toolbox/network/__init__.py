#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Standardized network primitives including gRPC server abstractions with Docker Guard.

DATA FLOW:
Service Definition -> GRPCServer -> Network Port Binding with Docker Guard

KEY PARAMETERS:
- GRPCServer: Standardized gRPC server wrapper.
"""

from .grpc_server import GRPCServer
from .tls import (
    build_client_ssl_credentials,
    create_aio_channel,
    is_local_address,
    normalize_tls_mode,
    should_use_client_tls,
)

__all__ = [
    "GRPCServer",
    "build_client_ssl_credentials",
    "create_aio_channel",
    "is_local_address",
    "normalize_tls_mode",
    "should_use_client_tls",
]
