variable "aws_endpoint_url" {
  type        = string
  description = "MiniStack or AWS endpoint. Empty string targets real AWS."
  default     = "http://localhost:4566"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "lakehouse-local"
}

variable "bronze_bucket" {
  type    = string
  default = "lakehouse-local-bronze"
}

variable "silver_bucket" {
  type    = string
  default = "lakehouse-local-silver"
}

variable "gold_bucket" {
  type    = string
  default = "lakehouse-local-gold"
}

variable "pipeline_runs_table" {
  type    = string
  default = "lakehouse-local-pipeline-runs"
}

variable "gold_metrics_table" {
  type    = string
  default = "lakehouse-local-gold-metrics"
}

variable "bronze_events_queue" {
  type    = string
  default = "lakehouse-local-bronze-events"
}

variable "bronze_events_dlq" {
  type        = string
  description = "Dead-letter queue for Bronze S3/SQS events that exhaust retries."
  default     = "lakehouse-local-bronze-events-dlq"
}

variable "bronze_events_max_receive_count" {
  type        = number
  description = "Receives before a Bronze event is moved to the DLQ."
  default     = 3
}

variable "lambda_runtime" {
  type        = string
  description = "Lambda runtime shared by zone functions."
  default     = "python3.12"
}

variable "lambda_zip_path" {
  type        = string
  description = "Path to the packaged lakehouse Lambda zip. Empty uses ../../build/lambda/lakehouse.zip."
  default     = ""
}
