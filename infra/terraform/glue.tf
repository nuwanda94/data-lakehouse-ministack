# Glue Data Catalog for Silver and Gold.
# MiniStack may not emulate Glue; keep enable_glue=false locally so `make infra`
# stays reliable. Flip the variable (or pass -var) when targeting real AWS.

resource "aws_glue_catalog_database" "lakehouse" {
  count = var.enable_glue ? 1 : 0

  name        = var.glue_database
  description = "Medallion lakehouse Silver and Gold tables"
}

resource "aws_glue_catalog_table" "silver" {
  count = var.enable_glue ? 1 : 0

  name          = var.glue_silver_table
  database_name = aws_glue_catalog_database.lakehouse[0].name
  table_type    = "EXTERNAL_TABLE"
  description   = "Cleansed CommerceEvent plus _late flag. Partitioned by event_type and dt."

  parameters = {
    classification                 = "json"
    EXTERNAL                       = "TRUE"
    zone                           = "silver"
    "projection.enabled"           = "true"
    "projection.event_type.type"   = "enum"
    "projection.event_type.values" = "page_view,add_to_cart,purchase,refund"
    "projection.dt.type"           = "date"
    "projection.dt.format"         = "yyyy-MM-dd"
    "projection.dt.range"          = "2024-01-01,NOW"
    "storage.location.template"    = "s3://${var.silver_bucket}/events/event_type=$${event_type}/dt=$${dt}"
  }

  storage_descriptor {
    location      = "s3://${var.silver_bucket}/events/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "json"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name    = "event_id"
      type    = "string"
      comment = "Same as bronze; used as object basename."
    }
    columns {
      name    = "event_ts"
      type    = "timestamp"
      comment = "Timezone-aware event time."
    }
    columns {
      name = "user_id"
      type = "string"
    }
    columns {
      name = "sku"
      type = "string"
    }
    columns {
      name    = "quantity"
      type    = "bigint"
      comment = "Units; Silver requires > 0."
    }
    columns {
      name    = "amount_usd"
      type    = "double"
      comment = "Gross amount in USD; Silver requires >= 0."
    }
    columns {
      name = "country"
      type = "string"
    }
    columns {
      name    = "_late"
      type    = "boolean"
      comment = "True when event_ts is older than watermark - lookback."
    }
  }

  partition_keys {
    name    = "event_type"
    type    = "string"
    comment = "page_view, add_to_cart, purchase, refund"
  }
  partition_keys {
    name    = "dt"
    type    = "string"
    comment = "Event date YYYY-MM-DD"
  }
}

resource "aws_glue_catalog_table" "gold" {
  count = var.enable_glue ? 1 : 0

  name          = var.glue_gold_table
  database_name = aws_glue_catalog_database.lakehouse[0].name
  table_type    = "EXTERNAL_TABLE"
  description   = "Daily grain aggregates by event_type. Partitioned by metric and dt."

  parameters = {
    classification              = "json"
    EXTERNAL                    = "TRUE"
    zone                        = "gold"
    "projection.enabled"        = "true"
    "projection.metric.type"    = "enum"
    "projection.metric.values"  = "page_view,add_to_cart,purchase,refund"
    "projection.dt.type"        = "date"
    "projection.dt.format"      = "yyyy-MM-dd"
    "projection.dt.range"       = "2024-01-01,NOW"
    "storage.location.template" = "s3://${var.gold_bucket}/metrics/metric=$${metric}/dt=$${dt}"
  }

  storage_descriptor {
    location      = "s3://${var.gold_bucket}/metrics/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "json"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name    = "events"
      type    = "bigint"
      comment = "Count of Silver events in the bucket."
    }
    columns {
      name    = "amount_usd"
      type    = "double"
      comment = "Sum of amount_usd, rounded to 2 decimal places."
    }
  }

  partition_keys {
    name    = "metric"
    type    = "string"
    comment = "event_type stored as Hive key metric="
  }
  partition_keys {
    name    = "dt"
    type    = "string"
    comment = "Event date YYYY-MM-DD"
  }
}
