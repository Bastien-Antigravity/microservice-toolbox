#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides deep merging capabilities for configuration dictionaries.
Ensures nested structures are correctly overlaid following the 'Hierarchy of Truth'.

DATA FLOW:
1. Receives a destination and source dictionary.
2. Recursively traverses nested keys.
3. Overwrites leaf values while preserving non-conflicting structure.

KEY PARAMETERS:
- dst: The dictionary to be updated.
- src: The source dictionary containing override values.
"""

from typing import Any, Dict

# -----------------------------------------------------------------------------------------------


def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """
    Recursive deep merge of src into dst.
    - If keys match and both values are dicts, it recurses.
    - Otherwise, src value overwrites dst value.
    """
    if dst is None:
        return
    for key, value in src.items():
        if isinstance(value, dict) and key in dst and isinstance(dst[key], dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value
