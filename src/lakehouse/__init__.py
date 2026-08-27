"""Medallion lakehouse package for the MiniStack local stack.

Public surface is intentionally small. Import from `lakehouse` rather than
reaching into implementation modules from scripts or tests.
"""

from lakehouse.config import Settings, load_settings

__all__ = [
    "Settings",
    "load_settings",
    "__version__",
]

__version__ = "0.1.0"
