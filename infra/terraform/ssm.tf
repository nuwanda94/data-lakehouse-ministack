locals {
  pipeline_config_path = var.pipeline_config_path != "" ? var.pipeline_config_path : "${path.module}/../../configs/pipeline.json"
  pipeline_config_body = file(local.pipeline_config_path)
}

resource "aws_ssm_parameter" "pipeline" {
  name        = var.pipeline_ssm_parameter
  description = "Lakehouse behavior config (quality, lookback, partitions, feature flags)"
  type        = "String"
  overwrite   = true
  value       = local.pipeline_config_body
}

resource "aws_iam_role_policy" "lambda_ssm" {
  name = "${var.project}-lambda-ssm"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPipelineConfig"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
        ]
        Resource = aws_ssm_parameter.pipeline.arn
      }
    ]
  })
}
