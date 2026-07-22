#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Standardized, reliable bootstrapper for Python microservices.
"""

import os
import sys
from pathlib import Path
from typing import Tuple, Any, Optional

from .bootstrap import (
    _find_nearest_venv,
    get_venv_python,
    find_vault_root,
    prepend_venv_bin,
    ensure_import_paths,
    redirect_working_directory,
)


def init_microservice(
    app_name: str,
    config_profile: str = "standalone",
    logger_profile: Optional[str] = None,
    log_level: str = "info"
) -> Tuple[Any, Any]:
    """
    Standardized, reliable bootstrapper for Python microservices.
    
    1. Identifies the nearest virtualenv and CGO master dylib.
    2. Forces a relaunch with aligned environment variables if not already set.
    3. Loads the distributed configuration.
    4. Initializes the UniLog logging client.
    
    Returns (config, logger). Raises RuntimeError or ValueError if initialization fails.
    """
    # 1. Resolve path components
    script_dir = Path(sys.argv[0]).resolve().parent
    _venv_parent = _find_nearest_venv(str(script_dir))
    _venv_dir = _venv_parent / ".venv"
    _venv_python = get_venv_python(_venv_parent)
    
    # Resolve the master libunilog dylib path
    _dylib_path = None
    _candidates = [
        _venv_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "unilog" / "libunilog.dylib",
        _venv_parent / "universal-logger" / "unilog" / "libunilog" / "libunilog.dylib",
        _venv_parent / "universal-logger" / "unilog" / "python" / "unilog" / "libunilog.dylib"
    ]
    # Fallback to walking up to find vault root
    vault_root = find_vault_root(str(script_dir))
    _candidates.extend([
        vault_root / "universal-logger" / "unilog" / "libunilog" / "libunilog.dylib",
        vault_root / "universal-logger" / "unilog" / "python" / "unilog" / "libunilog.dylib"
    ])
    
    for _c in _candidates:
        if _c.exists():
            _dylib_path = str(_c.resolve())
            break
            
    if not _dylib_path:
        sys.stderr.write("❌ INITIALIZATION ERROR: libunilog shared library not found in workspace candidates.\n")
        sys.exit(1)
        
    # Check if environment is already aligned or we need to relaunch
    has_venv = sys.prefix == str(_venv_dir)
    has_env = os.environ.get("LIBUNILOG_PATH") == _dylib_path and os.environ.get("LIBDISTCONF_PATH") == _dylib_path
    
    if not (has_venv and has_env):
        # Align environment and relaunch
        os.environ["LIBUNILOG_PATH"] = _dylib_path
        os.environ["LIBDISTCONF_PATH"] = _dylib_path
        os.environ["GODEBUG"] = "cgocheck=0"
        os.environ.pop("PYTHONPATH", None)
        
        python_bin = _venv_python if os.path.exists(_venv_python) else sys.executable
        try:
            os.execve(python_bin, [python_bin] + sys.argv, os.environ)
        except Exception as e:
            sys.stderr.write(f"❌ INITIALIZATION ERROR: Failed to relaunch process: {e}\n")
            sys.exit(1)
            
    # If we reach here, we are running in the aligned process!
    prepend_venv_bin(_venv_parent)
    ensure_import_paths(script_dir, vault_root)
    
    # Add virtualenv site-packages to sys.path
    _site_packages = _venv_dir / ("Lib/site-packages" if os.name == "nt" else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    if _site_packages.exists() and str(_site_packages) not in sys.path:
        sys.path.insert(0, str(_site_packages))
        
    redirect_working_directory(script_dir)
    
    try:
        from microservice_toolbox.config.lib_loader import load_libdistconf
        load_libdistconf()
        
        from microservice_toolbox.config.loader import load_config
        from microservice_toolbox.logger import UniLog
        
        config = load_config(config_profile, input_args=[])
        if not config:
            raise RuntimeError("Failed to load configuration.")
            
        config_handle = getattr(config, "_handle", 0) or 0
        
        if not logger_profile:
            devel_mode = bool(config.data.get("capabilities", {}).get("rag_engine", {}).get("devel", True))
            logger_profile = os.environ.get("LOGGER_PROFILE", "devel" if devel_mode else "standard")
            
        logger = UniLog(
            app_name=app_name,
            config_profile=config_profile,
            logger_profile=logger_profile,
            log_level=log_level,
            config_handle=config_handle
        )
        
        config.set_logger(logger)
        return config, logger
    except Exception as e:
        sys.stderr.write(f"❌ INITIALIZATION ERROR: {e}\n")
        sys.exit(1)
