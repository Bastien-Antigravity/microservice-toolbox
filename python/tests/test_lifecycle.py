#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for Python LifecycleManager LIFO execution and shutdown signaling.
"""

from microservice_toolbox.lifecycle import new_manager


def test_lifecycle_lifo_execution():
    lm = new_manager()
    order = []
    lm.register("first", lambda: order.append("first"))
    lm.register("second", lambda: order.append("second"))
    lm.execute_cleanups()
    assert order == ["second", "first"]
    # Second call should be a no-op since hooks drained cleanly
    lm.execute_cleanups()
    assert order == ["second", "first"]

