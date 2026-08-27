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
