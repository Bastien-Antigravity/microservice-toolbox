import os
import socket


class Resolver:
    """
    Resolver handles environment-aware network address translation.
    """
    def __init__(self):
        # Detect Docker environment
        self.is_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_ENV') == 'true'

    def resolve_bind_addr(self, requested_ip: str) -> str:
        """
        Resolves the requested IP into an actual address to bind to.

        Docker Connectivity Logic:
        If running in a Docker container and a loopback address (127.0.0.1) is
        provided, this method translates it to the container's internal
        primary interface IP. This ensures that the service is actually
        reachable by other containers in the same network/fleet.
        """
        requested_ip = requested_ip.strip('"')

        # If not in Docker, or if the IP isn't a loopback placeholder, use it directly.
        if not self.is_docker or not self.is_loopback(requested_ip):
            return requested_ip

        # In Docker, we need the internal container IP (e.g., eth0) for other containers to reach us.
        try:
            return self._get_primary_interface_ip()
        except Exception as e:
            # Fallback or re-raise depending on criticality. Matching Go's error handling.
            raise RuntimeError(f"failed to resolve container IP for bind: {e}")

    def is_loopback(self, ip: str) -> bool:
        """
        Checks if the IP is a loopback address.
        """
        return ip.startswith('127.') or ip == '::1' or ip.lower() == 'localhost'

    def _get_primary_interface_ip(self) -> str:
        """
        Finds the first non-loopback IP address using a UDP socket trick.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            if ip and not self._is_loopback(ip):
                return ip
        except Exception:
            pass
        finally:
            s.close()

        # Fallback to hostname resolution
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            raise RuntimeError("no primary network interface found")

def new_resolver() -> Resolver:
    return Resolver()
