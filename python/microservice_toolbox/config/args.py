import argparse
import os
import sys

def parse_cli_args(specific_args=None):
    """
    Parses standard and specific command line arguments.
    Standard: --name, --host, --port, --conf, --log_level
    """
    parser = argparse.ArgumentParser(description="Microservice Toolbox CLI Parser")
    
    # Standard arguments
    parser.add_argument("--name", type=str, help="Service name")
    parser.add_argument("--host", type=str, help="Binding host IP")
    parser.add_argument("--port", type=int, help="Binding port")
    parser.add_argument("--conf", type=str, help="Path to configuration file")
    parser.add_argument("--log_level", type=str, help="Logging level (DEBUG, INFO, etc.)")
    
    # Specific arguments
    if specific_args:
        for arg in specific_args:
            # Clean dashes if provided
            clean_arg = arg.replace("--", "")
            parser.add_argument(f"--{clean_arg}", type=str, help=f"Specific argument: {clean_arg}")
            
    args = parser.parse_args()
    
    # Docker Guard: Detect Docker environment
    is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_ENV") == "true"
    
    if is_docker:
        if args.host or args.port:
            print("Toolbox (Python): Running in Docker. Ignoring CLI overrides for --host and --port to preserve network-aware resolution.")
        args.host = None
        args.port = None
        
    return args
