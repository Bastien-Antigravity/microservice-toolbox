import argparse
import os
import sys
from collections import namedtuple

CLIArgs = namedtuple('CLIArgs', ['name', 'host', 'port', 'grpc_host', 'grpc_port', 'conf', 'log_level', 'extras'])

def parse_cli_args(specific_args=None):
    """
    Parses standard and specific command line arguments.
    Standard: --name, --host, --port, --grpc_host, --grpc_port, --conf, --log_level
    """
    parser = argparse.ArgumentParser(description="Microservice Toolbox CLI Parser")
    
    # Standard arguments
    parser.add_argument("--name", type=str, help="Service name")
    parser.add_argument("--host", type=str, help="Binding host IP")
    parser.add_argument("--port", type=int, help="Binding port")
    parser.add_argument("--grpc_host", type=str, help="GRPC Binding host IP")
    parser.add_argument("--grpc_port", type=int, help="GRPC Binding port")
    parser.add_argument("--conf", type=str, help="Path to configuration file")
    parser.add_argument("--log_level", type=str, help="Logging level (DEBUG, INFO, etc.)")
    
    # Specific arguments
    if specific_args:
        for arg in specific_args:
            clean_arg = arg.replace("--", "")
            parser.add_argument(f"--{clean_arg}", type=str, help=f"Specific argument: {clean_arg}")
            
    args = parser.parse_args()
    
    extras = {}
    for arg in specific_args or []:
        clean_arg = arg.replace("--", "")
        extras[clean_arg] = getattr(args, clean_arg)

    # Map standard flags
    name = args.name
    conf = args.conf
    log_level = args.log_level
    
    # Docker Guard for network flags
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
    if is_docker:
        if args.host or args.port or args.grpc_host or args.grpc_port:
            print("Toolbox (Python): Running in Docker. Ignoring CLI network overrides to preserve network-aware resolution.")
        host = None
        port = None
        grpc_host = None
        grpc_port = None
    else:
        host = args.host
        port = args.port
        grpc_host = args.grpc_host
        grpc_port = args.grpc_port

    return CLIArgs(
        name=name,
        host=host,
        port=port,
        grpc_host=grpc_host,
        grpc_port=grpc_port,
        conf=conf,
        log_level=log_level,
        extras=extras
    )
