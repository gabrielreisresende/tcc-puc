Atue como especialista em DevOps/SRE com foco em GitHub Actions e automação de infraestrutura AWS com Terraform. Preciso que crie a estrutura completa de pipeline de CI/CD em arquivos de workflow do GitHub Actions (localizados em .github/workflows/) para automatizar o build das funções Lambda (Go e Quarkus) e o deploy da infraestrutura Terraform na AWS.

Contexto da Aplicação:
- 3 Lambdas em Go (CPU, Concorrência, I/O)[cite: 1].
- 3 Lambdas em Quarkus compiladas em executável nativo AOT via GraalVM (CPU, Concorrência, I/O)[cite: 1].
- Infraestrutura provisionada via Terraform[cite: 1].

Requisitos do Workflow (`.github/workflows/deploy.yml`):

1. Triggers de Execução (`on`):
   - Disparo por `pull_request` apontando para a branch `main`: executa validação, build e `terraform plan`.
   - Disparo por `push` na branch `main`: executa o fluxo completo e aplica o `terraform apply` automaticamente.

2. Trabalhos (Jobs) e Etapas Sequenciais:
   - Job 1: `validate-and-lint`
     * Checkout do código.
     * Configuração do Terraform.
     * `terraform init` e `terraform validate`.

   - Job 2: `build-go`
     * Setup do Go.
     * Compilação dos 3 cenários Go para a arquitetura alvo (ex: Linux/arm64 ou x86_64, gerando o executável `bootstrap` exigido pelo runtime `provided.al2023`).
     * Empacotamento dos binários em arquivos `.zip`.
     * Upload dos artefatos utilizando `actions/upload-artifact`.

   - Job 3: `build-quarkus-native`
     * Setup de ambiente com Suporte a Container/Docker ou GraalVM Mandrel Builder image.
     * Compilação nativa Ahead-Of-Time (AOT) do Quarkus (ex: `./mvnw package -Pnative -Dquarkus.native.container-build=true`).
     * Empacotamento dos binários em arquivos `.zip`.
     * Upload dos artefatos utilizando `actions/upload-artifact`.

   - Job 4: `terraform-plan-apply`
     * Depende dos jobs anteriores (`needs: [validate-and-lint, build-go, build-quarkus-native]`).
     * Download de todos os artefatos `.zip` para o diretório esperado pelo Terraform.
     * Autenticação na AWS utilizando `aws-actions/configure-aws-credentials`.
     * `terraform init` e `terraform plan`.
     * Execução automática do `terraform apply -auto-approve` APENAS se o evento for um `push` na branch `main` (`github.ref == 'refs/heads/main' && github.event_name == 'push'`).

3. Gerenciamento de Segredos e Segurança:
   - NENHUMA chave de acesso AWS ou variável sensível pode estar hardcoded no repositório.
   - O workflow deve consumir segredos configurados em `GitHub Secrets` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`).

Forneça o código YAML completo do workflow com comentários explicativos em cada etapa e inclua uma instrução de como cadastrar as Secret Variables no repositório do GitHub (Settings > Secrets and variables > Actions).