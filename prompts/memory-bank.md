# Memory Bank — TCC Lambda Benchmark (Go vs Quarkus)

> Documento de contexto para continuidade em outras conversas. Descreve o que
> já existe, como está estruturado, o que falta implementar e decisões já
> tomadas — para que outro chat consiga dar sequência sem precisar redescobrir
> nada disso.

---

## 1. Objetivo do projeto

Trabalho de Conclusão de Curso (TCC) que faz uma **análise comparativa de
desempenho e custo** entre runtimes **Go** e **Quarkus (compilado nativamente
via GraalVM/Mandrel)** rodando em **AWS Lambda**.

São avaliados **3 cenários de execução**, cada um implementado nas duas
linguagens (total de 6 Lambdas):

1. **CPU** — processamento intensivo (fatoração de números primos)
2. **Concorrência/Paralelismo** — Goroutines (Go) vs Java Virtual Threads (Quarkus)
3. **I/O** — leitura e escrita no Amazon DynamoDB

Métrica de interesse principal: **cold start**. Inicialmente o plano previa
AWS X-Ray Active Tracing obrigatório para medir isso, mas na prática o
Init Duration (cold start) já vem direto das linhas `REPORT` do CloudWatch
Logs — o X-Ray não contribuía dado nenhum aos resultados e só gerava custo,
então foi desativado em 27/08/2026 (`tracing_config { mode = "PassThrough" }`).

---

## 2. Stack técnica

| Camada | Tecnologia |
|---|---|
| Linguagem/runtime A | Go 1.22, compilado para runtime customizado `provided.al2023` |
| Linguagem/runtime B | Quarkus + GraalVM Mandrel (native/AOT), também `provided.al2023` |
| IaC | Terraform >= 1.5.0 (usando 1.9.x na pipeline) |
| Cloud | AWS (Lambda, DynamoDB, IAM, CloudWatch, S3 para backend) |
| CI/CD | GitHub Actions (migrado de GitLab CI) |
| Autenticação AWS na CI | OIDC (sem access keys de longa duração) |

---

## 3. Estrutura de diretórios (o que já existe)

```
.
├── .github/workflows/
│   ├── deploy.yml          # pipeline principal (validate/build/plan/apply)
│   └── destroy.yml         # pipeline manual de destroy
├── terraform/
│   ├── main.tf              # módulos dynamodb + lambda (for_each nas 6 funções)
│   ├── variables.tf         # todas as variáveis do projeto, com validations
│   ├── outputs.tf           # ARNs/nomes de tudo criado
│   ├── providers.tf         # provider aws + default_tags
│   ├── versions.tf          # required_version >= 1.5.0, aws >= 5.0
│   ├── backend.tf           # backend "s3" {} (config vazia, via -backend-config)
│   ├── backend.hcl.example  # exemplo de backend.hcl local (não versionado)
│   ├── terraform.tfvars.example
│   └── modules/
│       ├── dynamodb/        # tabela On-Demand, PK "id" (String)
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       └── lambda/          # 1 instância por cenário via for_each no root
│           ├── main.tf      # Lambda + IAM Role + policy + Log Group
│           ├── variables.tf
│           └── outputs.tf
├── prompts/
│   ├── terraform.md         # prompt original que gerou o Terraform
│   └── pipelines.md         # prompt original que gerou o GitHub Actions (pt-BR)
└── artigo/
    └── TCC_GabrielResende.pdf
```

> **Ainda não existe** o diretório com o código-fonte das Lambdas
> (`apps/go/{cpu,concurrency,io}` e `apps/quarkus/{cpu,concurrency,io}`), só a
> infraestrutura e a pipeline que já esperam essa estrutura. É o próximo
> passo do projeto.

---

## 4. Terraform — como está modelado

### 4.1 Módulo `dynamodb`
- Tabela `PAY_PER_REQUEST` (On-Demand), PK `id` (String).
- Usada apenas pelas Lambdas do cenário **I/O**.

### 4.2 Módulo `lambda`
- Uma instância por cenário, criada via `for_each` no `main.tf` raiz sobre o
  set `local.lambda_keys`:
  `go-cpu, go-concurrency, go-io, quarkus-cpu, quarkus-concurrency, quarkus-io`
