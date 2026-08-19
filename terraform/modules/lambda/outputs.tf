output "function_name" {
  description = "Nome da função Lambda."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN da função Lambda."
  value       = aws_lambda_function.this.arn
}

output "function_invoke_arn" {
  description = "ARN de invocação da função Lambda."
  value       = aws_lambda_function.this.invoke_arn
}

output "role_arn" {
  description = "ARN da IAM Role associada à função."
  value       = aws_iam_role.lambda.arn
}

output "role_name" {
  description = "Nome da IAM Role associada à função."
  value       = aws_iam_role.lambda.name
}

output "log_group_name" {
  description = "Nome do CloudWatch Log Group."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "log_group_arn" {
  description = "ARN do CloudWatch Log Group."
  value       = aws_cloudwatch_log_group.lambda.arn
}

output "function_url" {
  description = "URL de invocação direta da função (null se enable_function_url = false)."
  value       = try(aws_lambda_function_url.this[0].function_url, null)
}
