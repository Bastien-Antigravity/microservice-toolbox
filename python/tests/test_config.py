import os
import pytest
import yaml
from microservice_toolbox.config.loader import load_config, AppConfig

def test_app_config_deep_merge():
    dst = {"a": 1, "b": {"c": 2}}
    src = {"b": {"d": 3}, "e": 4}
    
    AppConfig.deep_merge(dst, src)
    
    assert dst["a"] == 1
    assert dst["e"] == 4
    assert dst["b"]["c"] == 2
    assert dst["b"]["d"] == 3

def test_app_config_loading(tmp_path):
    # Create temp config file
    config_file = tmp_path / "test-profile.yaml"
    config_data = {
        "common": {"name": "test-app"},
        "capabilities": {
            "test-service": {
                "ip": "1.2.3.4",
                "port": "8080"
            }
        }
    }
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    
    # Change CWD to tmp_path so load_config finds the file
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    try:
        ac = load_config("test-profile", input_args=[])
        assert ac.profile == "test-profile"
        assert ac.get_listen_addr("test-service") == "1.2.3.4:8080"
        
        # Test gRPC fallback
        assert ac.get_grpc_listen_addr("test-service") == "1.2.3.4:8081"
    finally:
        os.chdir(old_cwd)

def test_app_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("non-existent-profile", input_args=[])
