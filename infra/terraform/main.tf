resource "aws_s3_bucket" "bronze" {
  bucket        = var.bronze_bucket
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket" "silver" {
  bucket        = var.silver_bucket
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket" "gold" {
  bucket        = var.gold_bucket
  force_destroy = var.force_destroy
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

resource "aws_sqs_queue" "bronze_events_dlq" {
  name                      = var.bronze_events_dlq
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "bronze_events" {
  name                       = var.bronze_events_queue
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 60

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bronze_events_dlq.arn
    maxReceiveCount     = var.bronze_events_max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "bronze_events_dlq" {
  queue_url = aws_sqs_queue.bronze_events_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.bronze_events.arn]
  })
}
