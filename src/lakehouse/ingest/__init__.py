"""Event-driven Bronze ingestion (S3 → SQS → Lambda)."""

from lakehouse.ingest.bronze_handler import handler, ingest_bronze_event
from lakehouse.ingest.s3_events import BronzeObjectRef, extract_object_refs

__all__ = [
    "BronzeObjectRef",
    "extract_object_refs",
    "handler",
    "ingest_bronze_event",
]
