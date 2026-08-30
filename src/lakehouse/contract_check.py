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


def _matches(value: Any, ftype: str) -> bool:
    if ftype == "string":
        return isinstance(value, str)
    if ftype == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if ftype == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ftype == "boolean":
        return isinstance(value, bool)
    if ftype == "datetime":
        return isinstance(value, datetime) or (isinstance(value, str) and "T" in value)
    if ftype == "date":
        return isinstance(value, date) or (isinstance(value, str) and len(value) == 10)
    return True


def validate_payload(
    payload: dict[str, Any], spec: dict[str, Any], *, contract: str
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for fname, item in _map(spec).items():
        required = bool(item.get("required", False))
        if fname not in payload or payload[fname] is None:
            if required:
                issues.append(ContractIssue("error", contract, "missing_required", fname, fname))
            continue
        value = payload[fname]
        ftype = str(item.get("type") or "string")
        if not _matches(value, ftype):
            issues.append(
                ContractIssue(
                    "error",
                    contract,
                    "type_mismatch",
                    f"{fname} expected {ftype} got {type(value).__name__}",
                    fname,
                )
            )
        allowed = item.get("enum")
        if allowed and isinstance(value, str) and value not in allowed:
            issues.append(
                ContractIssue("error", contract, "enum_mismatch", f"{fname}={value!r}", fname)
            )
    return issues


def compare_contracts(old: dict[str, Any], new: dict[str, Any], *, name: str = "") -> SchemaDiff:
    contract = name or str(new.get("name") or old.get("name") or "unknown")
    diff = SchemaDiff(contract=contract)
    old_f, new_f = _map(old), _map(new)
    for fname, prev in old_f.items():
        nxt = new_f.get(fname)
        if nxt is None:
            if prev.get("required", False):
                diff.breaking.append(f"removed field {fname}")
            else:
                diff.additive.append(f"removed optional field {fname}")
            continue
        ot, nt = str(prev.get("type") or "string"), str(nxt.get("type") or "string")
        if ot != nt and nt not in _TYPE_WIDENS_TO.get(ot, frozenset()):
            diff.breaking.append(f"type change {fname}: {ot} -> {nt}")
        elif ot != nt:
            diff.additive.append(f"widened type {fname}: {ot} -> {nt}")
        if (not prev.get("required", False)) and nxt.get("required", False):
            diff.breaking.append(f"field {fname} became required")
        elif prev.get("required", False) and not nxt.get("required", False):
            diff.additive.append(f"field {fname} is no longer required")
        oe, ne = set(prev.get("enum") or []), set(nxt.get("enum") or [])
        if oe and ne:
            if oe - ne:
                diff.breaking.append(f"enum values removed from {fname}: {sorted(oe - ne)}")
            if ne - oe:
                diff.additive.append(f"enum values added to {fname}: {sorted(ne - oe)}")
        elif oe and not ne:
            diff.breaking.append(f"enum constraint removed from {fname}")
        elif ne and not oe:
            diff.breaking.append(f"enum constraint added to unconstrained field {fname}")
    for fname, nxt in new_f.items():
        if fname in old_f:
            continue
        if nxt.get("required", False):
            diff.breaking.append(f"added required field {fname}")
        else:
            diff.additive.append(f"added optional field {fname}")
    old_hive = list((old.get("partitioning") or {}).get("hive") or [])
    new_hive = list((new.get("partitioning") or {}).get("hive") or [])
    if old_hive and new_hive and old_hive != new_hive:
        diff.breaking.append(f"partition keys changed {old_hive} -> {new_hive}")
    if name == "quality" or old.get("checks") or new.get("checks"):
        oc = {str(c.get("name")) for c in (old.get("checks") or []) if isinstance(c, dict)}
        nc = {str(c.get("name")) for c in (new.get("checks") or []) if isinstance(c, dict)}
        if oc - nc:
            diff.breaking.append(f"quality checks removed: {sorted(oc - nc)}")
        if nc - oc:
            diff.additive.append(f"quality checks added: {sorted(nc - oc)}")
    diff.breaking = list(dict.fromkeys(diff.breaking))
    diff.additive = list(dict.fromkeys(diff.additive))
    return diff


def check_producers() -> list[ContractIssue]:
    from lakehouse.models import CommerceEvent, PipelineRun, QualityResult
    from lakehouse.quality.gate import KNOWN_EVENT_TYPES, evaluate_quality
    from lakehouse.seed.generate import EVENT_TYPES, generate_events

    issues: list[ContractIssue] = []
    bronze, silver = load_contract("bronze"), load_contract("silver")
    gold, quality = load_contract("gold"), load_contract("quality")
    pipeline_run = load_contract("pipeline_run")
    model_fields = set(CommerceEvent.model_fields)
    for fname in sorted(set(_names(bronze)) - model_fields):
        issues.append(ContractIssue("error", "bronze", "producer_missing_field", fname, fname))
    for fname in sorted(set(_names(silver)) - model_fields - {"_late"}):
        issues.append(ContractIssue("error", "silver", "producer_missing_field", fname, fname))
    if "_late" not in set(_names(silver)):
        issues.append(ContractIssue("error", "silver", "missing_late_flag", "_late"))
    bronze_enum = set((_map(bronze).get("event_type") or {}).get("enum") or [])
    silver_enum = set((_map(silver).get("event_type") or {}).get("enum") or [])
    if bronze_enum and set(EVENT_TYPES) != bronze_enum:
        issues.append(
            ContractIssue(
                "error",
                "bronze",
                "enum_drift",
                f"{sorted(set(EVENT_TYPES))} != {sorted(bronze_enum)}",
                "event_type",
            )
        )
    if silver_enum and set(KNOWN_EVENT_TYPES) != silver_enum:
        issues.append(
            ContractIssue(
                "error",
                "silver",
                "enum_drift",
                f"{sorted(set(KNOWN_EVENT_TYPES))} != {sorted(silver_enum)}",
                "event_type",
            )
        )
    sample = generate_events(3, seed=7)
    for event in sample:
        issues.extend(validate_payload(event.model_dump(), bronze, contract="bronze"))
    if not {"dt", "event_type", "events", "amount_usd"}.issubset(set(_names(gold))):
        issues.append(ContractIssue("error", "gold", "gold_fields_incomplete", "measures"))
    check_names = [str(c["name"]) for c in (quality.get("checks") or []) if "name" in c]
    result_names = {r.check_name for r in evaluate_quality(sample).results}
    if set(check_names) != result_names:
        issues.append(
            ContractIssue(
                "error",
                "quality",
                "check_drift",
                f"{sorted(result_names)} != {sorted(check_names)}",
            )
        )
    expected_report = {
        "run_id",
        "passed",
        "action",
        "rows_scanned",
        "rows_failed",
        "fail_ratio",
        "checks",
    }
    if not expected_report.issubset(set(quality.get("report_fields") or [])):
        issues.append(ContractIssue("error", "quality", "report_fields_incomplete", "report"))
    run_fields = set(PipelineRun.model_fields)
    for fname in sorted(set(_names(pipeline_run)) - {"object_count"} - run_fields):
        issues.append(
            ContractIssue("error", "pipeline_run", "producer_missing_field", fname, fname)
        )
    for needed in ("check_name", "passed", "rows_scanned", "rows_failed"):
        if needed not in QualityResult.model_fields:
            issues.append(
                ContractIssue("error", "quality", "producer_missing_field", needed, needed)
            )
    return issues


def check_all() -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for name in CONTRACT_NAMES:
        issues.extend(validate_contract_document(name))
    issues.extend(check_producers())
    return issues


def errors_only(issues: list[ContractIssue]) -> list[ContractIssue]:
    return [item for item in issues if item.severity == "error"]


def report_issues(issues: list[ContractIssue]) -> dict[str, Any]:
    errs = errors_only(issues)
    return {
        "ok": not errs,
        "error_count": len(errs),
        "warning_count": sum(1 for i in issues if i.severity == "warning"),
        "issues": [i.as_dict() for i in issues],
        "contracts": list(CONTRACT_NAMES),
    }
