"""Small test registry placeholder.

Tool handlers are explicitly registered; arbitrary module names, paths, or
commands supplied by a model are never executed.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
