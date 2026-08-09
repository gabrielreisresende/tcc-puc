# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------

output "dynamodb_table_name" {
  description = "Nome da tabela DynamoDB."
  value       = module.dynamodb.table_name
}

output "dynamodb_table_arn" {
  description = "ARN da tabela DynamoDB."
  value       = module.dynamodb.table_arn
}

# ---------------------------------------------------------------------------
# Lambda — nomes e ARNs das 6 funções
# ---------------------------------------------------------------------------

output "lambda_functions" {
  description = "Mapa com nome, ARN e invoke_arn de cada função Lambda."
  value = {
    for key, fn in module.lambda : key => {
      name       = fn.function_name
      arn        = fn.function_arn
      invoke_arn = fn.function_invoke_arn
      role_arn   = fn.role_arn
      log_group  = fn.log_group_name
    }
  }
}

output "lambda_function_names" {
  description = "Nomes das funções Lambda indexados por chave (go-cpu, quarkus-io, etc.)."
  value       = { for key, fn in module.lambda : key => fn.function_name }
}

output "lambda_function_arns" {
  description = "ARNs das funções Lambda indexados por chave."
  value       = { for key, fn in module.lambda : key => fn.function_arn }
}

# ---------------------------------------------------------------------------
# IAM & CloudWatch
# ---------------------------------------------------------------------------

output "lambda_iam_role_arns" {
  description = "ARNs das IAM Roles das Lambdas (menor privilégio por função)."
  value       = { for key, fn in module.lambda : key => fn.role_arn }
}

output "lambda_log_group_names" {
  description = "Nomes dos CloudWatch Log Groups das Lambdas."
  value       = { for key, fn in module.lambda : key => fn.log_group_name }
}
