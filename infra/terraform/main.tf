resource "aws_s3_bucket" "bronze" {
  bucket        = var.bronze_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "silver" {
  bucket        = var.silver_bucket
  force_destroy = true
}

resource "aws_s3_bucket" "gold" {
  bucket        = var.gold_bucket
  force_destroy = true
}

resource "aws_dynamodb_table" "pipeline_runs" {
  name         = var.pipeline_runs_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "gold_metrics" {
  name         = var.gold_metrics_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "metric_day"

  attribute {
    name = "metric_day"
    type = "S"
  }
}
