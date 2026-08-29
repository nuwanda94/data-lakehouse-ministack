locals {
  use_custom_endpoint = var.aws_endpoint_url != ""
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

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
    }
  }
}
