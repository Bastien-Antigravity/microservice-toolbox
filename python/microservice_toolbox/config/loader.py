#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Initializes a configuration loader following the Microservice Toolbox 'Hierarchy of Truth'.
Ensures service settings remain consistent across standalone and production fleets.

DATA FLOW:
1. Load base configuration from YAML profile.
2. Apply context-aware overrides (standalone/test modes).
3. Merge CLI overrides (highest priority).

KEY PARAMETERS:
- profile: The active configuration profile (e.g., standalone, production).
- specific_flags: Optional list of CLI flags to parse.
"""

from json import dumps as jsonDumps
from json import loads as jsonLoads
from os import getenv as osGetenv
from os.path import exists as osPathExists
from typing import Any, Callable, Dict, List, Optional

from yaml import safe_load as yamlSafe_load

from ..utils.logger import ILogger, ensure_safe_logger
from .args import parse_cli_args
from .lib_loader import CALLBACK_TYPE, lib
from .merger import deep_merge

# -----------------------------------------------------------------------------------------------




def load_config(
    profile: str, specific_flags: Optional[List[str]] = None, input_args: Optional[List[str]] = None
) -> "AppConfig":
    """Semantic helper to match Go LoadConfig()."""
    return AppConfig(profile, specific_flags, input_args=input_args)


# -----------------------------------------------------------------------------------------------


def load_config_with_logger(
    profile: str, logger: Optional[ILogger], specific_flags: Optional[List[str]] = None
) -> "AppConfig":
    """Semantic helper to match Go LoadConfigWithLogger()."""
    return AppConfig(profile, specific_flags, logger=logger)


# -----------------------------------------------------------------------------------------------


class AppConfig:
    """
    AppConfig wraps configuration data and provides layered resolution logic.
    It ensures that service settings remain consistent whether running in
    standalone development mode or across a containerized production fleet.
    """

    Name = "AppConfig"

    # -----------------------------------------------------------------------------------------------

    def __init__(
        self,
        profile: str,
        specific_flags: Optional[List[str]] = None,
        logger: Optional[ILogger] = None,
        input_args: Optional[List[str]] = None,
    ):
        self.profile = profile
        self.data: Dict[str, Any] = {}
        self.logger = ensure_safe_logger(logger)
        self.cli_args = parse_cli_args(specific_flags, input_args=input_args)
        filename = f"{profile}.yaml"

        # ---------------------------------------------------------------------
        # BRIDGE INITIALIZATION (v1.9.8 Standard)
        # ---------------------------------------------------------------------
        self._handle = None
        self._callback_refs = {} # Keep references to avoid GC

        if lib:
            try:
                self._handle = lib.DistConf_New(profile.encode('utf-8'))
                if self._handle:
                    self.logger.info("{0} : libdistconf session initialized (handle: {1})".format(self.Name, self._handle))
                    # Sync local data with bridge state
                    self._sync_from_bridge()
            except Exception as e:
                self.logger.warning("{0} : libdistconf initialization failed: {1}. Falling back to native.".format(self.Name, e))

        # ---------------------------------------------------------------------
        # PHASE 1: Load base configuration from YAML (Native Fallback)
        # ---------------------------------------------------------------------
        if not self._handle:
            if not osPathExists(filename):
                # Try fallback to config/ folder
                filename = f"config/{profile}.yaml"
                if not osPathExists(filename):
                    raise FileNotFoundError(f"Toolbox (Python): Config file not found for profile '{profile}' (Checked {profile}.yaml and config/{profile}.yaml)")
            self._load_from_file(filename)

        # ---------------------------------------------------------------------
        # PHASE 2: Apply context-aware overrides
        # In standalone/test modes, we ensure the local file is authoritative
        # over any previous merges (matching Go behavior).
        # ---------------------------------------------------------------------
        is_dev = profile in ["standalone", "test"]
        if is_dev:
            self.logger.info("{0} : Dev Mode detected. Re-applying Local File as Hard Override.".format(self.Name))
            self._apply_file_override(filename)
        else:
            self.logger.info("{0} : Production Mode detected. Configuration state remains stable.".format(self.Name))

        # ---------------------------------------------------------------------
        # PHASE 3: Apply CLI Overrides (The absolute Highest Priority)
        # ---------------------------------------------------------------------
        self._apply_cli_overrides()

        # If --key flag provided, set it as ENV override for the Private Key (decryption engine)
        if self.cli_args.key:
            from os import environ as os_environ
            os_environ["BASTIEN_PRIVATE_KEY_PATH"] = self.cli_args.key

        # ---------------------------------------------------------------------
        # PHASE 4: Load Public Key
        # ---------------------------------------------------------------------
        self._load_public_key()

    # -----------------------------------------------------------------------------------------------

    def _load_public_key(self) -> None:
        """Finds and loads public.pem into self.data['common']['public_key']."""
        path = osGetenv("BASTIEN_PUBLIC_KEY_PATH")
        if not path:
            path = "/etc/bastien/public.pem"
            if not osPathExists(path):
                if osPathExists("./public.pem"):
                    path = "./public.pem"
                else:
                    return

        try:
            if osPathExists(path):
                with open(path, "r") as f:
                    self.data["common"] = self.data.get("common", {})
                    self.data["common"]["public_key"] = f.read().strip()
                    self.logger.info(f"{self.Name} : Public Key Loaded from {path}")
        except Exception as e:
            self.logger.warning(f"{self.Name} : Failed to load public key from {path}: {e}")

    @property
    def common(self) -> Dict[str, Any]:
        """Provides direct access to the 'common' configuration block."""
        return self.data.get("common", {})

    # -----------------------------------------------------------------------------------------------

    def decrypt_secret(self, ciphertext: str) -> str:
        """
        Explicitly decrypts a single ENC(...) ciphertext string.
        Uses the hardened distributed-config engine to ensure cross-language consistency.
        Raises ValueError if decryption fails for an ENC(...) block.
        """
        if not isinstance(ciphertext, str) or not ciphertext.startswith("ENC(") or not ciphertext.endswith(")"):
            return ciphertext

        if self._handle:
            try:
                res = lib.DistConf_Decrypt(self._handle, ciphertext.encode('utf-8'))
                if res:
                    val = res.decode('utf-8')
                    return val
                else:
                    # Fetch raw error from bridge
                    err = lib.DistConf_GetLastError()
                    msg = err.decode('utf-8') if err else "Unknown decryption error"
                    raise ValueError(msg)
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                self.logger.error(f"{self.Name} : Decryption failed via bridge: {e}")

        # If we reach here, it's an ENC(...) block but we couldn't decrypt it
        # (either bridge failed or bridge is missing). Original behavior was to raise ValueError.
        raise ValueError(f"{self.Name} : Decryption not available or failed for ENC block")

    # -----------------------------------------------------------------------------------------------

    def _load_from_file(self, filename: str) -> None:
        """Full merge of all file data into self.data"""
        file_data = self._read_and_expand_yaml(filename)
        if file_data:
            self.deep_merge(self.data, file_data)

    # -----------------------------------------------------------------------------------------------

    def _apply_file_override(self, filename: str) -> None:
        """Re-reads file and merges ONLY capabilities as hard override (matches Go applyFileOverride)"""
        file_data = self._read_and_expand_yaml(filename)
        if file_data:
            if "capabilities" in file_data:
                self.data["capabilities"] = self.data.get("capabilities", {})
                self.deep_merge(self.data["capabilities"], file_data["capabilities"])
            if "local" in file_data:
                self.data["local"] = self.data.get("local", {})
                self.deep_merge(self.data["local"], file_data["local"])

    def _read_and_expand_yaml(self, filename: str) -> Dict[str, Any]:
        """Helper to read YAML file with environment variable expansion."""
        if not osPathExists(filename):
            return {}

        try:
            with open(filename, "r") as f:
                raw_content = f.read()

            # Expand Environment Variables: ${VAR} or ${VAR:default}
            import re
            def env_expander(match):
                token = match.group(1)
                parts = token.split(":", 1)
                var_name = parts[0]
                default_val = parts[1] if len(parts) > 1 else ""
                return osGetenv(var_name, default_val)

            expanded_content = re.sub(r"\${([^}]+)}", env_expander, raw_content)
            return yamlSafe_load(expanded_content) or {}
        except Exception as e:
            self.logger.warning(f"{self.Name} : Failed to load {filename}: {e}")
            return {}

    # -----------------------------------------------------------------------------------------------

    def _apply_cli_overrides(self) -> None:
        if self.cli_args.name:
            self.data["common"] = self.data.get("common", {})
            self.data["common"]["name"] = self.cli_args.name

        # If network flags provided and not blocked by Docker Guard
        if any([self.cli_args.host, self.cli_args.port, self.cli_args.grpc_host, self.cli_args.grpc_port]):
            target = self.cli_args.name or self.data.get("common", {}).get("name") or "config_server"
            self.data["capabilities"] = self.data.get("capabilities", {})
            cap = self.data["capabilities"].get(target, {})

            if self.cli_args.host:
                cap["ip"] = self.cli_args.host
            if self.cli_args.port:
                cap["port"] = str(self.cli_args.port)
            if self.cli_args.grpc_host:
                cap["grpc_ip"] = self.cli_args.grpc_host
            if self.cli_args.grpc_port:
                cap["grpc_port"] = str(self.cli_args.grpc_port)

            self.data["capabilities"][target] = cap

    # -----------------------------------------------------------------------------------------------

    @staticmethod
    def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
        """Wrapper around standalone deep_merge for backward compatibility."""
        deep_merge(dst, src)

    # -----------------------------------------------------------------------------------------------

    def get_listen_addr(self, capability: str) -> str:
        """
        Resolves the listening address for a capability.
        Prioritizes live bridge resolution (Service Discovery) over local snapshots.
        """
        if self._handle:
            try:
                res = lib.DistConf_GetAddress(self._handle, capability.encode('utf-8'))
                if res:
                    return res.decode('utf-8')
            except Exception as e:
                self.logger.warning(f"{self.Name} : Bridge GetAddress failed: {e}")

        return self._get_addr(capability, "ip", "port")

    # -----------------------------------------------------------------------------------------------

    def get_grpc_listen_addr(self, capability: str) -> str:
        """
        Resolves the gRPC listening address for a capability.
        Requires explicit grpc_ip and grpc_port (matching Go GetGRPCAddress behavior).
        """
        if self._handle:
            try:
                res = lib.DistConf_GetGRPCAddress(self._handle, capability.encode('utf-8'))
                if res:
                    return res.decode('utf-8')
            except Exception as e:
                self.logger.warning(f"{self.Name} : Bridge GetGRPCAddress failed: {e}")

        return self._get_addr(capability, "grpc_ip", "grpc_port")

    # -----------------------------------------------------------------------------------------------

    def _get_addr(self, capability: str, host_key: str, port_key: str) -> str:
        caps = self.data.get("capabilities", {})
        cap = caps.get(capability)
        if not cap:
            raise ValueError(f"capability {capability} not found")

        host = cap.get(host_key)
        if not host:
            raise ValueError(f"host key {host_key} missing or empty in capability {capability}")

        port = cap.get(port_key)
        if not port:
            raise ValueError(f"port key {port_key} missing or empty in capability {capability}")

        return f"{host}:{port}"

    # -----------------------------------------------------------------------------------------------

    def _sync_from_bridge(self) -> None:
        """Pulls the full configuration state from the Go bridge into self.data."""
        if not self._handle:
            return

        try:
            full_json = lib.DistConf_GetFullConfig(self._handle)
            if full_json:
                self.data = jsonLoads(full_json.decode('utf-8'))
        except Exception:
            err = lib.DistConf_GetLastError()
            if err:
                self.logger.warning(err.decode('utf-8'))

    # -----------------------------------------------------------------------------------------------

    def get_config(self, section: str, key: str, default: Any = None) -> Any:
        """Retrieves a value from the bridge or local data."""
        if self._handle:
            res = lib.DistConf_Get(self._handle, section.encode('utf-8'), key.encode('utf-8'))
            if res is not None:
                return res.decode('utf-8')

        # Fallback to local data
        sect = self.data.get(section, {})
        return sect.get(key, default)

    # -----------------------------------------------------------------------------------------------

    def get_local(self, key: str) -> Any:
        """
        Returns a value from the 'local' configuration section.
        Supports nested lookups using dot notation (e.g., "database.host").
        """
        local_data = self.data.get("local")
        if local_data is None:
            return None

        parts = key.split(".")
        current = local_data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return None
            else:
                return None
        return current

    # -----------------------------------------------------------------------------------------------

    def unmarshal_local(self, target: Any) -> Any:
        """
        Unmarshals the 'local' configuration section into a target type or instance.
        Parity with Go's UnmarshalLocal.
        """
        local_data = self.data.get("local")
        if not local_data:
            raise ValueError("No local configuration found")

        import json
        raw_json = json.dumps(local_data)
        data = json.loads(raw_json)

        if isinstance(target, type):
            # If target is a class (e.g. a dataclass), instantiate it
            return target(**data)
        else:
            # If target is an existing instance, update its attributes
            for k, v in data.items():
                setattr(target, k, v)
            return target

    # -----------------------------------------------------------------------------------------------

    def set_logger(self, logger: Any) -> None:
        """Updates the logger after instantiation."""
        self.logger = ensure_safe_logger(logger)
        self.logger.info("{0} : Logger updated successfully".format(self.Name))

    # -----------------------------------------------------------------------------------------------

    def on_live_conf_update(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a callback for live configuration updates (Dynamic Fleet Config)."""
        if not self._handle:
            self.logger.warning(f"{self.Name} : Live updates not supported (no bridge)")
            return

        def _bridge_cb(handle: int, json_data: bytes) -> None:
            try:
                data = jsonLoads(json_data.decode('utf-8'))
                callback(data)
                self._sync_from_bridge() # Keep local data in sync
            except Exception as e:
                self.logger.error(f"{self.Name} : Live update callback failed: {e}")

        self._callback_refs["live"] = CALLBACK_TYPE(_bridge_cb)
        lib.DistConf_OnLiveConfUpdate(self._handle, self._callback_refs["live"])

    # -----------------------------------------------------------------------------------------------

    def on_registry_update(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a callback for service registry changes (Service Discovery)."""
        if not self._handle:
            self.logger.warning(f"{self.Name} : Registry updates not supported (no bridge)")
            return

        def _bridge_cb(handle: int, json_data: bytes) -> None:
            try:
                data = jsonLoads(json_data.decode('utf-8'))
                callback(data)
                self._sync_from_bridge()
            except Exception as e:
                self.logger.error(f"{self.Name} : Registry update callback failed: {e}")

        self._callback_refs["registry"] = CALLBACK_TYPE(_bridge_cb)
        lib.DistConf_OnRegistryUpdate(self._handle, self._callback_refs["registry"])

    # -----------------------------------------------------------------------------------------------

    def on_update(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Deprecated: Use on_live_conf_update(). Semantic alias for backward compatibility."""
        self.on_live_conf_update(callback)

    # -----------------------------------------------------------------------------------------------

    def share_config(self, payload: Dict[str, Any]) -> bool:
        """Shares service configuration with the ecosystem."""
        if not self._handle:
            return False
        try:
            return lib.DistConf_ShareConfig(self._handle, jsonDumps(payload).encode('utf-8'))
        except Exception as e:
            self.logger.error(f"{self.Name} : ShareConfig failed: {e}")
            return False

    # -----------------------------------------------------------------------------------------------

    def close(self):
        """Releases the underlying DistConf handle."""
        if hasattr(self, "_handle") and self._handle:
            self._lib.DistConf_Close(self._handle)
            self._handle = None

    def __del__(self):
        self.close()
