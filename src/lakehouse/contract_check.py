"""Producer alignment and schema-evolution checks for zone contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from lakehouse.contracts import CONTRACT_NAMES, load_contract

ALLOWED_FIELD_TYPES = frozenset(
    {"string", "integer", "number", "boolean", "datetime", "date", "json-string", "object"}
)
_TYPE_WIDENS_TO = {
    "integer": frozenset({"number"}),
    "date": frozenset({"datetime", "string"}),
    "datetime": frozenset({"string"}),
    "boolean": frozenset({"string"}),
}


@dataclass(frozen=True)
class ContractIssue:
    severity: str
    contract: str
    code: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaDiff:
    contract: str
    breaking: list[str] = field(default_factory=list)
    additive: list[str] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return not self.breaking


def _items(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in (spec.get("fields") or []) if isinstance(f, dict) and "name" in f]


def _names(spec: dict[str, Any]) -> list[str]:
    return [str(f["name"]) for f in _items(spec)]


def _map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(f["name"]): f for f in _items(spec)}


def validate_contract_document(
    name: str, spec: dict[str, Any] | None = None
) -> list[ContractIssue]:
    spec = spec if spec is not None else load_contract(name)
    issues: list[ContractIssue] = []
    if not spec.get("name"):
        issues.append(ContractIssue("error", name, "missing_name", "missing top-level name"))
    fields = spec.get("fields")
    if name != "quality" and not fields:
        issues.append(ContractIssue("error", name, "missing_fields", "no fields list"))
        return issues
    seen: set[str] = set()
    for item in fields or []:
        if not isinstance(item, dict) or "name" not in item:
            issues.append(ContractIssue("error", name, "malformed_field", "field missing name"))
            continue
        fname = str(item["name"])
        if fname in seen:
            issues.append(ContractIssue("error", name, "duplicate_field", fname, fname))
        seen.add(fname)
        ftype = str(item.get("type") or "")
        if ftype and ftype not in ALLOWED_FIELD_TYPES:
            issues.append(
                ContractIssue("error", name, "unknown_type", f"{fname} type {ftype!r}", fname)
            )
        enum = item.get("enum")
        if enum is not None and (
            not isinstance(enum, list) or not enum or not all(isinstance(v, str) for v in enum)
        ):
            issues.append(ContractIssue("error", name, "malformed_enum", fname, fname))
    if name == "quality":
        checks = [c.get("name") for c in (spec.get("checks") or []) if isinstance(c, dict)]
        if len(checks) != len(set(checks)):
            issues.append(ContractIssue("error", name, "duplicate_check", "duplicate checks"))
        if not spec.get("report_fields"):
            issues.append(
                ContractIssue("error", name, "missing_report_fields", "need report_fields")
            )
    return issues
