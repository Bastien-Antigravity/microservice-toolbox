#!/usr/bin/env python
# coding:utf-8

"""
Unit tests for microservice_toolbox.version dynamic resolution.
"""

import pytest

from microservice_toolbox import load_config
from microservice_toolbox.version import (
    get_version,
    reset_version,
    resolve_version,
    set_version,
)


@pytest.fixture(autouse=True)
def clean_version_cache():
    reset_version()
    yield
    reset_version()


def test_default_resolution_from_repo():
    v = get_version()
    assert v == "0.0.1"


def test_resolution_from_isolated_version_file(tmp_path, monkeypatch):
    svc_dir = tmp_path / "demo_svc"
    nested = svc_dir / "src" / "handlers"
    nested.mkdir(parents=True)
    (svc_dir / "VERSION.txt").write_text("2.9.1\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    assert resolve_version(caller_file=str(nested / "routes.py")) == "2.9.1"


def test_env_vars_do_not_override_version_txt(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.setenv("SERVICE_VERSION", "8.8.8")
    svc_dir = tmp_path / "strict_svc"
    svc_dir.mkdir()
    (svc_dir / ".git").mkdir()
    (svc_dir / "VERSION.txt").write_text("3.4.0\n", encoding="utf-8")
    monkeypatch.chdir(svc_dir)

    assert resolve_version(caller_file=str(svc_dir / "main.py")) == "3.4.0"


def test_caching_behavior(tmp_path, monkeypatch):
    svc_dir = tmp_path / "cached_svc"
    svc_dir.mkdir()
    (svc_dir / ".git").mkdir()
    ver_file = svc_dir / "VERSION.txt"
    ver_file.write_text("1.0.1\n", encoding="utf-8")
    monkeypatch.chdir(svc_dir)

    first = get_version(caller_file=str(svc_dir / "main.py"))
    assert first == "1.0.1"

    # Mutate file without reset - should return cached value
    ver_file.write_text("2.0.2\n", encoding="utf-8")
    cached = get_version(caller_file=str(svc_dir / "main.py"))
    assert cached == "1.0.1"

    # Reset clears cache
    reset_version()
    fresh = get_version(caller_file=str(svc_dir / "main.py"))
    assert fresh == "2.0.2"


def test_set_version():
    set_version("5.5.5")
    assert get_version() == "5.5.5"

    with pytest.raises(ValueError):
        set_version("   ")


def test_fail_fast_when_version_missing(tmp_path, monkeypatch):
    isolated = tmp_path / "isolated_svc"
    isolated.mkdir()
    (isolated / ".git").mkdir()
    monkeypatch.chdir(isolated)

    with pytest.raises(RuntimeError):
        resolve_version(caller_file=str(isolated / "main.py"))

    with pytest.raises(RuntimeError):
        get_version(caller_file=str(isolated / "main.py"))


def test_app_config_version_integration():
    cfg = load_config("standalone", input_args=[])
    assert cfg.get_version() == "0.0.1"
    assert cfg.version == "0.0.1"
