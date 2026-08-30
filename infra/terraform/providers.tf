locals {
  use_custom_endpoint = var.aws_endpoint_url != ""
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = var.use_static_credentials ? var.aws_access_key : null
  secret_key                  = var.use_static_credentials ? var.aws_secret_key : null
  skip_credentials_validation = var.use_static_credentials
  skip_metadata_api_check     = var.use_static_credentials
  skip_requesting_account_id  = var.use_static_credentials
  s3_use_path_style           = local.use_custom_endpoint

  dynamic "endpoints" {
    for_each = local.use_custom_endpoint ? [1] : []
    content {
      s3       = var.aws_endpoint_url
      dynamodb = var.aws_endpoint_url
      iam      = var.aws_endpoint_url
      sts      = var.aws_endpoint_url
      sqs      = var.aws_endpoint_url
      lambda   = var.aws_endpoint_url
      logs     = var.aws_endpoint_url
      ssm      = var.aws_endpoint_url
      states   = var.aws_endpoint_url
      glue     = var.aws_endpoint_url
      athena   = var.aws_endpoint_url
    }
  }

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
