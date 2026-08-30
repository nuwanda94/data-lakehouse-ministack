# Athena workgroup + named queries over the Glue Silver/Gold tables.
# MiniStack typically has no Athena API; keep enable_athena=false locally so
# `make infra` stays reliable. Flip the variable when targeting real AWS.

resource "aws_athena_workgroup" "lakehouse" {
  count = var.enable_athena ? 1 : 0

  name        = var.athena_workgroup
  description = "Medallion lakehouse analyst workgroup with scan caps."
  state       = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 104857600

    result_configuration {
      output_location = "s3://${var.gold_bucket}/athena-results/"
    }
  }
}

resource "aws_athena_named_query" "gold_daily_totals" {
  count = var.enable_athena ? 1 : 0

  name        = "gold_daily_totals"
  workgroup   = aws_athena_workgroup.lakehouse[0].id
  database    = var.glue_database
  description = "All Gold daily event metrics ordered by date then metric."
  query       = <<-SQL
    SELECT metric, dt, events, amount_usd
    FROM ${var.glue_database}.${var.glue_gold_table}
    ORDER BY dt, metric;
  SQL
}

resource "aws_athena_named_query" "gold_purchase_revenue" {
  count = var.enable_athena ? 1 : 0

  name        = "gold_purchase_revenue"
  workgroup   = aws_athena_workgroup.lakehouse[0].id
  database    = var.glue_database
  description = "Purchase-only Gold rows (revenue proxy)."
  query       = <<-SQL
    SELECT dt, events, amount_usd
    FROM ${var.glue_database}.${var.glue_gold_table}
    WHERE metric = 'purchase'
    ORDER BY dt;
  SQL
}

resource "aws_athena_named_query" "gold_last_7_days" {
  count = var.enable_athena ? 1 : 0

  name        = "gold_last_7_days"
  workgroup   = aws_athena_workgroup.lakehouse[0].id
  database    = var.glue_database
  description = "Gold metrics for the last 7 calendar days (inclusive)."
  query       = <<-SQL
    SELECT metric, dt, events, amount_usd
    FROM ${var.glue_database}.${var.glue_gold_table}
    WHERE dt >= date_format(date_add('day', -6, current_date), '%Y-%m-%d')
    ORDER BY dt, metric;
  SQL
}

resource "aws_athena_named_query" "silver_late_event_counts" {
  count = var.enable_athena ? 1 : 0

  name        = "silver_late_event_counts"
  workgroup   = aws_athena_workgroup.lakehouse[0].id
  database    = var.glue_database
  description = "Count of late vs on-time Silver events by type and day."
  query       = <<-SQL
    SELECT event_type, dt,
           count(*) AS events,
           sum(CASE WHEN _late THEN 1 ELSE 0 END) AS late_events
    FROM ${var.glue_database}.${var.glue_silver_table}
    GROUP BY event_type, dt
    ORDER BY dt, event_type;
  SQL
}
