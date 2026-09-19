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

__all__ = ["GRPCServer"]
