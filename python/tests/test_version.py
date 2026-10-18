#!/usr/bin/env python
# coding:utf-8

"""
Unit tests for microservice_toolbox.version dynamic resolution.
"""

import os
from pathlib import Path
import pytest

from microservice_toolbox.version import (
    get_version,
    resolve_version,
    set_version,
    reset_version,
    DEFAULT_FALLBACK_VERSION,
)
from microservice_toolbox import load_config


@pytest.fixture(autouse=True)
def clean_version_cache():
    reset_version()
    old_app_ver = os.environ.get("APP_VERSION")
    old_svc_ver = os.environ.get("SERVICE_VERSION")
    yield
    reset_version()
    if old_app_ver is not None:
        os.environ["APP_VERSION"] = old_app_ver
    else:
        os.environ.pop("APP_VERSION", None)
    if old_svc_ver is not None:
        os.environ["SERVICE_VERSION"] = old_svc_ver
    else:
        os.environ.pop("SERVICE_VERSION", None)


def test_default_resolution_from_repo():
    v = get_version()
    assert v == "0.0.1"


def test_env_override_app_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "2.9.1")
    v = resolve_version()
    assert v == "2.9.1"


def test_env_override_service_version(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("SERVICE_VERSION", "3.4.0-rc2")
    v = resolve_version()
    assert v == "3.4.0-rc2"


def test_caching_behavior(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.0.1")
    first = get_version()
    assert first == "1.0.1"

    # Mutate env without reset - should return cached value
    monkeypatch.setenv("APP_VERSION", "2.0.2")
    cached = get_version()
    assert cached == "1.0.1"

    # Reset clears cache
    reset_version()
    fresh = get_version()
    assert fresh == "2.0.2"


def test_set_version():
    set_version("5.5.5")
    assert get_version() == "5.5.5"


def test_app_config_version_integration():
    cfg = load_config("standalone", input_args=[])
    assert cfg.get_version() == "0.0.1"
    assert cfg.version == "0.0.1"
