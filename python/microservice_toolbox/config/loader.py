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
        
        # Priority Logic:
        # 1. Base (Env)
        self._load_from_env()
        
        # 2. Server (Placeholder)
        self._load_from_server()
        
        # 3. Local File (Layered based on Profile)
        is_dev = profile in ["standalone", "test"]
        if is_dev:
            print(f"Toolbox (Python): Dev Mode. File > Server.")
            self._load_from_file(f"{profile}.yaml")
        else:
            print(f"Toolbox (Python): Production Mode. Server > File.")
            self._load_from_file(f"{profile}.yaml", hard_override=False)

        # 4. CLI Overrides (Highest)
        self._apply_cli_overrides()

    def _load_from_env(self):
        # Base defaults from ENV if needed
        pass

    def _load_from_server(self):
        # Future: Sync with Config Server
        pass

    def _load_from_file(self, filename, hard_override=True):
        if not os.path.exists(filename):
            return
            
        with open(filename, 'r') as f:
            file_data = yaml.safe_load(f)
            if file_data:
                if hard_override:
                    self.deep_merge(self.data, file_data)
                else:
                    # In production, file only fills gaps (Server wins)
                    temp = file_data.copy()
                    self.deep_merge(temp, self.data)
                    self.data = temp

    def _apply_cli_overrides(self):
        if self.cli_args.name:
            self.data['common'] = self.data.get('common', {})
            self.data['common']['name'] = self.cli_args.name
            
        # If network flags provided and not blocked by Docker Guard
        if any([self.cli_args.host, self.cli_args.port, self.cli_args.grpc_host, self.cli_args.grpc_port]):
            target = self.cli_args.name or "config_server"
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

    def get_listen_addr(self, name):
        return self._get_addr(name, 'ip', 'port')

    def get_grpc_listen_addr(self, name):
        caps = self.data.get('capabilities', {})
        cap = caps.get(name, {})
        
        # 1. Try explicit grpc config
        grpc_ip = cap.get('grpc_ip')
        grpc_port = cap.get('grpc_port')
        
        if grpc_ip and grpc_port:
            return f"{grpc_ip}:{grpc_port}"
            
        # 2. Fallback to convention: ip:port+1
        ip = cap.get('ip', '127.0.0.1')
        port = cap.get('port', '80')
        try:
            grpc_port = int(port) + 1
        except (ValueError, TypeError):
            grpc_port = 81
            
        return f"{ip}:{grpc_port}"

    def _get_addr(self, name, host_key, port_key):
        caps = self.data.get('capabilities', {})
        cap = caps.get(name, {})
        ip = cap.get(host_key, '127.0.0.1')
        port = cap.get(port_key, '80')
        return f"{ip}:{port}"
