"""Load and check zone contracts from configs/contracts/.

Contracts are JSON documents checked into the repo so producers, tests, and
docs share one field list. This module:

* loads the documents
* validates each document's own shape
* checks in-repo producers (models, seed enums, quality checks) against them
* diffs two contract versions so CI can fail a breaking schema change
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

CONTRACT_NAMES = ("bronze", "silver", "gold", "quality", "pipeline_run")

ALLOWED_FIELD_TYPES = frozenset(
    {
        "string",
        "integer",
        "number",
        "boolean",
        "datetime",
        "date",
        "json-string",
        "object",
    }
)

_TYPE_WIDENS_TO: dict[str, frozenset[str]] = {
    "integer": frozenset({"number"}),
    "date": frozenset({"datetime", "string"}),
    "datetime": frozenset({"string"}),
    "boolean": frozenset({"string"}),
}


@dataclass(frozen=True)
class ContractIssue:
    """One validation finding against a contract document or a producer."""

    severity: str
    contract: str
    code: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaDiff:
    """Result of comparing an older contract document to a newer one."""

    contract: str
    breaking: list[str] = field(default_factory=list)
    additive: list[str] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return not self.breaking

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "compatible": self.compatible,
            "breaking": list(self.breaking),
            "additive": list(self.additive),
        }


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
    return _field_names(spec)


def _field_items(spec: dict[str, Any]) -> list[dict[str, Any]]:
    fields = spec.get("fields") or []
    return [item for item in fields if isinstance(item, dict) and "name" in item]


def _field_names(spec: dict[str, Any]) -> list[str]:
    return [str(item["name"]) for item in _field_items(spec)]


def _field_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]): item for item in _field_items(spec)]
