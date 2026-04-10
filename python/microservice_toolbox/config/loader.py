import yaml
import os
from .args import parse_cli_args

class AppConfig:
    def __init__(self, profile, specific_flags=None):
        self.profile = profile
        self.data = {}
        self.cli_args = parse_cli_args(specific_flags)
        
        # Priority Logic:
        # 1. Base (Env - very simple placeholder for now as we don't have python-dist-config yet)
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
            
        # If host/port provided and not blocked by Docker Guard
        if self.cli_args.host or self.cli_args.port:
            target = self.cli_args.name or "config_server"
            self.data['capabilities'] = self.data.get('capabilities', {})
            cap = self.data['capabilities'].get(target, {})
            
            if self.cli_args.host:
                cap['ip'] = self.cli_args.host
            if self.cli_args.port:
                cap['port'] = str(self.cli_args.port)
                
            self.data['capabilities'][target] = cap

    @staticmethod
    def deep_merge(dst, src):
        for key, value in src.items():
            if isinstance(value, dict) and key in dst and isinstance(dst[key], dict):
                AppConfig.deep_merge(dst[key], value)
            else:
                dst[key] = value

    def get_capability_addr(self, name):
        caps = self.data.get('capabilities', {})
        cap = caps.get(name, {})
        ip = cap.get('ip', '127.0.0.1')
        port = cap.get('port', '80')
        return f"{ip}:{port}"
