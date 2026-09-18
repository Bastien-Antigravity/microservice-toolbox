#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Standardized, reliable bootstrapper for Python microservices. Configures virtualenv paths, dynamic CGO library bindings, distributed configuration, and universal logging.

DATA FLOW:
1. Input: Application identity, profile names, and virtual environment paths.
2. Logic: Aligns virtualenv and CGO environment variables (LIBUNILOG_PATH, LIBDISTCONF_PATH), loads distributed configuration, and binds UniLog.
3. Output: Tuple of (config: AppConfig, logger: UniLog).

KEY PARAMETERS:
- app_name: Canonical identifier of the microservice application.
- config_profile: Configuration profile to load (default: "standalone").
- logger_profile: Optional logging profile sink (default: "cloud" in containers, "standard" on host).
- log_level: Initial minimum logging level string (default: "info").
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


# -----------------------------------------------------------------------------------------------
# ### SERVICE BOOTSTRAPPER ###
# -----------------------------------------------------------------------------------------------

def init_microservice(
    app_name: str,
    config_profile: str = "standalone",
    logger_profile: Optional[str] = None,
    log_level: str = "info"
) -> Tuple[Any, Any]:
    """
    Standardized, reliable bootstrapper for Python microservices.

    Aligns the process with the local virtualenv, binds to native CGO libraries (libunilog,
    libdistconf), loads the distributed configuration, and initializes the universal logger.

    Args:
        app_name: Canonical identifier of the microservice application.
        config_profile: Active configuration profile (e.g., 'standalone', 'production').
        logger_profile: Optional sink profile override. Defaults to 'cloud' if running in
            Docker/container, or 'standard' on host.
        log_level: Minimum threshold for log dispatching ('debug', 'info', 'warning', etc.).

    Returns:
        Tuple[AppConfig, UniLog]: Initialized and bound configuration and logging instances.

    Raises:
        RuntimeError: If the CGO shared library (libunilog) is missing, process relaunch fails,
            or configuration cannot be loaded.
    """
    # 1. Resolve path components
    script_dir = Path(sys.argv[0]).resolve().parent
    _venv_parent = _find_nearest_venv(str(script_dir))
    _venv_dir = _venv_parent / ".venv"
    _venv_python = get_venv_python(_venv_parent)
    
    vault_root = find_vault_root(str(script_dir))

    from .lib_loader import resolve_library_path

    # Resolve the master libunilog shared library path
    _dylib_path = resolve_library_path("libunilog", "LIBUNILOG_PATH")
    if not _dylib_path:
        _ext = ".dylib" if sys.platform == "darwin" else (".dll" if sys.platform == "win32" else ".so")
        raise RuntimeError(
            f"libunilog shared library (libunilog{_ext}) not found in workspace candidates or LIBUNILOG_PATH. "
            f"Please compile the CGO library ('make shared-lib' in universal-logger) or set the LIBUNILOG_PATH environment variable."
        )

    # Resolve libdistconf path independently
    _distconf_path = resolve_library_path("libdistconf", "LIBDISTCONF_PATH")
    if sys.platform == "darwin" and not _distconf_path:
        _distconf_path = _dylib_path


    # Check if environment is already aligned or we need to relaunch
    has_venv = sys.prefix == str(_venv_dir) if _venv_dir.exists() else True
    has_env = (os.environ.get("LIBUNILOG_PATH") == _dylib_path) and (
        _distconf_path is None or os.environ.get("LIBDISTCONF_PATH") == _distconf_path
    )
    
    if not (has_venv and has_env):
        # Align environment and relaunch
        os.environ["LIBUNILOG_PATH"] = _dylib_path
        if _distconf_path:
            os.environ["LIBDISTCONF_PATH"] = _distconf_path
        os.environ["GODEBUG"] = "cgocheck=0"
        os.environ.pop("PYTHONPATH", None)
        
        python_bin = _venv_python if os.path.exists(_venv_python) else sys.executable
        try:
            os.execve(python_bin, [python_bin] + sys.argv, os.environ)
        except Exception as e:
            raise RuntimeError(f"Failed to relaunch process with aligned environment: {e}") from e
            
    # If we reach here, we are running in the aligned process!
    prepend_venv_bin(_venv_parent)
    ensure_import_paths(script_dir, vault_root)
    
    # Add virtualenv site-packages to sys.path
    _site_packages = _venv_dir / ("Lib/site-packages" if os.name == "nt" else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    if _site_packages.exists() and str(_site_packages) not in sys.path:
        sys.path.insert(0, str(_site_packages))
        
    redirect_working_directory(script_dir)
    
    from .lib_loader import load_libdistconf
    load_libdistconf()
    
    from microservice_toolbox.config.loader import load_config
    from microservice_toolbox.logger import UniLog
    
    config = load_config(config_profile, input_args=[])
    if not config:
        raise RuntimeError("Failed to load configuration.")
        
    config_handle = getattr(config, "_handle", 0) or 0
    
    if not logger_profile:
        if os.environ.get("DOCKER_ENV") == "true" or os.environ.get("CONTAINER") == "true":
            logger_profile = os.environ.get("LOGGER_PROFILE", "cloud")
        else:
            logger_profile = os.environ.get("LOGGER_PROFILE", "standard")
        
    logger = UniLog(
        app_name=app_name,
        config_profile=config_profile,
        logger_profile=logger_profile,
        log_level=log_level,
        config_handle=config_handle
    )
    
    config.set_logger(logger)
    return config, logger
