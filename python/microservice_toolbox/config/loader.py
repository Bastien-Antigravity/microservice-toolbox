import yaml
import os
from .args import parse_cli_args

def load_config(profile, specific_flags=None):
    """Semantic helper to match Go LoadConfig()"""
    return AppConfig(profile, specific_flags)

class AppConfig:
    def __init__(self, profile, specific_flags=None):
        self.profile = profile
        self.data = {}
        self.cli_args = parse_cli_args(specific_flags)
        
        # Phase 1: Load base config from file (full merge of all sections)
        filename = f"{profile}.yaml"
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Toolbox (Python): Config file '{filename}' not found for profile '{profile}'")
        self._load_from_file(filename)

        # Phase 2: Layered logic matching Go implementation
        is_dev = profile in ["standalone", "test"]
        if is_dev:
            print(f"Toolbox (Python): Dev Mode detected. Re-applying Local File as Hard Override.")
            self._apply_file_override(filename)
        else:
            print(f"Toolbox (Python): Production Mode detected. Config Server remains authoritative.")

        # Phase 3: CLI Overrides (Highest)
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
