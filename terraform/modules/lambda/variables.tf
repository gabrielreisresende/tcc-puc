variable "function_name" {
  description = "Nome único da função Lambda."
  type        = string
}

variable "runtime_family" {
  description = "Família de runtime do benchmark: go ou quarkus."
  type        = string

  validation {
    condition     = contains(["go", "quarkus"], var.runtime_family)
    error_message = "runtime_family deve ser 'go' ou 'quarkus'."
  }
}

variable "scenario" {
  description = "Cenário de benchmark: cpu, concurrency ou io."
  type        = string

  validation {
    condition     = contains(["cpu", "concurrency", "io"], var.scenario)
    error_message = "scenario deve ser 'cpu', 'concurrency' ou 'io'."
  }
}

variable "filename" {
  description = "Caminho local do pacote .zip contendo o binário da Lambda."
  type        = string
}

variable "handler" {
  description = "Handler da Lambda. Para provided.al2023 use 'bootstrap' (Go/Quarkus nativo)."
  type        = string
  default     = "bootstrap"
}

variable "runtime" {
  description = "Runtime AWS Lambda (ex: provided.al2023 para binários nativos)."
  type        = string
}

variable "memory_size" {
  description = "Memória RAM alocada para a função (MB)."
  type        = number
}

variable "timeout" {
  description = "Timeout máximo de execução (segundos)."
  type        = number
  default     = 30
}

variable "architectures" {
  description = "Arquitetura de CPU da Lambda (ex: [\"x86_64\"] ou [\"arm64\"])."
  type        = list(string)
}

variable "log_retention_days" {
  description = "Retenção dos logs no CloudWatch (dias)."
  type        = number
}

variable "enable_dynamodb_access" {
  description = "Concede permissões de leitura/escrita na tabela DynamoDB (cenário I/O)."
  type        = bool
  default     = false
}

variable "dynamodb_table_arn" {
  description = "ARN da tabela DynamoDB (obrigatório quando enable_dynamodb_access = true)."
  type        = string
  default     = ""
}

variable "dynamodb_table_name" {
  description = "Nome da tabela DynamoDB injetado como variável de ambiente."
  type        = string
  default     = ""
}

variable "environment_variables" {
  description = "Variáveis de ambiente adicionais da Lambda."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags adicionais aplicadas aos recursos."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Function URL — invocação HTTP direta para testes de carga (k6).
# ---------------------------------------------------------------------------

variable "enable_function_url" {
  description = "Cria uma AWS Lambda Function URL pública (AuthType = NONE) para esta função."
  type        = bool
  default     = false
}
