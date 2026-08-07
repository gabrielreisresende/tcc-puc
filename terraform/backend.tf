# Backend remoto S3 + DynamoDB para lock do estado.
# Valores sensíveis ou específicos do ambiente devem ser passados via -backend-config
# ou arquivo backend.hcl (não versionado).
#
# Exemplo de inicialização:
#   terraform init -backend-config=backend.hcl
#
# Conteúdo sugerido para backend.hcl:
#   bucket         = "seu-bucket-terraform-state"
#   key            = "tcc/lambda-benchmark/terraform.tfstate"
#   region         = "us-east-1"
#   dynamodb_table = "terraform-state-lock"
#   encrypt        = true

terraform {
  backend "s3" {}
}
