class ConnectionManagerError(Exception):
    """Base class for connection manager errors."""
    pass

class ConnectionRefusedError(ConnectionManagerError):
    """Raised when the target address actively rejects the connection."""
    pass

class MaxRetriesReachedError(ConnectionManagerError):
    """Raised when the network manager gives up after the configured number of attempts."""
    pass

class NoConnectionError(ConnectionManagerError):
    """Raised when an operation is attempted on a nil or closed connection."""
    pass

class WriteFailedError(ConnectionManagerError):
    """Raised when data could not be sent over the socket."""
    pass
