Plano de Implementação — Lambda Function URLs (sem autenticação)

Documento para ser executado pelo Cursor. Objetivo: expor as 6 Lambdas via AWS Lambda Function URL (AuthType = NONE, acesso público) para que o k6 consiga chamá-las diretamente via HTTP, sem API Gateway e sem necessidade de assinatura/autenticação nas requisições.

Contexto
Infra atual: 6 Lambdas (Go + Quarkus) via módulo terraform/modules/lambda, sem nenhum mecanismo de invocação HTTP pública.
Suíte de testes de carga já existe em k6/ mas depende de URLs (URL_GO_CPU, etc.) que ainda não existem.
Decisão: usar Function URL em vez de API Gateway (menos overhead na métrica de cold start, menos custo/IaC).
Sem autenticação: authorization_type = "NONE". Isso deixa o endpoint publicamente acessível por qualquer um que descubra a URL. Aceitável apenas porque é um ambiente de benchmark/TCC descartável — não usar esse padrão em produção.
Passo 1 — terraform/modules/lambda/variables.tf

Adicionar ao final do arquivo:

hcl
# ---------------------------------------------------------------------------
# Function URL — invocação HTTP direta para testes de carga (k6).
# ---------------------------------------------------------------------------

variable "enable_function_url" {
  description = "Cria uma AWS Lambda Function URL pública (AuthType = NONE) para esta função."
  type        = bool
  default     = false
}
Passo 2 — terraform/modules/lambda/main.tf

Adicionar ao final do arquivo:

hcl
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

  principal               = "*"
  function_url_auth_type  = "NONE"
}
Passo 3 — terraform/modules/lambda/outputs.tf

Adicionar ao final do arquivo:

hcl
output "function_url" {
  description = "URL de invocação direta da função (null se enable_function_url = false)."
  value       = try(aws_lambda_function_url.this[0].function_url, null)
}
Passo 4 — terraform/variables.tf (raiz)

Adicionar:

hcl
# ---------------------------------------------------------------------------
# Function URL — testes de carga (k6)
# ---------------------------------------------------------------------------

variable "enable_lambda_function_urls" {
  description = "Habilita Function URL pública (AuthType = NONE) nas 6 Lambdas para uso pelo k6."
  type        = bool
  default     = false
}
Passo 5 — terraform/main.tf (raiz)

Dentro do bloco module "lambda" existente, adicionar a linha (sem remover nada do que já está lá):

hcl
module "lambda" {
  for_each = local.lambda_keys

  source = "./modules/lambda"

  # ... manter todos os argumentos já existentes ...

  enable_function_url = var.enable_lambda_function_urls
}
Passo 6 — terraform/outputs.tf (raiz)

Adicionar:

hcl
output "lambda_function_urls" {
  description = "URLs de invocação (Function URL) das Lambdas, indexadas por chave (go-cpu, quarkus-io, etc.)."
  value       = { for key, fn in module.lambda : key => fn.function_url }
}
Passo 7 — terraform/terraform.tfvars.example

Adicionar ao final:

hcl
# Habilita Function URL pública (sem autenticação) para as 6 Lambdas.
# Necessário para os testes de carga em k6/. Endpoint fica acessível
# publicamente enquanto habilitado — desabilite fora de janelas de teste.
enable_lambda_function_urls = true
Passo 8 — Pipeline .github/workflows/deploy.yml

Adicionar a variável de ambiente no bloco "Definir variáveis do Terraform derivadas do ambiente" (job terraform-plan-apply), junto às demais TF_VAR_*:

yaml
echo "TF_VAR_enable_lambda_function_urls=${{ vars.TF_VAR_ENABLE_LAMBDA_FUNCTION_URLS || 'false' }}" >> "$GITHUB_ENV"

Isso deixa o comportamento padrão desligado em CI/CD (produção), habilitável via GitHub Variable TF_VAR_ENABLE_LAMBDA_FUNCTION_URLS=true quando quiser rodar benchmark a partir de um ambiente implantado pela pipeline.

Passo 9 — k6/README.md e k6/.env.example

Atualizar a seção de pré-requisitos para deixar claro que as URLs vêm direto do output do Terraform, sem qualquer proxy de assinatura:

md
## Obtendo as URLs

Após `terraform apply` com `enable_lambda_function_urls = true`:

    terraform output -json lambda_function_urls

Copie os valores para as variáveis URL_GO_CPU, URL_GO_PARALLEL, URL_GO_IO,
URL_QUARKUS_CPU, URL_QUARKUS_PARALLEL, URL_QUARKUS_IO — sem necessidade de
autenticação ou assinatura adicional nas chamadas.

Nenhuma mudança de código é necessária em k6/config/env.js ou k6/lib/endpoints.js — eles já fazem http.post simples, que funciona diretamente contra a Function URL pública.

Passo 10 — prompts/memory-bank.md

Atualizar a seção 9 (Estado atual) e 10 (Próximos passos) para refletir:

md
- [x] Function URL pública (AuthType = NONE) adicionada ao módulo lambda,
      habilitável via `enable_lambda_function_urls` — usada pelos testes k6.

E remover/ajustar qualquer menção futura a API Gateway como pendência, já que a decisão foi por Function URL.

Checklist de validação (rodar após as mudanças)
terraform fmt -recursive no diretório terraform/.
terraform validate.
terraform plan local com -var="enable_lambda_function_urls=true" — conferir que aparecem 6× aws_lambda_function_url + 6× aws_lambda_permission novos, sem ~ (drift) em recursos já existentes.
Após apply: terraform output -json lambda_function_urls deve retornar 6 URLs no formato https://<url-id>.lambda-url.<region>.on.aws/.
curl -X POST -H "Content-Type: application/json" -d '{}' <uma-das-urls> deve responder 200 sem exigir header de autenticação.
Rodar k6 run -e URL_GO_CPU=... -e TARGETS=go-cpu --vus 1 --duration 10s load.js (smoke test) para confirmar que o k6 consegue chamar sem qualquer proxy.