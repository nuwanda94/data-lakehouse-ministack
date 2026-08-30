# Real AWS. Edit bucket names before apply — S3 names are globally unique.
# Credentials come from the default chain (env, shared config, or instance role).
environment              = "aws"
aws_endpoint_url         = ""
aws_region               = "us-east-1"
use_static_credentials   = false
force_destroy            = false
enable_glue              = true
enable_athena            = true
ssm_enabled              = true
project                  = "lakehouse-aws"
bronze_bucket            = "lakehouse-aws-bronze"
silver_bucket            = "lakehouse-aws-silver"
gold_bucket              = "lakehouse-aws-gold"
pipeline_runs_table      = "lakehouse-aws-pipeline-runs"
gold_metrics_table       = "lakehouse-aws-gold-metrics"
bronze_events_queue      = "lakehouse-aws-bronze-events"
bronze_events_dlq        = "lakehouse-aws-bronze-events-dlq"
pipeline_ssm_parameter   = "/lakehouse-aws/pipeline"
glue_database            = "lakehouse_aws"
athena_workgroup         = "lakehouse-aws"
