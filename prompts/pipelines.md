Atue como especialista em CI/CD com foco em GitLab CI e automação de infraestrutura AWS com Terraform. Preciso que crie o arquivo `.gitlab-ci.yml` para automatizar o build das funções Lambda (Go e Quarkus) e o deploy da infraestrutura Terraform na AWS.

Requisitos da Pipeline:
1. Estágios da Pipeline (`stages`):
   - `validate`: Validação e lint do código Terraform.
   - `build`: Compilação dos binários das aplicações (Go e Quarkus em modo Native com GraalVM/Docker) e empacotamento em `.zip`.
   - `plan`: Execução do `terraform plan` gerando um artefato do plano de execução.
   - `apply`: Deploy automático da infraestrutura via `terraform apply` quando houver push ou merge na branch `main`.

2. Requisitos dos Jobs:
   - Utilizar imagens Docker oficiais e leves para cada etapa (ex: `hashicorp/terraform:latest`, `golang:1.22`, `quay.io/quarkus/ubi-quarkus-mandrel-builder-image`).
   - Job de `build-go`: Compila os 3 cenários Go para a arquitetura alvo (Linux/arm64 ou x86_64) gerando o executável `bootstrap` empacotado em ZIP.
   - Job de `build-quarkus`: Executa o build nativo Ahead-Of-Time (AOT) do Quarkus (ex: `./mvnw package -Pnative -Dquarkus.native.container-build=true`) gerando os ZIPs nativos.
   - O armazenamento dos artefatos (`.zip` gerados e o plano do terraform) deve ser passado entre os estágios via `artifacts` do GitLab CI.

3. Segurança e Variáveis de Ambiente:
   - NENHUMA chave de acesso AWS ou segredo deve estar visível no código.
   - Configure o código para utilizar as variáveis mascaradas e protegidas do GitLab CI/CD:
     * `AWS_ACCESS_KEY_ID`
     * `AWS_SECRET_ACCESS_KEY`
     * `AWS_DEFAULT_REGION`
   - Configure o Terraform para ler essas variáveis automaticamente do ambiente.

4. Regras de Execução (`rules`):
   - Estágios `validate`, `build` e `plan` devem rodar em Merge Requests e branches.
   - O estágio `apply` deve rodar AUTOMATICAMENTE apenas quando os commits forem aplicados na branch `main`.

Forneça a estrutura completa do arquivo `.gitlab-ci.yml` com comentários explicativos de cada seção e instruções de como cadastrar as variáveis de ambiente no painel do GitLab CI (Settings > CI/CD > Variables).