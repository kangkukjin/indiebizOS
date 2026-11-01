"""Reuse YAML parsing by exact text, never by a path or a file timestamp.

Callers still read their file on every observation. Each result is a deep copy:
body filtering and caller mutations cannot alter a later reader's document.
Only syntax decoding is shared; validation, identity and permissions are not.
"""
import copy
from functools import lru_cache

import yaml


# Bound retained sources and parsed trees; oversized documents still parse.
_MAX_SOURCE_CHARS = 1_000_000


@lru_cache(maxsize=32)
def _parsed(source):
    return yaml.safe_load(source)


def load_yaml(source: str):
    """Decode current file text with SafeLoader and return caller-owned values."""
    if len(source) > _MAX_SOURCE_CHARS:
        return yaml.safe_load(source)
    return copy.deepcopy(_parsed(source))
