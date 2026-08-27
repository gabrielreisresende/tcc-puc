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

  # X-Ray Active Tracing foi desativado em 27/08/2026: as metricas usadas no
  # TCC (Init Duration, Billed Duration, memoria) vem das linhas REPORT do
  # CloudWatch Logs, nao do X-Ray, e o Active Tracing estava gerando custo
  # (cobranca por trace gravado/recuperado) sem contribuir dado nenhum aos
  # resultados. "PassThrough" e o modo padrao/gratuito (nao gera nem cobra
  # traces por conta propria).
  tracing_config {
    mode = "PassThrough"
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

# ---------------------------------------------------------------------------
# Function URL — pública, sem autenticação. Habilitar apenas em ambientes de
# benchmark/teste; a URL fica acessível por qualquer requisição HTTP.
# ---------------------------------------------------------------------------
resource "aws_lambda_function_url" "this" {
  count = var.enable_function_url ? 1 : 0

  function_name      = aws_lambda_function.this.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
  }
}

resource "aws_lambda_permission" "function_url_public" {
  count = var.enable_function_url ? 1 : 0

  statement_id  = "AllowPublicFunctionUrlInvoke"
  action        = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.this.function_name

  principal              = "*"
  function_url_auth_type = "NONE"
}
