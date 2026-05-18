#!/usr/bin/env python
# coding:utf-8

import sys
import os
from microservice_toolbox.config.loader import load_config

def main():
    if len(sys.argv) < 3:
        print("Usage: expansion_check.py <profile> <key>")
        sys.exit(1)

    profile = sys.argv[1]
    key = sys.argv[2]

    try:
        ac = load_config(profile, input_args=[])
        val = ac.get_local(key)
        sys.stdout.write(f"VALUE:{val}")
    except Exception as e:
        # Fallback for when profile yaml doesn't exist but we might want to check something else
        sys.stdout.write(f"VALUE:ERROR_{e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
