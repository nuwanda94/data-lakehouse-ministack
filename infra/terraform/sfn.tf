resource "aws_iam_role" "sfn" {
  name = "${var.project}-sfn"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "sfn" {
  name = "${var.project}-sfn"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeZoneLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.zone["ingest"].arn,
          aws_lambda_function.zone["silver"].arn,
          aws_lambda_function.zone["quality"].arn,
          aws_lambda_function.zone["gold"].arn,
        ]
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_sfn_state_machine" "medallion" {
  name     = "${var.project}-medallion"
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/sfn.asl.json.tftpl", {
    ingest_arn  = aws_lambda_function.zone["ingest"].arn
    silver_arn  = aws_lambda_function.zone["silver"].arn
    quality_arn = aws_lambda_function.zone["quality"].arn
    gold_arn    = aws_lambda_function.zone["gold"].arn
  })

  depends_on = [
    aws_iam_role_policy.sfn,
    aws_lambda_function.zone,
  ]
}
