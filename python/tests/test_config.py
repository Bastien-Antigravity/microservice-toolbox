import os

import pytest
import yaml

from microservice_toolbox.config.loader import AppConfig, load_config

# ---- Deep Merge ----

def test_app_config_deep_merge():
    dst = {"a": 1, "b": {"c": 2}}
    src = {"b": {"d": 3}, "e": 4}

    AppConfig.deep_merge(dst, src)

    assert dst["a"] == 1
    assert dst["e"] == 4
    assert dst["b"]["c"] == 2
    assert dst["b"]["d"] == 3


# ---- Config Loading ----

def test_load_config_factory(tmp_path):
    """Verify the load_config() factory function works (Go LoadConfig parity)."""
    config_file = tmp_path / "factory.yaml"
    yaml.dump({"common": {"name": "factory-app"}}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("factory", input_args=[])
        assert isinstance(ac, AppConfig)
        assert ac.profile == "factory"
    finally:
        os.chdir(old_cwd)


def test_app_config_loading_and_addresses(tmp_path):
    """Verify loading, get_listen_addr, and get_grpc_listen_addr."""
    config_file = tmp_path / "test-profile.yaml"
    config_data = {
        "common": {"name": "test-app"},
        "capabilities": {
            "test-service": {
                "ip": "1.2.3.4", "port": "8080",
                "grpc_ip": "1.2.3.4", "grpc_port": "8081",
            }
        },
    }
    yaml.dump(config_data, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("test-profile", input_args=[])
        assert ac.profile == "test-profile"
        assert ac.get_listen_addr("test-service") == "1.2.3.4:8080"
        assert ac.get_grpc_listen_addr("test-service") == "1.2.3.4:8081"
    finally:
        os.chdir(old_cwd)


def test_app_config_missing_file():
    """Verify FileNotFoundError on missing profile (no bridge fallback)."""
    with pytest.raises(FileNotFoundError):
        load_config("non-existent-profile", input_args=[])


def test_grpc_missing_raises(tmp_path):
    """Verify get_grpc_listen_addr raises when grpc_ip/grpc_port are absent (Go parity)."""
    config_file = tmp_path / "no-grpc.yaml"
    yaml.dump({"capabilities": {"svc": {"ip": "1.2.3.4", "port": "8080"}}}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("no-grpc", input_args=[])
        with pytest.raises(ValueError):
            ac.get_grpc_listen_addr("svc")
    finally:
        os.chdir(old_cwd)


# ---- Decryption ----

def test_decrypt_secret_plaintext_passthrough(tmp_path):
    """Verify plaintext strings pass through unchanged."""
    config_file = tmp_path / "plain.yaml"
    yaml.dump({"common": {"name": "plain"}}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("plain", input_args=[])
        assert ac.decrypt_secret("normal_pass") == "normal_pass"
        assert ac.decrypt_secret("") == ""
        assert ac.decrypt_secret("ENC(no-closing-paren") == "ENC(no-closing-paren"
        assert ac.decrypt_secret("not-ENC(data)") == "not-ENC(data)"
    finally:
        os.chdir(old_cwd)


def test_decrypt_secret_enc_raises(tmp_path):
    """Verify ENC(...) block raises ValueError when decryption fails."""
    config_file = tmp_path / "secret.yaml"
    yaml.dump({"password": "ENC(dummy)"}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("secret", input_args=[])

        # Raw data is preserved
        assert ac.data["password"] == "ENC(dummy)"

        # Valid ENC() block but dummy content → must raise
        with pytest.raises(ValueError):
            ac.decrypt_secret("ENC(dummy)")
    finally:
        os.chdir(old_cwd)


# ---- Local Config ----

def test_get_local(tmp_path):
    """Verify get_local() returns values from the 'private' YAML section."""
    config_file = tmp_path / "local.yaml"
    yaml.dump({"private": {"local_setting": "value_xyz", "nested": {"a": 1}}}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("local", input_args=[])
        assert ac.get_local("local_setting") == "value_xyz"
        assert ac.get_local("nested") == {"a": 1}
        assert ac.get_local("missing") is None
    finally:
        os.chdir(old_cwd)


def test_get_local_empty(tmp_path):
    """Verify get_local() returns None when no private section exists."""
    config_file = tmp_path / "no-local.yaml"
    yaml.dump({"common": {"name": "test"}}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("no-local", input_args=[])
        assert ac.get_local("anything") is None
    finally:
        os.chdir(old_cwd)


def test_unmarshal_local(tmp_path):
    """Verify unmarshal_local() maps the private section to a class."""
    config_file = tmp_path / "unmarshal.yaml"
    yaml.dump({"private": {"local_setting": "value_xyz", "item_count": 5}}, open(config_file, "w"))

    class MyConfig:
        def __init__(self, local_setting=None, item_count=0):
            self.local_setting = local_setting
            self.item_count = item_count

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("unmarshal", input_args=[])
        
        # Test instantiating a type
        cfg = ac.unmarshal_local(MyConfig)
        assert cfg.local_setting == "value_xyz"
        assert cfg.item_count == 5

        # Test updating an existing instance
        cfg2 = MyConfig()
        ac.unmarshal_local(cfg2)
        assert cfg2.local_setting == "value_xyz"
        assert cfg2.item_count == 5
    finally:
        os.chdir(old_cwd)


# ---- Set Logger ----

def test_set_logger(tmp_path):
    """Verify set_logger replaces the logger safely."""
    config_file = tmp_path / "logger.yaml"
    yaml.dump({"common": {"name": "logger-test"}}, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("logger", input_args=[])
        old_logger = ac.logger

        # Setting None should not crash (ensure_safe_logger wraps it)
        ac.set_logger(None)
        assert ac.logger is not None
        assert ac.logger is not old_logger
    finally:
        os.chdir(old_cwd)


# ---- CLI Override Scope ----

def test_cli_override_targets_single_capability(tmp_path):
    """Verify CLI --host/--port overrides only the target capability (Go parity)."""
    config_file = tmp_path / "cli.yaml"
    yaml.dump({
        "common": {"name": "my-svc"},
        "capabilities": {
            "my-svc": {"ip": "0.0.0.0", "port": "9000"},
            "other-svc": {"ip": "0.0.0.0", "port": "9001"},
        },
    }, open(config_file, "w"))

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("cli", input_args=["--host", "10.0.0.1", "--port", "5555"])

        # Target capability (my-svc from common.name) should be overridden
        assert ac.get_listen_addr("my-svc") == "10.0.0.1:5555"

        # Other capability should NOT be affected
        assert ac.get_listen_addr("other-svc") == "0.0.0.0:9001"
    finally:
        os.chdir(old_cwd)


# ---- Env Expansion ----

def test_env_expansion(tmp_path):
    """Verify ${VAR:default} expansion in YAML loading."""
    config_file = tmp_path / "env.yaml"
    yaml.dump({
        "private": {
            "host": "${TEST_HOST:localhost}",
            "port": "${TEST_PORT:8080}",
        }
    }, open(config_file, "w"))

    os.environ["TEST_HOST"] = "127.0.0.5"
    if "TEST_PORT" in os.environ:
        del os.environ["TEST_PORT"]

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        ac = load_config("env", input_args=[])
        assert ac.get_local("host") == "127.0.0.5"
        # YAML parses 8080 as int unless quoted
        assert int(ac.get_local("port")) == 8080
    finally:
        os.chdir(old_cwd)
