import functools
import socket


@functools.lru_cache(maxsize=1)
def get_hostname():
    """Get system hostname (cached)"""
    try:
        return socket.gethostname()
    except Exception:
        return "localhost"
