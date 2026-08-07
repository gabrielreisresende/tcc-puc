locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
  }

  # Chaves das 6 funções Lambda: 3 Go + 3 Quarkus (CPU, Concorrência, I/O).
  lambda_keys = toset([
    "go-cpu",
    "go-concurrency",
    "go-io",
    "quarkus-cpu",
    "quarkus-concurrency",
    "quarkus-io",
  ])

  lambda_metadata = {
    "go-cpu" = {
      runtime_family = "go"
      scenario       = "cpu"
    }
    "go-concurrency" = {
      runtime_family = "go"
      scenario       = "concurrency"
    }
    "go-io" = {
      runtime_family = "go"
      scenario       = "io"
    }
    "quarkus-cpu" = {
      runtime_family = "quarkus"
      scenario       = "cpu"
    }
    "quarkus-concurrency" = {
      runtime_family = "quarkus"
      scenario       = "concurrency"
    }
    "quarkus-io" = {
      runtime_family = "quarkus"
      scenario       = "io"
    }
  }
}

# ---------------------------------------------------------------------------
# DynamoDB — tabela On-Demand para o cenário de I/O.
# ---------------------------------------------------------------------------
module "dynamodb" {
  source = "./modules/dynamodb"

  table_name = var.dynamodb_table_name
  tags       = local.common_tags
}

# ---------------------------------------------------------------------------
# Lambda + IAM + CloudWatch — 6 funções cobrindo os cenários do TCC.
# ---------------------------------------------------------------------------
module "lambda" {
  for_each = local.lambda_keys

  source = "./modules/lambda"

  function_name  = "${local.name_prefix}-${each.key}"
  runtime_family = local.lambda_metadata[each.key].runtime_family
  scenario       = local.lambda_metadata[each.key].scenario

  # Caminho do pacote .zip — definido em var.lambda_deployment_packages.
  # Exemplo: "../build/go-cpu/bootstrap.zip"
  filename = var.lambda_deployment_packages[each.key]

  handler       = lookup(var.lambda_handlers, each.key, var.lambda_default_handler)
  runtime       = var.lambda_runtime
  memory_size   = lookup(var.lambda_memory_sizes, each.key, var.lambda_default_memory_size)
  timeout       = lookup(var.lambda_timeouts, each.key, var.lambda_default_timeout)
  architectures = var.lambda_architectures

  log_retention_days = var.log_retention_days

  enable_dynamodb_access = local.lambda_metadata[each.key].scenario == "io"
  dynamodb_table_arn     = module.dynamodb.table_arn
  dynamodb_table_name    = module.dynamodb.table_name

  environment_variables = lookup(var.lambda_environment_variables, each.key, {})

  tags = local.common_tags
}
