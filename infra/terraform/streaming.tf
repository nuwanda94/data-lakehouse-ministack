# Optional Kinesis + Firehose producer path into Bronze.
# Off by default so MiniStack CI does not depend on streaming APIs.

variable "enable_streaming" {
  type        = bool
  description = "Create Kinesis stream + Firehose delivery into the Bronze bucket. Keep false on MiniStack unless you are exercising the streaming path."
  default     = false
}

variable "kinesis_stream" {
  type    = string
  default = "lakehouse-local-events"
}

variable "kinesis_shard_count" {
  type    = number
  default = 1
}

variable "firehose_stream" {
  type    = string
  default = "lakehouse-local-events-firehose"
}

resource "aws_kinesis_stream" "events" {
  count            = var.enable_streaming ? 1 : 0
  name             = var.kinesis_stream
  shard_count      = var.kinesis_shard_count
  retention_period = 24
}

resource "aws_iam_role" "firehose" {
  count = var.enable_streaming ? 1 : 0
  name  = "${var.project}-firehose"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "firehose" {
  count = var.enable_streaming ? 1 : 0
  name  = "${var.project}-firehose"
  role  = aws_iam_role.firehose[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadKinesis"
        Effect = "Allow"
        Action = [
          "kinesis:DescribeStream",
          "kinesis:GetShardIterator",
          "kinesis:GetRecords",
          "kinesis:ListShards",
        ]
        Resource = aws_kinesis_stream.events[0].arn
      },
      {
        Sid    = "WriteBronze"
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject",
        ]
        Resource = [
          aws_s3_bucket.bronze.arn,
          "${aws_s3_bucket.bronze.arn}/*",
        ]
      }
    ]
  })
}

resource "aws_kinesis_firehose_delivery_stream" "events" {
  count       = var.enable_streaming ? 1 : 0
  name        = var.firehose_stream
  destination = "extended_s3"

  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.events[0].arn
    role_arn           = aws_iam_role.firehose[0].arn
  }

  extended_s3_configuration {
    role_arn           = aws_iam_role.firehose[0].arn
    bucket_arn         = aws_s3_bucket.bronze.arn
    prefix             = "events/dt=!{timestamp:yyyy-MM-dd}/"
    buffering_size     = 1
    buffering_interval = 60
    compression_format = "UNCOMPRESSED"
  }
}
