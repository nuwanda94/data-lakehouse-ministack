# Bronze ObjectCreated → SQS (ingest Lambda ESM) + EventBridge fan-out.
# Filter is events/ so quarantine / other prefixes do not start a run.

resource "aws_sqs_queue_policy" "bronze_events" {
  queue_url = aws_sqs_queue.bronze_events.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3BronzeNotify"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = ["sqs:SendMessage", "sqs:SendMessageBatch"]
        Resource = aws_sqs_queue.bronze_events.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.bronze.arn
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_notification" "bronze_events" {
  bucket = aws_s3_bucket.bronze.id

  queue {
    id            = "bronze-events-sqs"
    queue_arn     = aws_sqs_queue.bronze_events.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "events/"
  }

  # Same objects also land on the default event bus for later SFN / rules.
  eventbridge = true

  depends_on = [aws_sqs_queue_policy.bronze_events]
}
