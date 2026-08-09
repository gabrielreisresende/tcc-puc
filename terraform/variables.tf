# ---------------------------------------------------------------------------
# Configuração geral
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "Região AWS de implantação. Pode ser definida via TF_VAR_aws_region."
  type        = string
}

variable "environment" {
  description = "Ambiente de implantação (ex: dev, staging, prod)."
  type        = string
}

variable "project_name" {
  description = "Nome do projeto usado como prefixo de recursos."
  type        = string
}

# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------

variable "dynamodb_table_name" {
  description = "Nome da tabela DynamoDB para o benchmark de I/O."
  type        = string
}

# ---------------------------------------------------------------------------
# Lambda — configuração compartilhada
# ---------------------------------------------------------------------------

variable "lambda_runtime" {
  description = "Runtime AWS Lambda. Use provided.al2023 para binários nativos Go/Quarkus."
  type        = string
}

variable "lambda_architectures" {
  description = "Arquitetura de CPU das Lambdas (x86_64 ou arm64)."
  type        = list(string)

  validation {
    condition = alltrue([
      for arch in var.lambda_architectures : contains(["x86_64", "arm64"], arch)
    ])
    error_message = "Arquiteturas permitidas: x86_64 ou arm64."
  }
}

variable "lambda_default_handler" {
  description = "Handler padrão para runtimes customizados (provided.al2023)."
  type        = string
  default     = "bootstrap"
}

variable "lambda_default_memory_size" {
  description = "Memória RAM padrão (MB) quando não especificada por função."
  type        = number

  validation {
    condition     = var.lambda_default_memory_size >= 128 && var.lambda_default_memory_size <= 10240
    error_message = "Memória deve estar entre 128 e 10240 MB."
  }
}

variable "lambda_default_timeout" {
  description = "Timeout padrão (segundos) quando não especificado por função."
  type        = number
  default     = 30
}

variable "lambda_memory_sizes" {
  description = "Memória RAM (MB) por função. Chaves: go-cpu, go-concurrency, go-io, quarkus-cpu, quarkus-concurrency, quarkus-io."
  type        = map(number)
  default     = {}
}

variable "lambda_timeouts" {
  description = "Timeout (segundos) por função."
  type        = map(number)
  default     = {}
}

variable "lambda_handlers" {
  description = "Handler por função (sobrescreve lambda_default_handler)."
  type        = map(string)
  default     = {}
}

# Caminhos locais dos pacotes .zip — NÃO incluir segredos aqui.
# Cada valor aponta para o artefato compilado da respectiva Lambda.
variable "lambda_deployment_packages" {
  description = <<-EOT
    Mapa com o caminho local do .zip de cada função Lambda.
    Chaves obrigatórias: go-cpu, go-concurrency, go-io, quarkus-cpu, quarkus-concurrency, quarkus-io.

    Exemplos de caminhos (ajuste conforme seu pipeline de build):
      go-cpu              -> "../build/go/cpu/bootstrap.zip"
      go-concurrency      -> "../build/go/concurrency/bootstrap.zip"
      go-io               -> "../build/go/io/bootstrap.zip"
      quarkus-cpu         -> "../build/quarkus/cpu/function.zip"
      quarkus-concurrency -> "../build/quarkus/concurrency/function.zip"
      quarkus-io          -> "../build/quarkus/io/function.zip"
  EOT
  type        = map(string)

  validation {
    condition = alltrue([
      for key in [
        "go-cpu",
        "go-concurrency",
        "go-io",
        "quarkus-cpu",
        "quarkus-concurrency",
        "quarkus-io",
      ] : contains(keys(var.lambda_deployment_packages), key)
    ])
    error_message = "lambda_deployment_packages deve conter as 6 chaves: go-cpu, go-concurrency, go-io, quarkus-cpu, quarkus-concurrency, quarkus-io."
  }
}

variable "lambda_environment_variables" {
  description = "Variáveis de ambiente adicionais por função Lambda."
  type        = map(map(string))
  default     = {}
}

# ---------------------------------------------------------------------------
# Observabilidade
# ---------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Retenção dos CloudWatch Log Groups das Lambdas (dias)."
  type        = number

  validation {
    condition = contains([
      0, 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653
    ], var.log_retention_days)
    error_message = "Valor de retenção deve ser um valor suportado pelo CloudWatch Logs."
  }
}
