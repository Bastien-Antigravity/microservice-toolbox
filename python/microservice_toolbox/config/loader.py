import os
from typing import Optional

import yaml

from ..utils.logger import ILogger, ensure_safe_logger
from .args import parse_cli_args


def load_config(profile: str, specific_flags: Optional[list] = None, input_args: Optional[list] = None) -> 'AppConfig':
    """
    Initializes a configuration loader following the Microservice Toolbox 'Hierarchy of Truth'.
    
    Priority levels (highest to lowest):
    1. CLI Overrides (e.g., --host, --port)
    2. Context-Aware File Overrides (Dev Mode Hard Overrides)
    3. Production/Fleet Source (Config Server or YAML)
    4. Base environment/defaults
    """
    return AppConfig(profile, specific_flags, input_args=input_args)

def load_config_with_logger(profile: str, logger: Optional[ILogger], specific_flags: Optional[list] = None) -> 'AppConfig':
    """Semantic helper to match Go LoadConfigWithLogger()."""
    return AppConfig(profile, specific_flags, logger=logger)

class AppConfig:
    """
    AppConfig wraps configuration data and provides layered resolution logic.
    It ensures that service settings remain consistent whether running in 
    standalone development mode or across a containerized production fleet.
    """
    def __init__(self, profile: str, specific_flags: Optional[list] = None, logger: Optional[ILogger] = None, input_args: Optional[list] = None):
        self.profile = profile
        self.data = {}
        self.logger = ensure_safe_logger(logger)
        self.cli_args = parse_cli_args(specific_flags, input_args=input_args)

        # ---------------------------------------------------------------------
        # PHASE 1: Load base configuration from YAML
        # ---------------------------------------------------------------------
        filename = f"{profile}.yaml"
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Toolbox (Python): Config file '{filename}' not found for profile '{profile}'")
        self._load_from_file(filename)

        # ---------------------------------------------------------------------
        # PHASE 2: Apply context-aware overrides
        # In standalone/test modes, we ensure the local file is authoritative 
        # over any previous merges (matching Go behavior).
        # ---------------------------------------------------------------------
        is_dev = profile in ["standalone", "test"]
        if is_dev:
            self.logger.info("Dev Mode detected. Re-applying Local File as Hard Override.")
            self._apply_file_override(filename)
        else:
            self.logger.info("Production Mode detected. Configuration state remains stable.")

        # ---------------------------------------------------------------------
        # PHASE 3: Apply CLI Overrides (The absolute Highest Priority)
        # ---------------------------------------------------------------------
        self._apply_cli_overrides()


    def _load_from_file(self, filename):
        """Full merge of all file data into self.data"""
        with open(filename, 'r') as f:
            file_data = yaml.safe_load(f)
            if file_data:
                self.deep_merge(self.data, file_data)

    def _apply_file_override(self, filename):
        """Re-reads file and merges ONLY capabilities as hard override (matches Go applyFileOverride)"""
        with open(filename, 'r') as f:
            file_data = yaml.safe_load(f)
            if file_data and 'capabilities' in file_data:
                self.data['capabilities'] = self.data.get('capabilities', {})
                self.deep_merge(self.data['capabilities'], file_data['capabilities'])


    def _apply_cli_overrides(self):
        if self.cli_args.name:
            self.data['common'] = self.data.get('common', {})
            self.data['common']['name'] = self.cli_args.name

        # If network flags provided and not blocked by Docker Guard
        if any([self.cli_args.host, self.cli_args.port, self.cli_args.grpc_host, self.cli_args.grpc_port]):
            target = self.cli_args.name or self.data.get('common', {}).get('name') or "config_server"
            self.data['capabilities'] = self.data.get('capabilities', {})
            cap = self.data['capabilities'].get(target, {})

            if self.cli_args.host:
                cap['ip'] = self.cli_args.host
            if self.cli_args.port:
                cap['port'] = str(self.cli_args.port)
            if self.cli_args.grpc_host:
                cap['grpc_ip'] = self.cli_args.grpc_host
            if self.cli_args.grpc_port:
                cap['grpc_port'] = str(self.cli_args.grpc_port)

            self.data['capabilities'][target] = cap

    @staticmethod
    def deep_merge(dst, src):
        for key, value in src.items():
            if isinstance(value, dict) and key in dst and isinstance(dst[key], dict):
                AppConfig.deep_merge(dst[key], value)
            else:
                dst[key] = value

    def get_listen_addr(self, capability):
        return self._get_addr(capability, 'ip', 'port')

    def get_grpc_listen_addr(self, capability):
        caps = self.data.get('capabilities', {})
        cap = caps.get(capability)

        if not cap:
            raise ValueError(f"capability {capability} not found for gRPC fallback")

        # 1. Try explicit grpc config
        grpc_ip = cap.get('grpc_ip')
        grpc_port = cap.get('grpc_port')

        if grpc_ip and grpc_port:
            return f"{grpc_ip}:{grpc_port}"

        # 2. Fallback to convention: ip:port+1 (matching Go implementation)
        ip = cap.get('ip', '0.0.0.0')
        port_str = cap.get('port', '8080')
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            port = 8080

        return f"{ip}:{port + 1}"

    def _get_addr(self, capability, host_key, port_key):
        caps = self.data.get('capabilities', {})
        cap = caps.get(capability)
        if not cap:
            raise ValueError(f"capability {capability} not found")

        host = cap.get(host_key, '0.0.0.0')
        port = cap.get(port_key)
        if not port:
            raise ValueError(f"port key {port_key} missing or empty in capability {capability}")

        return f"{host}:{port}"
