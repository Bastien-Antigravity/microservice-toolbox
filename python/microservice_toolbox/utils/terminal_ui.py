import datetime

from .helpers import get_hostname


def print_internal_log(level, module, filename, line, message):
    """Formats and prints an internal toolbox log message"""
    # Precision timestamp in ISO 8601 format
    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "000Z"
    hostname = get_hostname()

    # Colorize level
    colors = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "LOGON": "\033[32m",
        "LOGOUT": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[31m",
    }
    color = colors.get(level, "")
    colored_level = f"{color}{truncate(level, 10):<10}\033[0m"

    # Fixed column format: 33-12-15-10-20-25-6 message
    print(
        f"{timestamp:<33} "
        f"{truncate(hostname, 12):<12} "
        f"{truncate('microservice-toolbox', 15):<15} "
        f"{colored_level} "
        f"{truncate(filename, 20):<20} "
        f"{truncate(module, 25):<25} "
        f"{truncate(line, 6):<6} "
        f"{message}"
    )

def truncate(s, max_len):
    return s[:max_len] if len(s) > max_len else s
