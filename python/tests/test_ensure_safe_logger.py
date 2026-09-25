#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for ensure_safe_logger, verifying safe fallback and strict mode enforcement.

DATA FLOW:
Logger instance -> ensure_safe_logger() -> assertion

KEY PARAMETERS:
- STRICT_LOGGER: Environment variable toggling strict mode.
"""

import os
import pytest
from microservice_toolbox.logger.logger import ensure_safe_logger, PythonLogger


def test_ensure_safe_logger_fallback():
    if "STRICT_LOGGER" in os.environ:
        del os.environ["STRICT_LOGGER"]
    log = ensure_safe_logger(None)
    assert log is not None
    # Calling methods must not fail
    log.info("test info")
    log.debug("test debug")
    log.warning("test warning")
    log.error("test error")
    log.critical("test critical")


def test_ensure_safe_logger_strict_mode():
    os.environ["STRICT_LOGGER"] = "true"
    try:
        with pytest.raises(RuntimeError, match="CRITICAL ARCHITECTURAL VIOLATION"):
            ensure_safe_logger(None)
    finally:
        del os.environ["STRICT_LOGGER"]


def test_ensure_safe_logger_passthrough():
    custom = PythonLogger("custom")
    log = ensure_safe_logger(custom)
    assert log is custom