- Cada Lambda recebe:
  - `runtime_family` (`go` | `quarkus`) e `scenario` (`cpu` | `concurrency` | `io`) — só para tags/metadados.
  - `filename` = caminho do `.zip` do binário, vindo de `var.lambda_deployment_packages[each.key]`.
  - `source_code_hash = filebase64sha256(var.filename)` — **importante**: isso
    significa que o Terraform **lê o arquivo do disco** mesmo em operações de
    `destroy`, então qualquer job de pipeline (deploy ou destroy) precisa
    garantir que esses `.zip` existam no runner antes do `terraform plan`.
  - `handler` = `bootstrap` (padrão, sobrescreve por `lambda_handlers` se necessário).
  - `runtime` = `provided.al2023` (único runtime usado, tanto para Go quanto Quarkus nativo).
  - `architectures` = `["x86_64"]` por padrão (configurável para `arm64`).
  - `tracing_config { mode = "PassThrough" }` — X-Ray Active Tracing
    desativado em 27/08/2026 (gerava custo sem contribuir dado usado no TCC;
    o Init Duration/cold start vem das linhas `REPORT` do CloudWatch Logs).
  - IAM Role dedicada por função, com policy base (só CloudWatch Logs) e,
    quando `scenario == "io"`, policy adicional de acesso à tabela DynamoDB
    (`enable_dynamodb_access = true`, controlado automaticamente no `main.tf` raiz).
  - CloudWatch Log Group `/aws/lambda/<function_name>` com retenção parametrizada.
  - **Function URL** pública (`AuthType = NONE`), opcional via `enable_function_url`
    — habilitada no root por `enable_lambda_function_urls` para testes k6.

### 4.3 Variáveis principais (`terraform/variables.tf`)
- `aws_region`, `environment`, `project_name` (compõem `name_prefix = "${project_name}-${environment}"`, usado no nome de todos os recursos).
- `dynamodb_table_name`
- `lambda_runtime` (default esperado: `provided.al2023`)
- `lambda_architectures` (validação: só aceita `x86_64` ou `arm64`)
- `lambda_default_memory_size`, `lambda_default_timeout`, `lambda_default_handler`
- `lambda_memory_sizes` / `lambda_timeouts` / `lambda_handlers` — maps opcionais para sobrescrever por função
- **`lambda_deployment_packages`** — map obrigatório com as 6 chaves exatas
  (`go-cpu`, `go-concurrency`, `go-io`, `quarkus-cpu`, `quarkus-concurrency`,
  `quarkus-io`); há uma `validation` no Terraform que **falha o plan** se
  alguma chave estiver faltando.
- `lambda_environment_variables` — map de map, env vars extras por função.
- `enable_lambda_function_urls` — habilita Function URL pública (AuthType = NONE) nas 6 Lambdas para k6.
- `log_retention_days` — validação: só aceita valores suportados pelo CloudWatch (7, 14, 30, etc.)

### 4.4 Backend remoto
- `backend "s3" {}` vazio no código — toda a configuração (bucket, key,
  region, dynamodb_table, encrypt) vem via `-backend-config` no `terraform init`,
  tanto localmente (`backend.hcl`) quanto na pipeline (secrets do GitHub).
- **O backend (bucket S3 + tabela DynamoDB de lock) não é gerenciado pelo
  Terraform deste projeto** — precisa ser criado manualmente antes do
  primeiro uso (ver seção 7).

### 4.5 Outputs
`terraform/outputs.tf` expõe: nome/ARN da tabela DynamoDB, e para cada
Lambda (indexado por chave `go-cpu`, etc.): nome, ARN, invoke_arn, role_arn,
log_group_name — tudo agregado em maps (`lambda_functions`,
`lambda_function_names`, `lambda_function_arns`, `lambda_iam_role_arns`,
`lambda_log_group_names`, `lambda_function_urls`).

---

## 5. CI/CD — GitHub Actions

### 5.1 `.github/workflows/deploy.yml`

**Triggers:**
- `pull_request` → `main`: roda validate + build + `terraform plan` (sem apply).
- `push` → `main`: roda tudo + `terraform apply -auto-approve`.

**Jobs (nessa ordem/dependência):**

1. **`validate-and-lint`** — checkout, `hashicorp/setup-terraform`, `terraform init -backend=false`, `terraform fmt -check`, `terraform validate`.

2. **`build-go`** — matrix `[cpu, concurrency, io]`. Setup Go 1.22, define `GOARCH`
   a partir de `LAMBDA_ARCHITECTURE` (var), compila com
   `GOOS=linux CGO_ENABLED=0`, `go build -trimpath -ldflags="-s -w" -tags lambda.norpc -o bootstrap .`,
   empacota em `bootstrap.zip`, sobe via `actions/upload-artifact@v4`
   (nome: `go-<scenario>-<sha>`). Espera o código-fonte em `apps/go/<scenario>/`.

3. **`build-quarkus-native`** — matrix `[cpu, concurrency, io]`. Usa
   `docker/setup-buildx-action` (build nativo roda em container Mandrel via
   Docker, sem precisar de runner com GraalVM instalado), cache de `~/.m2`,
   roda `./mvnw package -Pnative -Dquarkus.native.container-build=true
   -Dquarkus.native.container-runtime=docker`, localiza `function.zip` ou
   `*-runner.zip` gerado em `target/`, sobe como artefato
   (`quarkus-<scenario>-<sha>`). Espera o código-fonte em `apps/quarkus/<scenario>/`.

