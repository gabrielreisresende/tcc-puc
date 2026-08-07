Atue como um Engenheiro DevOps/Cloud SRE especialista em Terraform e AWS. Preciso que você crie os arquivos de Infraestrutura como Código (IaC) em Terraform para implantar o ambiente experimental do meu Trabalho de Conclusão de Curso (TCC).

Contexto da Pesquisa:
O trabalho é uma análise comparativa de desempenho e custo entre runtimes Go e Quarkus (compilado nativamente via GraalVM) rodando na AWS Lambda[cite: 1]. Serão avaliados 3 cenários de execução:
1. Processamento Intensivo de CPU (fatoração de números primos)[cite: 1].
2. Concorrência e Paralelismo (Goroutines vs Java Virtual Threads)[cite: 1].
3. Operações de I/O (Leitura e escrita no Amazon DynamoDB)[cite: 1].

Requisitos da Infraestrutura AWS:
1. Módulo para Amazon DynamoDB:
   - Tabela em modo On-Demand (PAY_PER_REQUEST) para o teste de I/O[cite: 1].
   - Chave primária: `id` (String).

2. Módulo para AWS Lambda:
   - Total de 6 funções Lambda: 3 para Go e 3 para Quarkus (cobrindo os cenários CPU, Concorrência e I/O)[cite: 1].
   - Arquitetura de CPU parametrizável (ex: x86_64 ou arm64).
   - Runtime configurável (ex: `provided.al2023` para binários nativos de Go e Quarkus).
   - Configuração de Memória RAM parametrizável por variável.
   - Ativação obrigatória do AWS X-Ray Active Tracing (`tracing_config { mode = "Active" }`) para medição detalhada de Cold Start[cite: 1].

3. Módulo de Segurança e Observabilidade (IAM & CloudWatch):
   - IAM Roles e IAM Policies com o princípio do menor privilégio para cada Lambda.
   - Permissões necessárias: Escrita no CloudWatch Logs, escrita no AWS X-Ray Tracing e acesso de leitura/escrita na tabela DynamoDB (para as Lambdas de I/O)[cite: 1].
   - CloudWatch Log Groups explicitamente criados para cada Lambda com tempo de retenção parametrizado (ex: 7 dias)[cite: 1].

4. Organização do Código Terraform:
   - `main.tf`: Chamada dos módulos e recursos principais.
   - `variables.tf`: Definição de todas as variáveis do projeto (região, ambiente, memória das lambdas, nome do banco, etc.). NENHUM valor sensível ou fixo (hardcoded).
   - `outputs.tf`: Exportação dos ARNs e URLs/Nomes das funções Lambdas e da tabela DynamoDB.
   - `terraform.tfvars.example`: Exemplo de preenchimento das variáveis não sensíveis.
   - `backend.tf`: Configuração do Backend S3/DynamoDB para guardar o estado (`tfstate`) remotamente.

Regras de Parametrização e Segurança:
- Use variáveis de ambiente padrão do Terraform para dados sensíveis ou específicos (ex: `TF_VAR_aws_region`).
- Adicione comentários explicando onde colar o caminho do pacote/zip de cada binário das Lambdas.
- Garanta sintaxe válida para Terraform >= 1.5.0.