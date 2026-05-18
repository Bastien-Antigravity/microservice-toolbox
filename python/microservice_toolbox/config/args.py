#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Parses command-line arguments and environment variables for microservice initialization.
Provides a standardized set of CLI flags (name, host, port, profile, etc.) used across the fleet.

DATA FLOW:
1. Receives sys.argv or explicit test arguments.
2. Detects environment context (e.g., Docker Guard).
3. Returns a structured CLIArgs namedtuple.

KEY PARAMETERS:
- specific_args: Optional list of additional flags to register.
- input_args: Explicit list of arguments (for testing).
"""

from argparse import ArgumentParser as argparseArgumentParser
from collections import namedtuple
from os import environ as osEnviron
from os.path import exists as osPathExists
from typing import List, Optional

# -----------------------------------------------------------------------------------------------

CLIArgs = namedtuple("CLIArgs", ["name", "host", "port", "grpc_host", "grpc_port", "conf", "log_level", "key", "profile", "extras"])

# -----------------------------------------------------------------------------------------------


def parse_cli_args(specific_args: Optional[List[str]] = None, input_args: Optional[List[str]] = None) -> CLIArgs:
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
    parser.add_argument("--key", type=str, help="Path to RSA Public/Private key")
    parser.add_argument("--profile", "-p", type=str, help="Configuration profile (e.g. standalone, production)")

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
    key = args.key

    # If key provided, set it as ENV override for the decryption engine
    if key:
        osEnviron["BASTIEN_PRIVATE_KEY_PATH"] = key

    # Docker Guard for network flags
    is_docker = osPathExists("/.dockerenv") or osEnviron.get("DOCKER_ENV") == "true"
    if is_docker:
        if args.host or args.port or args.grpc_host or args.grpc_port:
            print(
                "Toolbox (Python): Running in Docker. "
                "Ignoring CLI network overrides to preserve network-aware resolution."
            )
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
        key=key,
        profile=args.profile,
        extras=extras,
    )