4. **`terraform-plan-apply`** — `needs: [validate-and-lint, build-go, build-quarkus-native]`.
   Baixa os 6 artefatos para os caminhos que o Terraform espera
   (`build/go/{cpu,concurrency,io}`, `build/quarkus/{cpu,concurrency,io}`),
   autentica na AWS via OIDC, monta as `TF_VAR_*` a partir de secrets/vars,
   roda `terraform init` com backend remoto, `terraform plan`, sobe o plano
   como artefato, e só roda `terraform apply -auto-approve` se
   `github.ref == 'refs/heads/main' && github.event_name == 'push'`.

### 5.2 `.github/workflows/destroy.yml`

- **Só manual** (`workflow_dispatch`), nunca dispara em push/PR.
- Input obrigatório `confirm`: usuário precisa digitar exatamente `destroy`,
  validado em job separado (`check-confirmation`) antes de qualquer coisa tocar na AWS.
- `environment: production` — se configurado com *required reviewers* em
  Settings → Environments, adiciona aprovação manual.
- Como `source_code_hash = filebase64sha256(...)` exige os arquivos no disco
  mesmo para destroy, o job **cria 6 arquivos placeholder** (conteúdo
  irrelevante) nos mesmos caminhos usados no deploy antes do `terraform init`.
- Roda `terraform plan -destroy` → sobe o plano como artefato (retenção 30
  dias) → `terraform apply -auto-approve` do plano de destroy.
- **Não apaga** o backend (bucket S3 / tabela DynamoDB de lock) — isso é fora
  do escopo do Terraform e precisa ser feito manualmente se um dia for necessário.

---

## 6. Autenticação AWS via OIDC (já decidido e documentado)

Não se usa `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` como secrets de longa
duração. Em vez disso:

