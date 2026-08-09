data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# CloudWatch Log Group — um por função Lambda, retenção parametrizada.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "/aws/lambda/${var.function_name}"
  })
}

# ---------------------------------------------------------------------------
# IAM — princípio do menor privilégio por função.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "lambda" {
  name = "${var.function_name}-role"

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

  tags = merge(var.tags, {
    Name = "${var.function_name}-role"
  })
}

resource "aws_iam_role_policy" "lambda_base" {
  name = "${var.function_name}-base-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "${aws_cloudwatch_log_group.lambda.arn}",
          "${aws_cloudwatch_log_group.lambda.arn}:*"
        ]
      },
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
          "xray:GetSamplingStatisticSummaries"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_dynamodb" {
  count = var.enable_dynamodb_access ? 1 : 0

  name = "${var.function_name}-dynamodb-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:DescribeTable"
        ]
        Resource = [
          var.dynamodb_table_arn,
          "${var.dynamodb_table_arn}/index/*"
        ]
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# AWS Lambda — runtime customizado (Go / Quarkus nativo via provided.al2023).
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = aws_iam_role.lambda.arn
  handler       = var.handler
  runtime       = var.runtime

  # Cole aqui o caminho local do pacote .zip do binário compilado.
  # Exemplo Go (CPU):     "../build/go-cpu/bootstrap.zip"
  # Exemplo Quarkus (I/O): "../build/quarkus-io/function.zip"
  filename         = var.filename
  source_code_hash = filebase64sha256(var.filename)

  memory_size = var.memory_size
  timeout     = var.timeout

  architectures = var.architectures

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = merge(
      var.environment_variables,
      var.enable_dynamodb_access ? {
        DYNAMODB_TABLE_NAME = var.dynamodb_table_name
      } : {}
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_base
  ]

  tags = merge(var.tags, {
    Name              = var.function_name
    RuntimeFamily     = var.runtime_family
    BenchmarkScenario = var.scenario
  })
}
