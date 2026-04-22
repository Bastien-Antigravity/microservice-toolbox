import os
import sys
from pathlib import Path

# Add universal-logger/python to sys.path to find 'unilog' package
uni_logger_path = str(Path(__file__).parent.parent.parent / "universal-logger" / "python")
sys.path.append(uni_logger_path)

try:
    from unilog.facade import UniLog

    from microservice_toolbox.config.loader import load_config_with_logger
    from microservice_toolbox.conn_manager.manager import NewNetworkManagerWithLogger
    from microservice_toolbox.utils.logger import UniLogger

    print(">>> Initializing UniLog (compiled)...")
    native_log = UniLog(config_profile="standalone", app_name="test-python")
    logger = UniLogger(native_log)

    print(">>> Testing NetworkManager with UniLogger...")
    nm = NewNetworkManagerWithLogger(max_retries=2, logger=logger)
    try:
        # This will fail and log retries
        nm.connect_with_retry("localhost", "1234", "127.0.0.1", "test")
    except Exception as e:
        print(f">>> Expected failure: {e}")

    print(">>> Testing AppConfig with UniLogger...")
    # Requires a standalone.yaml to exist in current dir
    if os.path.exists("standalone.yaml"):
        conf = load_config_with_logger("standalone", logger=logger)
        print(f">>> Config loaded for profile: {conf.profile}")
    else:
        print(">>> Skipping AppConfig test (standalone.yaml not found)")

    print(">>> SUCCESS: Python Toolbox modernized with compiled universal-logger!")

except ImportError as e:
    print(f">>> FAILED: Could not import unilog or toolbox modules: {e}")
except Exception as e:
    print(f">>> FAILED: Unexpected error: {e}")
    import traceback

    traceback.print_exc()
