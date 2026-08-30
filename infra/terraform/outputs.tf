output "aws_endpoint_url" {
  value = var.aws_endpoint_url
}

output "aws_region" {
  value = var.aws_region
}

output "bronze_bucket" {
  value = aws_s3_bucket.bronze.bucket
}

output "silver_bucket" {
  value = aws_s3_bucket.silver.bucket
}

output "gold_bucket" {
  value = aws_s3_bucket.gold.bucket
}

output "pipeline_runs_table" {
  value = aws_dynamodb_table.pipeline_runs.name
}

output "gold_metrics_table" {
  value = aws_dynamodb_table.gold_metrics.name
}

output "bronze_events_queue" {
  value = aws_sqs_queue.bronze_events.name
}

output "bronze_events_queue_url" {
  value = aws_sqs_queue.bronze_events.url
}

output "bronze_events_queue_arn" {
  value = aws_sqs_queue.bronze_events.arn
}

output "bronze_events_dlq" {
  value = aws_sqs_queue.bronze_events_dlq.name
}

output "bronze_events_dlq_url" {
  value = aws_sqs_queue.bronze_events_dlq.url
}

output "bronze_events_dlq_arn" {
  value = aws_sqs_queue.bronze_events_dlq.arn
}

output "bronze_notify_prefix" {
  value = "events/"
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

output "lambda_ingest_name" {
  value = aws_lambda_function.zone["ingest"].function_name
}

output "lambda_silver_name" {
  value = aws_lambda_function.zone["silver"].function_name
}

output "lambda_quality_name" {
  value = aws_lambda_function.zone["quality"].function_name
}

output "lambda_gold_name" {
  value = aws_lambda_function.zone["gold"].function_name
}

output "sfn_state_machine_name" {
  value = aws_sfn_state_machine.medallion.name
}

output "sfn_state_machine_arn" {
  value = aws_sfn_state_machine.medallion.arn
}

output "pipeline_ssm_parameter" {
  value = aws_ssm_parameter.pipeline.name
}

output "glue_database" {
  value = var.glue_database
}

output "glue_silver_table" {
  value = var.glue_silver_table
}

output "glue_gold_table" {
  value = var.glue_gold_table
}

output "enable_glue" {
  value = var.enable_glue
}

output "enable_athena" {
  value = var.enable_athena
}

output "athena_workgroup" {
  value = var.athena_workgroup
}

output "athena_result_location" {
  value = "s3://${var.gold_bucket}/athena-results/"
}
