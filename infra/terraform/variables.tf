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

variable "pipeline_ssm_parameter" {
  type        = string
  description = "SSM parameter name that stores configs/pipeline.json."
  default     = "/lakehouse-local/pipeline"
}

variable "pipeline_config_path" {
  type        = string
  description = "Path to the checked-in pipeline config JSON published to SSM."
  default     = ""
}

variable "ssm_enabled" {
  type        = bool
  description = "When true, Lambdas overlay Settings from the SSM parameter."
  default     = false
}

variable "enable_glue" {
  type        = bool
  description = "Create Glue catalog database + Silver/Gold tables. Keep false on MiniStack."
  default     = false
}

variable "glue_database" {
  type    = string
  default = "lakehouse_local"
}

variable "glue_silver_table" {
  type    = string
  default = "commerce_event_conformed"
}

variable "glue_gold_table" {
  type    = string
  default = "daily_event_metrics"
}

variable "enable_athena" {
  type        = bool
  description = "Create Athena workgroup + named queries. Keep false on MiniStack."
  default     = false
}

variable "athena_workgroup" {
  type    = string
  default = "lakehouse-local"
}
