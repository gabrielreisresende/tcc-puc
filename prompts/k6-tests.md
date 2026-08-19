Contexto:
Estou desenvolvendo o meu Trabalho de Conclusão de Curso (TCC) que compara o desempenho e custo de funções Serverless desenvolvidas em Go e Quarkus na AWS Lambda. Já finalizei o deploy da infraestrutura (via Terraform) e o desenvolvimento das lambdas. Agora preciso criar a suíte de testes de carga utilizando o K6.

Requisitos do Projeto K6:
Preciso que você estruture um projeto K6 modular para realizar requisições HTTP para os endpoints expostos pelo meu AWS API Gateway.
Para garantir a flexibilidade, o projeto deve ser altamente parametrizado via variáveis de ambiente (__ENV):

URLs das Lambdas: As URLs específicas de cada uma das 6 funções Lambda devem ser injetadas por variáveis separadas (ex: URL_GO_CPU, URL_GO_PARALLEL, URL_GO_IO, URL_QUARKUS_CPU, URL_QUARKUS_PARALLEL, URL_QUARKUS_IO). O script deve ser capaz de executar os testes para as 6 lambdas (ou permitir selecionar qual testar via parâmetro).

Carga de Execução: A quantidade de execuções/carga (como número de VUs no pico, VUs em regime estável e durações dos estágios) também deve ser parametrizada via variáveis de ambiente/

Dimensão 1: Endpoints a serem testados
Temos um total de 6 Lambdas (3 em Go e 3 em Quarkus), divididas em 3 cenários de estresse computacional. O K6 deve ter funções de requisição prontas para cada caso:

Rota de CPU: Executa um algoritmo de fatoração de números primos.

Rota de Concorrência: Processa e agrupa lotes de dados simulando paralelismo (Goroutines / Virtual Threads).

Rota de I/O: Realiza leitura e escrita no AWS DynamoDB.

Dimensão 2: Perfis de Carga (Configuração do options do K6)
Precisamos de dois arquivos de teste distintos (ou configurações separadas de scenarios), refletindo a minha metodologia de pesquisa, consumindo as variáveis de ambiente de carga:

Teste de Pico (Spike Testing - Foco em Cold Start): O objetivo é forçar a plataforma a instanciar novos contêineres do zero. A configuração de estágios (stages) do K6 deve ter períodos prolongados de inatividade (taxa 0) intercalados com injeções massivas, abruptas e curtas de requisições.

Teste de Carga (Load Testing - Foco em Warm Start): O objetivo é manter os contêineres aquecidos e avaliar o regime estável. A configuração deve simular alta concorrência contínua (ramp-up moderado, platô longo com alta carga, ramp-down).

Tarefas solicitadas:

Analise a estrutura dos projetos para saber como estruturar esses testes de carga

Crie a estrutura de diretórios e arquivos ideal para organizar esses testes no K6 (ex: separando cenários, payloads de configuração, chamadas HTTP e centralização de variáveis).

Gere o código JavaScript para as chamadas HTTP cobrindo as 6 lambdas, mapeando corretamente as variáveis de ambiente das URLs.

Gere os dois cenários de execução (Spike e Load) utilizando a API de scenarios ou options.stages do K6, aplicando as variáveis de ambiente que definem a intensidade da carga.

Adicione checks (validações de status 200) e custom metrics (ex: tags por linguagem e por tipo de rota para facilitar a visualização no relatório e comparar Go vs Quarkus).

Crie um README.md completo com instruções claras de como rodar os testes via linha de comando, mostrando um exemplo prático que passe todas as variáveis de ambiente (as 6 URLs e os parâmetros de carga).
