from argparse import ArgumentParser as argparseArgumentParser
from collections import namedtuple
from os import environ as osEnviron
from os.path import exists as osPathExists

CLIArgs = namedtuple('CLIArgs', ['name', 'host', 'port', 'grpc_host', 'grpc_port', 'conf', 'log_level', 'extras'])

def parse_cli_args(specific_args=None, input_args=None):
    """
    Parses standard and specific command line arguments.
    Standard: --name, --host, --port, --grpc_host, --grpc_port, --conf, --log_level

    Security & Reliability (Docker Guard):
    If DOCKER_ENV=true, settings for --host, --port, --grpc_host, and --grpc_port
    are strictly IGNORED. This prevents brittle hardcoded overrides from breaking
    internal network-aware resolution in dynamic container environments.
    """
    parser = argparseArgumentParser(description="Microservice Toolbox CLI Parser")

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

    # If input_args provided (usually for tests), use them. Else argparse uses sys.argv
    args = parser.parse_args(input_args)

    extras = {}
    for arg in specific_args or []:
        clean_arg = arg.replace("--", "")
        extras[clean_arg] = getattr(args, clean_arg)

    # Map standard flags
    name = args.name
    conf = args.conf
    log_level = args.log_level

    # Docker Guard for network flags
    is_docker = osPathExists('/.dockerenv') or osEnviron.get('DOCKER_ENV') == 'true'
    if is_docker:
        if args.host or args.port or args.grpc_host or args.grpc_port:
            print("Toolbox (Python): Running in Docker. "
                  "Ignoring CLI network overrides to preserve network-aware resolution.")
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