1. **Identity Provider OIDC** criado uma única vez por conta AWS:
   - URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`

2. **IAM Role** (`github-actions-tcc-lambda-benchmark`, nome sugerido) com:
   - **Trust policy** restrita por `sub` a:
     - `repo:<ORG>/<REPO>:ref:refs/heads/main` (para push/apply)
     - `repo:<ORG>/<REPO>:pull_request` (para PRs/plan)
   - **Permissions policy** cobrindo, com `Resource` restrito por prefixo
     (`tcc-lambda-benchmark-*`, `tcc-benchmark-*`):
     - S3 (state): `GetObject/PutObject/DeleteObject/ListBucket` no bucket do state.
     - DynamoDB (lock): `GetItem/PutItem/DeleteItem` na tabela de lock.
     - DynamoDB (benchmark): `CreateTable/DeleteTable/DescribeTable/UpdateTable/Tag*`.
     - Lambda: `CreateFunction/UpdateFunctionCode/UpdateFunctionConfiguration/GetFunction/DeleteFunction/Tag*`.
     - IAM: `CreateRole/DeleteRole/GetRole/Put|DeleteRolePolicy/Tag*/PassRole` (para as roles das próprias Lambdas).
     - CloudWatch Logs: `CreateLogGroup/DeleteLogGroup/DescribeLogGroups/PutRetentionPolicy/Tag*`.
     - `sts:GetCallerIdentity`.

3. No workflow, autenticação via:
   ```yaml
   permissions:
     id-token: write
     contents: read
   ...
   - uses: aws-actions/configure-aws-credentials@v4
     with:
       role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
       aws-region: ${{ secrets.AWS_REGION }}
       role-session-name: github-actions-terraform-${{ github.run_id }}
   ```

**Erro comum já resolvido**: colar a trust policy (que não tem `Resource`)
no lugar de uma permissions policy causa o erro *"Add a Resource or
NotResource element..."*. Trust policy vai em `create-role
--assume-role-policy-document` ou na aba **Trust relationships** da role —
nunca em `create-policy`.

---

## 7. O que precisa existir na AWS *fora* do Terraform (setup manual, uma vez)

1. **Bucket S3** para o state (versionamento + encryption habilitados, acesso público bloqueado).
2. **Tabela DynamoDB** para lock do state — atenção: a PK **precisa se chamar `LockID`** (String), é o nome fixo esperado pelo backend `s3` do Terraform.
3. **OIDC Identity Provider** + **IAM Role** (seção 6).

Tudo o resto (as 6 Lambdas, 6 IAM Roles das Lambdas, 6 Log Groups, tabela
DynamoDB de benchmark) é criado pelo próprio Terraform.

---

## 8. GitHub — Secrets e Variables necessários

### Secrets (Settings → Secrets and variables → Actions → Secrets)
| Nome | Obrigatório | Descrição |
|---|---|---|
| `AWS_ROLE_ARN` | Sim | ARN da role OIDC (substituiu access keys) |
| `AWS_REGION` | Sim | Região AWS |
| `TF_STATE_BUCKET` | Sim | Bucket S3 do backend |
| `TF_STATE_DYNAMODB_TABLE` | Sim | Tabela de lock do state |
| `TF_STATE_KEY` | Não (default `tcc/lambda-benchmark/terraform.tfstate`) | Caminho do state no bucket |

### Variables (aba Variables)
| Nome | Default se ausente |
|---|---|
| `LAMBDA_ARCHITECTURE` | `x86_64` |
| `TF_VAR_ENVIRONMENT` | `dev` |
| `TF_VAR_PROJECT_NAME` | `tcc-lambda-benchmark` |
| `TF_VAR_DYNAMODB_TABLE_NAME` | `tcc-benchmark-io` |
| `TF_VAR_LOG_RETENTION_DAYS` | `7` |
| `TF_VAR_ENABLE_LAMBDA_FUNCTION_URLS` | `false` |

### GitHub Environment
`production` referenciado nos dois workflows — vale configurar *required
reviewers* nele para dar um gate manual antes de `apply`/`destroy` em
produção (Settings → Environments).

---

## 9. Estado atual (o que já está pronto)

- [x] Infraestrutura Terraform completa (DynamoDB + 6 Lambdas + IAM + CloudWatch).
      X-Ray Active Tracing foi desativado em 27/08/2026 (ver seção 1).
- [x] Function URL pública (AuthType = NONE) adicionada ao módulo lambda,
      habilitável via `enable_lambda_function_urls` — usada pelos testes k6.
- [x] Pipeline GitHub Actions de deploy (validate/build/plan/apply) completa.
- [x] Pipeline GitHub Actions de destroy (manual, com confirmação e proteção).
- [x] Decisão e passo a passo de autenticação via OIDC (troca de access keys).
- [x] `.gitlab-ci.yml` obsoleto — deve ser removido do repositório (a migração para GitHub Actions já foi decidida e documentada em `prompts/pipelines.md`).

## 10. Próximos passos (o que falta)

1. **Implementar o código das 6 Lambdas**, que é o próximo grande passo:
   - `apps/go/cpu/`, `apps/go/concurrency/`, `apps/go/io/` — Go, handler compatível com `provided.al2023` (binário `bootstrap`), usando `aws-lambda-go`.
   - `apps/quarkus/cpu/`, `apps/quarkus/concurrency/`, `apps/quarkus/io/` — Quarkus com extensão `quarkus-amazon-lambda`, compilação nativa gerando `function.zip` (ou `*-runner.zip`) em `target/`.
   - Cenário **CPU**: fatoração de números primos (mesma carga de trabalho nas duas linguagens, para comparação justa).
   - Cenário **Concorrência**: Goroutines (Go) vs Java Virtual Threads (Quarkus/Java 21+).
   - Cenário **I/O**: leitura/escrita na tabela DynamoDB — nome da tabela chega via env var `DYNAMODB_TABLE_NAME` (já injetada automaticamente pelo módulo Terraform quando `enable_dynamodb_access = true`).
   - Cada Lambda precisa reportar/expor métricas de cold start de forma consistente entre as duas linguagens (para a análise do TCC).

2. **Popular `terraform.tfvars`** (a partir do `.example`) com valores reais do ambiente, ou configurar via `TF_VAR_*` no CI.

3. **Rodar o setup manual da seção 7** (bucket, tabela de lock, OIDC, role) antes do primeiro `push`/PR que dispare a pipeline.

4. **Primeira execução**: abrir PR para `main` (dispara validate/build/plan) → revisar plano → merge (dispara apply).

5. Possível trabalho futuro de CI/CD: separar builds por scenario/linguagem
   em pipelines independentes se o tempo de build do Quarkus nativo (Docker +
   Mandrel) começar a pesar muito no tempo total; considerar cache adicional
   de camadas Docker.

---

## 11. Convenções e nomenclatura a manter

- Nome de todos os recursos segue `${project_name}-${environment}-<chave>`,
  ex: `tcc-lambda-benchmark-dev-go-cpu`.
- Chaves de cenário são sempre: `go-cpu`, `go-concurrency`, `go-io`,
  `quarkus-cpu`, `quarkus-concurrency`, `quarkus-io` — usadas de forma
  consistente em Terraform (`for_each`), nos artefatos do GitHub Actions
  (`upload-artifact`/`download-artifact`) e em `lambda_deployment_packages`.
  **Não renomear** sem atualizar os três lugares.
- Todo texto de documentação/prompts do projeto está em **pt-BR**; o código
  (Terraform, Go, YAML) segue convenções normais em inglês.
- Nenhum segredo/credencial deve ser hardcoded em nenhum arquivo — sempre via
  `secrets.*`/`vars.*` (GitHub) ou `TF_VAR_*`/`-backend-config` (Terraform).