#!/usr/bin/env python
# coding:utf-8

"""
# -----------------------------------------------------------------------------------------------
# ESSENTIAL PROCESS:
# Notification package root providing NotificationClient facade for Python.
#
# DATA FLOW:
# Callers -> NotificationClient -> gRPC Protobuf -> notif-server
# -----------------------------------------------------------------------------------------------
"""

from .client import (
    DEFAULT_TIMEOUT,
    NotificationClient,
    new_client,
    new_client_with_target,
)

__all__ = [
    "NotificationClient",
    "new_client",
    "new_client_with_target",
    "DEFAULT_TIMEOUT",
]
