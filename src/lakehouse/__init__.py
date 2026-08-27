"""Medallion lakehouse ministack — local AWS (MiniStack) pipeline package.

Public layout
-------------
lakehouse.config     settings loaded from environment / .env
lakehouse.aws        shared boto3 session + resource factories
lakehouse.models     typed records that cross zone boundaries
lakehouse.seed       synthetic event generation + bronze landing
lakehouse.pipeline   bronze → silver → gold transforms and quality gates
lakehouse.cli        `lakehouse` console entry point
"""

from lakehouse.config import Settings, get_settings

__version__ = "0.1.0"
__all__ = [
    "Settings",
    "get_settings",
    "__version__",
]
