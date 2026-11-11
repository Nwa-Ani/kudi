"""Read environment variables, including split NAME_P0, NAME_P1, ... parts."""

from __future__ import annotations

import os


def read_env(name: str) -> str:
    """Read an env var. If NAME_P0, NAME_P1, ... are set, concatenate those instead.

    Some hosts cap a single environment value at a very short length. Split
    parts let the full value be provided without printing it.
    """
    if os.environ.get(f"{name}_P0") is not None:
        parts: list[str] = []
        index = 0
        while f"{name}_P{index}" in os.environ:
            parts.append(os.environ.get(f"{name}_P{index}") or "")
            index += 1
        return "".join(parts).strip()
    return (os.environ.get(name) or "").strip()
