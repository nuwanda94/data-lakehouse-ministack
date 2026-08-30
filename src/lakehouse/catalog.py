"""Glue Data Catalog table specs for Silver and Gold.

Specs are derived from ``configs/contracts/{silver,gold}.json`` so the catalog,
data dictionary, and producers stay aligned. Terraform
(``infra/terraform/glue.tf``) materializes the same tables on real AWS.
MiniStack may not emulate Glue; ``register_catalog`` then records the spec
locally and still returns a complete description.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from lakehouse.config import Settings, load_settings
from lakehouse.contracts import load_contract

GLUE_DATABASE = "lakehouse_local"
SILVER_TABLE = "commerce_event_conformed"
GOLD_TABLE = "daily_event_metrics"

_TYPE_MAP = {
    "string": "string",
    "integer": "bigint",
    "number": "double",
    "datetime": "timestamp",
    "date": "date",
    "boolean": "boolean",
}


@dataclass(frozen=True, slots=True)
class CatalogColumn:
    name: str
    type: str
    comment: str = ""


@dataclass(frozen=True, slots=True)
class CatalogTable:
    database: str
    name: str
    zone: str
    bucket: str
    location: str
    format: str
    classification: str
    columns: tuple[CatalogColumn, ...]
    partition_keys: tuple[CatalogColumn, ...]
    description: str
    comments: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["columns"] = [asdict(col) for col in self.columns]
        payload["partition_keys"] = [asdict(col) for col in self.partition_keys]
        return payload

    def glue_storage_descriptor(self) -> dict[str, Any]:
        return {
            "Columns": [
                {
                    "Name": col.name,
                    "Type": col.type,
                    "Comment": col.comment,
                }
                for col in self.columns
            ],
            "Location": self.location,
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
            "Compressed": False,
            "SerdeInfo": {
                "SerializationLibrary": "org.openx.data.jsonserde.JsonSerDe",
                "Parameters": {"ignore.malformed.json": "true"},
            },
            "Parameters": {
                "classification": self.classification,
                "compressionType": "none",
                "typeOfData": "file",
            },
        }


def _hive_type(contract_type: str) -> str:
    return _TYPE_MAP.get(contract_type, "string")


def _columns_from_contract(
    spec: dict[str, Any],
    *,
    partition_names: list[str],
    partition_aliases: dict[str, str] | None = None,
) -> tuple[list[CatalogColumn], list[CatalogColumn]]:
    """Split contract fields into data columns vs Hive partition keys.

    Partition aliases map a Hive key (e.g. Gold ``metric``) onto a contract
    field (``event_type``) so types and comments stay correct.
    """

    aliases = partition_aliases or {}
    by_name = {str(item["name"]): item for item in spec.get("fields") or [] if "name" in item}
    data_cols: list[CatalogColumn] = []
    part_cols: list[CatalogColumn] = []

    for item in spec.get("fields") or []:
        name = str(item.get("name") or "")
        if not name or name in partition_names or name in aliases.values():
            continue
        data_cols.append(
            CatalogColumn(
                name=name,
                type=_hive_type(str(item.get("type") or "string")),
                comment=str(item.get("description") or ""),
            )
        )

    for part_name in partition_names:
        source_name = aliases.get(part_name, part_name)
        item = by_name.get(source_name, {"name": part_name, "type": "string"})
        part_cols.append(
            CatalogColumn(
                name=part_name,
                type="string",
                comment=str(item.get("description") or f"Hive partition {part_name}"),
            )
        )
    return data_cols, part_cols


def _s3_location(bucket: str, prefix: str) -> str:
    cleaned = prefix.strip("/")
    return f"s3://{bucket}/{cleaned}/"


def silver_table(settings: Settings | None = None) -> CatalogTable:
    resolved = settings or load_settings()
    spec = load_contract("silver")
    hive = list((spec.get("partitioning") or {}).get("hive") or ["event_type", "dt"])
    data_cols, part_cols = _columns_from_contract(spec, partition_names=hive)
    prefix = str((spec.get("partitioning") or {}).get("prefix") or resolved.silver_prefix)
    return CatalogTable(
        database=GLUE_DATABASE,
        name=str(spec.get("name") or SILVER_TABLE),
        zone="silver",
        bucket=resolved.silver_bucket,
        location=_s3_location(resolved.silver_bucket, prefix),
        format="json",
        classification="json",
        columns=tuple(data_cols),
        partition_keys=tuple(part_cols),
        description=str(spec.get("description") or "Silver conformed commerce events"),
        comments={col.name: col.comment for col in (*data_cols, *part_cols) if col.comment},
    )


def gold_table(settings: Settings | None = None) -> CatalogTable:
    resolved = settings or load_settings()
    spec = load_contract("gold")
    hive = list((spec.get("partitioning") or {}).get("hive") or ["metric", "dt"])
    data_cols, part_cols = _columns_from_contract(
        spec,
        partition_names=hive,
        partition_aliases={"metric": "event_type"},
    )
    prefix = str((spec.get("partitioning") or {}).get("prefix") or resolved.gold_prefix)
    return CatalogTable(
        database=GLUE_DATABASE,
        name=str(spec.get("name") or GOLD_TABLE),
        zone="gold",
        bucket=resolved.gold_bucket,
        location=_s3_location(resolved.gold_bucket, prefix),
        format="json",
        classification="json",
        columns=tuple(data_cols),
        partition_keys=tuple(part_cols),
        description=str(spec.get("description") or "Gold daily event metrics"),
        comments={col.name: col.comment for col in (*data_cols, *part_cols) if col.comment},
    )


def catalog_tables(settings: Settings | None = None) -> list[CatalogTable]:
    resolved = settings or load_settings()
    return [silver_table(resolved), gold_table(resolved)]


def _ensure_database(glue: Any, name: str) -> None:
    try:
        glue.get_database(Name=name)
        return
    except Exception:
        pass
    glue.create_database(
        DatabaseInput={
            "Name": name,
            "Description": "Local-first medallion lakehouse Silver/Gold tables",
        }
    )


def _put_table(glue: Any, table: CatalogTable) -> str:
    body = {
        "Name": table.name,
        "Description": table.description,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": table.classification,
            "EXTERNAL": "TRUE",
            "zone": table.zone,
        },
        "StorageDescriptor": table.glue_storage_descriptor(),
        "PartitionKeys": [
            {"Name": col.name, "Type": col.type, "Comment": col.comment}
            for col in table.partition_keys
        ],
    }
    try:
        glue.get_table(DatabaseName=table.database, Name=table.name)
        glue.update_table(DatabaseName=table.database, TableInput=body)
        return "updated"
    except Exception:
        glue.create_table(DatabaseName=table.database, TableInput=body)
        return "created"


def register_catalog(settings: Settings | None = None) -> dict[str, Any]:
    """Create or update Glue tables. Falls back to an in-process description."""

    resolved = settings or load_settings()
    tables = catalog_tables(resolved)
    result: dict[str, Any] = {
        "database": GLUE_DATABASE,
        "backend": "glue",
        "tables": [table.as_dict() for table in tables],
        "actions": {},
        "errors": [],
    }
    try:
        from lakehouse.aws import client

        glue = client("glue", resolved)
        _ensure_database(glue, GLUE_DATABASE)
        for table in tables:
            result["actions"][table.name] = _put_table(glue, table)
    except Exception as exc:
        result["backend"] = "spec"
        result["errors"].append(str(exc))
        result["actions"] = {table.name: "described" for table in tables}
    return result


def describe_catalog(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or load_settings()
    tables = catalog_tables(resolved)
    live: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        from lakehouse.aws import client

        glue = client("glue", resolved)
        for table in tables:
            resp = glue.get_table(DatabaseName=table.database, Name=table.name)
            live.append(resp.get("Table") or {})
    except Exception as exc:
        errors.append(str(exc))
    return {
        "database": GLUE_DATABASE,
        "tables": [table.as_dict() for table in tables],
        "live": live,
        "errors": errors,
    }
