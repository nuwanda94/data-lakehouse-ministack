"""Parse and lint the in-repo dbt project without requiring dbt-core.

MiniStack rarely emulates Athena. Gold models still live as a real dbt
project under ``transform/dbt`` so analysts can ``dbt run`` against
Glue/Athena on real AWS. Locally we parse YAML + SQL, substitute
``{{ source }}`` / ``{{ ref }}``, and check the graph against the Glue
catalog names.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lakehouse.catalog import GLUE_DATABASE, GOLD_TABLE, SILVER_TABLE

SOURCE_RE = re.compile(
    r"""\{\{\s*source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}""",
)
REF_RE = re.compile(r"""\{\{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}""")
CONFIG_RE = re.compile(r"\{\{\s*config\s*\(.*?\)\s*\}\}", re.DOTALL)


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        marker = candidate / "transform" / "dbt" / "dbt_project.yml"
        if marker.is_file():
            return candidate
    return Path.cwd()


def project_dir() -> Path:
    return repo_root() / "transform" / "dbt"


@dataclass(frozen=True, slots=True)
class DbtModel:
    name: str
    path: str
    materialization: str
    raw_sql: str
    compiled_sql: str
    sources: tuple[tuple[str, str], ...]
    refs: tuple[str, ...]
    description: str = ""
    tests: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DbtProject:
    name: str
    profile: str
    models: list[DbtModel] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "profile": self.profile,
            "project_dir": str(project_dir()),
            "models": [model.as_dict() for model in self.models],
            "sources": self.sources,
            "issues": self.issues,
        }


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text or text in {"|", ">"}:
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    if (text.startswith("'") and text.endswith("'")) or (
        text.startswith('"') and text.endswith('"')
    ):
        return text[1:-1]
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _load_yaml(path: Path) -> dict[str, Any]:
    """Indent-based YAML subset (mappings, lists of mappings, inline lists)."""

    lines: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, stripped.lstrip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        mapping: dict[str, Any] = {}
        sequence: list[Any] = []
        is_list: bool | None = None
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"{path}: unexpected indent at {content!r}")
            if content.startswith("- "):
                if is_list is False:
                    raise ValueError(f"{path}: mixed list/map at {content!r}")
                is_list = True
                item_text = content[2:].strip()
                index += 1
                child: Any
                if ":" in item_text:
                    key, value = item_text.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    child_value: Any = _parse_scalar(value) if value else {}
                    if index < len(lines) and lines[index][0] > current_indent:
                        nested, index = parse_block(index, lines[index][0])
                        if value:
                            child = {key: child_value}
                            if isinstance(nested, dict):
                                child.update(nested)
                        else:
                            child = {key: nested}
                    else:
                        child = {key: child_value}
                else:
                    child = _parse_scalar(item_text)
                    if index < len(lines) and lines[index][0] > current_indent:
                        nested, index = parse_block(index, lines[index][0])
                        child = nested
                sequence.append(child)
                continue

            if is_list is True:
                break
            is_list = False
            if ":" not in content:
                raise ValueError(f"{path}: expected key: value, got {content!r}")
            key, value = content.split(":", 1)
            key = key.strip()
            value = value.strip()
            index += 1
            if value:
                mapping[key] = _parse_scalar(value)
            elif index < len(lines) and lines[index][0] > current_indent:
                mapping[key], index = parse_block(index, lines[index][0])
            else:
                mapping[key] = {}
        return (sequence if is_list else mapping), index

    parsed, _ = parse_block(0, lines[0][0] if lines else 0)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} did not contain a mapping")
    return parsed


def _strip_jinja_config(sql: str) -> str:
    return CONFIG_RE.sub("", sql).strip()


def _compile_sql(sql: str, *, database: str) -> str:
    compiled = SOURCE_RE.sub(lambda match: f"{database}.{match.group(2)}", sql)
    compiled = REF_RE.sub(lambda match: match.group(1), compiled)
    compiled = _strip_jinja_config(compiled)
    compiled = re.sub(r"\n{3,}", "\n\n", compiled)
    return compiled.strip() + "\n"


def _materialization(sql: str, default: str = "view") -> str:
    match = re.search(r"materialized\s*=\s*['\"](\w+)['\"]", sql)
    return match.group(1) if match else default


def _model_docs(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for model in schema.get("models") or []:
        if isinstance(model, dict) and model.get("name"):
            by_name[str(model["name"])] = model
    return by_name


def _collect_tests(entry: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for test in entry.get("tests") or []:
        if isinstance(test, str):
            names.append(test)
        elif isinstance(test, dict):
            names.extend(str(key) for key in test)
    for column in entry.get("columns") or []:
        if not isinstance(column, dict):
            continue
        col = str(column.get("name") or "")
        for test in column.get("tests") or []:
            if isinstance(test, str):
                names.append(f"{col}:{test}")
            elif isinstance(test, dict):
                names.extend(f"{col}:{key}" for key in test)
    return tuple(names)


def load_project() -> DbtProject:
    root = project_dir()
    project_yml = _load_yaml(root / "dbt_project.yml")
    sources_yml = _load_yaml(root / "models" / "sources.yml")
    schema_yml = _load_yaml(root / "models" / "schema.yml")
    docs = _model_docs(schema_yml)

    sources: list[dict[str, Any]] = []
    for src in sources_yml.get("sources") or []:
        if isinstance(src, dict):
            sources.append(src)

    models: list[DbtModel] = []
    for path in sorted((root / "models").rglob("*.sql")):
        raw = path.read_text(encoding="utf-8")
        name = path.stem
        entry = docs.get(name, {})
        models.append(
            DbtModel(
                name=name,
                path=str(path.relative_to(root)),
                materialization=_materialization(raw),
                raw_sql=raw,
                compiled_sql=_compile_sql(raw, database=GLUE_DATABASE),
                sources=tuple(SOURCE_RE.findall(raw)),
                refs=tuple(REF_RE.findall(raw)),
                description=str(entry.get("description") or ""),
                tests=_collect_tests(entry),
            )
        )

    return DbtProject(
        name=str(project_yml.get("name") or "lakehouse"),
        profile=str(project_yml.get("profile") or "lakehouse"),
        models=models,
        sources=sources,
    )


def lint_project(project: DbtProject | None = None) -> list[str]:
    loaded = project or load_project()
    issues: list[str] = []
    model_names = {model.name for model in loaded.models}

    expected_models = {
        "stg_daily_event_metrics",
        "fct_daily_event_metrics",
        "fct_daily_purchase_revenue",
        "dim_event_type",
    }
    missing = expected_models - model_names
    if missing:
        issues.append(f"missing models: {sorted(missing)}")

    source_tables: set[tuple[str, str]] = set()
    for src in loaded.sources:
        src_name = str(src.get("name") or "")
        schema = str(src.get("schema") or "")
        if schema and schema != GLUE_DATABASE:
            issues.append(f"source {src_name!r} schema {schema!r} != {GLUE_DATABASE!r}")
        for table in src.get("tables") or []:
            if isinstance(table, dict) and table.get("name"):
                source_tables.add((src_name, str(table["name"])))

    expected_sources = {("lakehouse", GOLD_TABLE), ("lakehouse", SILVER_TABLE)}
    if not expected_sources.issubset(source_tables):
        issues.append(f"sources missing Glue tables; have {sorted(source_tables)}")

    gold_stage = next((m for m in loaded.models if m.name == "stg_daily_event_metrics"), None)
    if gold_stage and ("lakehouse", GOLD_TABLE) not in gold_stage.sources:
        issues.append("stg_daily_event_metrics must source lakehouse.daily_event_metrics")

    purchase = next((m for m in loaded.models if m.name == "fct_daily_purchase_revenue"), None)
    if purchase and "purchase" not in purchase.compiled_sql:
        issues.append("fct_daily_purchase_revenue must filter metric = purchase")

    for model in loaded.models:
        if "{{" in model.compiled_sql:
            issues.append(f"{model.name} still contains Jinja after compile")
        for ref in model.refs:
            if ref not in model_names:
                issues.append(f"{model.name} refs unknown model {ref!r}")
        for source in model.sources:
            if source not in source_tables:
                issues.append(f"{model.name} refs unknown source {source!r}")
        if not model.tests and model.name.startswith("fct_"):
            issues.append(f"{model.name} has no schema tests")

    loaded.issues = issues
    return issues


def describe_project() -> dict[str, Any]:
    project = load_project()
    issues = lint_project(project)
    payload = project.as_dict()
    payload["ok"] = not issues
    payload["glue_database"] = GLUE_DATABASE
    payload["gold_table"] = GOLD_TABLE
    payload["silver_table"] = SILVER_TABLE
    return payload
