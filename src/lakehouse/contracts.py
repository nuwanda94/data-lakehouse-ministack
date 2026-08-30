"""Load zone contracts from configs/contracts/.

Contracts are JSON documents checked into the repo so producers, tests, and
docs share one field list. This module does not validate live objects; it
exposes the documents for tests and future schema-evolution CI.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

CONTRACT_NAMES = ("bronze", "silver", "gold", "quality", "pipeline_run")


def contracts_dir() -> Path:
    """Return configs/contracts/, walking up from this file or cwd."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "configs" / "contracts"
        if candidate.is_dir():
            return candidate
    cwd = Path.cwd() / "configs" / "contracts"
    if cwd.is_dir():
        return cwd
    raise FileNotFoundError("configs/contracts/ not found from package or cwd")


@cache
def load_contract(name: str) -> dict[str, Any]:
    path = contracts_dir() / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing contract: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_contracts() -> dict[str, dict[str, Any]]:
    return {name: load_contract(name) for name in CONTRACT_NAMES}


def contract_field_names(name: str) -> list[str]:
    spec = load_contract(name)
    fields = spec.get("fields") or []
    return [str(item["name"]) for item in fields if "name" in item]
