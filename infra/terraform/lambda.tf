locals {
  lambda_zip_path = var.lambda_zip_path != "" ? var.lambda_zip_path : "${path.module}/../../build/lambda/lakehouse.zip"
  lambda_env = {
    AWS_ENDPOINT_URL        = var.aws_endpoint_url
    AWS_DEFAULT_REGION      = var.aws_region
    BRONZE_BUCKET           = aws_s3_bucket.bronze.bucket
    SILVER_BUCKET           = aws_s3_bucket.silver.bucket
    GOLD_BUCKET             = aws_s3_bucket.gold.bucket
    PIPELINE_RUNS_TABLE     = aws_dynamodb_table.pipeline_runs.name
    GOLD_METRICS_TABLE      = aws_dynamodb_table.gold_metrics.name
    BRONZE_EVENTS_QUEUE     = aws_sqs_queue.bronze_events.name
    BRONZE_EVENTS_QUEUE_URL = aws_sqs_queue.bronze_events.url
  }
  lambda_functions = {
    ingest = {
      handler = "lakehouse.ingest.bronze_handler.handler"
      timeout = 60
      memory  = 256
    }
    silver = {
      handler = "lakehouse.silver.handler.handler"
      timeout = 120
      memory  = 256
    }
    quality = {
      handler = "lakehouse.quality.handler.handler"
      timeout = 120
      memory  = 256
    }
    gold = {
      handler = "lakehouse.gold.handler.handler"
      timeout = 120
      memory  = 256
    }
  }
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project}-lambda"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3Zones"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:HeadObject",
        ]
        Resource = [
          aws_s3_bucket.bronze.arn,
          "${aws_s3_bucket.bronze.arn}/*",
          aws_s3_bucket.silver.arn,
          "${aws_s3_bucket.silver.arn}/*",
          aws_s3_bucket.gold.arn,
          "${aws_s3_bucket.gold.arn}/*",
        ]
      },
      {
        Sid    = "Dynamo"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.pipeline_runs.arn,
          aws_dynamodb_table.gold_metrics.arn,
        ]
      },
      {
        Sid    = "SqsBronze"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:ChangeMessageVisibility",
        ]
        Resource = [aws_sqs_queue.bronze_events.arn]
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambda_functions
  name              = "/aws/lambda/${var.project}-${each.key}"
  retention_in_days = 14
}

resource "aws_lambda_function" "zone" {
  for_each = local.lambda_functions

  function_name    = "${var.project}-${each.key}"
  role             = aws_iam_role.lambda.arn
  handler          = each.value.handler
  runtime          = var.lambda_runtime
  filename         = local.lambda_zip_path
  source_code_hash = filebase64sha256(local.lambda_zip_path)
  timeout          = each.value.timeout
  memory_size      = each.value.memory

  environment {
    variables = local.lambda_env
  }

  depends_on = [
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.lambda,
  ]
}

resource "aws_lambda_event_source_mapping" "bronze_ingest" {
  event_source_arn = aws_sqs_queue.bronze_events.arn
  function_name    = aws_lambda_function.zone["ingest"].arn
  batch_size       = 10
  enabled          = true
}
