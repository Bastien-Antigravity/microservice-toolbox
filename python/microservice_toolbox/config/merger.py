#!/usr/bin/env python
# coding:utf-8
"""
MERGER UTILITY:
Provides deep merging capabilities for configuration dictionaries.
Ensures nested structures are correctly overlaid following the 'Hierarchy of Truth'.
"""

from typing import Any, Dict


def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """
    Recursive deep merge of src into dst.
    - If keys match and both values are dicts, it recurses.
    - Otherwise, src value overwrites dst value.
    """
    for key, value in src.items():
        if isinstance(value, dict) and key in dst and isinstance(dst[key], dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value
