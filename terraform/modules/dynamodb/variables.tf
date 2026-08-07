variable "table_name" {
  description = "Nome da tabela DynamoDB para o cenário de I/O."
  type        = string
}

variable "tags" {
  description = "Tags adicionais aplicadas à tabela."
  type        = map(string)
  default     = {}
}
