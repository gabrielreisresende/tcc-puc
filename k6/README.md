# K6 — Testes de Carga TCC Lambda Benchmark

Suíte modular de testes de carga com [K6](https://k6.io/) para comparar o desempenho das 6 funções AWS Lambda (Go vs Quarkus) nos cenários **CPU**, **Concorrência** e **I/O**.

## Estrutura do projeto

```
k6/
├── README.md
├── spike.js              # Entry point — teste de pico (cold start)
├── load.js               # Entry point — teste de carga (warm start)
├── .env.example          # Referência de variáveis de ambiente
├── config/
│   └── env.js            # Leitura centralizada de __ENV
└── lib/
    ├── endpoints.js      # Chamadas HTTP e checks
    ├── metrics.js        # Métricas customizadas
    └── scenarios.js      # Montagem dos scenarios K6
```

## Pré-requisitos

- [K6](https://grafana.com/docs/k6/latest/set-up/install-k6/) instalado localmente
- URLs HTTP públicas das 6 Lambdas via **Lambda Function URL** (Terraform: `enable_lambda_function_urls = true`)
- Lambdas implantadas e acessíveis via `POST` com corpo JSON — **sem autenticação ou assinatura adicional**

## Obtendo as URLs

Após `terraform apply` com `enable_lambda_function_urls = true`:

```bash
terraform output -json lambda_function_urls
```

Copie os valores para as variáveis `URL_GO_CPU`, `URL_GO_PARALLEL`, `URL_GO_IO`,
`URL_QUARKUS_CPU`, `URL_QUARKUS_PARALLEL`, `URL_QUARKUS_IO` — sem necessidade de
autenticação ou assinatura adicional nas chamadas.

| Chave Terraform | Variável k6 |
|---|---|
| `go-cpu` | `URL_GO_CPU` |
| `go-concurrency` | `URL_GO_PARALLEL` |
| `go-io` | `URL_GO_IO` |
| `quarkus-cpu` | `URL_QUARKUS_CPU` |
| `quarkus-concurrency` | `URL_QUARKUS_PARALLEL` |
| `quarkus-io` | `URL_QUARKUS_IO` |

Formato esperado: `https://<url-id>.lambda-url.<region>.on.aws/`

## Endpoints testados

| Target | Variável de ambiente | Cenário | Payload |
|---|---|---|---|
| `go-cpu` | `URL_GO_CPU` | Fatoração de primos | `{"number": 999999999989}` |
| `go-parallel` | `URL_GO_PARALLEL` | Goroutines | `{"tasks": 5000}` |
| `go-io` | `URL_GO_IO` | DynamoDB R/W | `{}` |
| `quarkus-cpu` | `URL_QUARKUS_CPU` | Fatoração de primos | `{"number": 999999999989}` |
| `quarkus-parallel` | `URL_QUARKUS_PARALLEL` | Virtual Threads | `{"tasks": 5000}` |
| `quarkus-io` | `URL_QUARKUS_IO` | DynamoDB R/W | `{}` |

## Perfis de teste

### Spike (`spike.js`) — Cold Start

Simula períodos longos de inatividade (0 VUs) intercalados com picos abruptos de carga. Objetivo: forçar a plataforma a instanciar novos contêineres.

| Variável | Padrão | Descrição |
|---|---|---|
| `SPIKE_IDLE_DURATION` | `5m` | Duração de cada período de inatividade |
| `SPIKE_SPIKE_DURATION` | `30s` | Duração de cada pico de carga |
| `SPIKE_PEAK_VUS` | `100` | VUs no pico |
| `SPIKE_CYCLES` | `3` | Quantidade de ciclos idle → spike |

### Load (`load.js`) — Warm Start

Mantém alta concorrência contínua para avaliar o regime estável com contêineres aquecidos.

| Variável | Padrão | Descrição |
|---|---|---|
| `LOAD_RAMP_UP_DURATION` | `2m` | Ramp-up inicial |
| `LOAD_STEADY_DURATION` | `10m` | Platô com carga constante |
| `LOAD_RAMP_DOWN_DURATION` | `2m` | Ramp-down final |
| `LOAD_STEADY_VUS` | `50` | VUs em regime estável |

## Seleção de targets

Por padrão, todos os 6 endpoints são testados em paralelo (um scenario K6 por Lambda).

Para testar apenas um subconjunto:

```bash
TARGETS=go-cpu,quarkus-cpu k6 run spike.js
```

Valores aceitos: `go-cpu`, `go-parallel`, `go-io`, `quarkus-cpu`, `quarkus-parallel`, `quarkus-io`, ou `all`.

## Métricas e tags

Cada requisição HTTP recebe tags para facilitar a comparação Go vs Quarkus no relatório:

- `language`: `go` ou `quarkus`
- `route`: `cpu`, `parallel` ou `io`
- `target`: chave completa (ex: `go-cpu`)
- `test_profile`: `spike` ou `load`

**Checks aplicados:**

- Status HTTP 200
- Resposta com corpo não vazio

**Métricas customizadas:**

- `lambda_duration` — Trend da duração por tag
- `lambda_success` — Rate de sucesso (checks)
- `lambda_requests` — Counter de requisições

## Como executar

### Exemplo completo — Spike (6 URLs + parâmetros de carga)

```bash
k6 run \
  -e URL_GO_CPU="https://abc123.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_PARALLEL="https://def456.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_IO="https://ghi789.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CPU="https://jkl012.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_PARALLEL="https://mno345.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_IO="https://pqr678.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=all \
  -e SPIKE_IDLE_DURATION=5m \
  -e SPIKE_SPIKE_DURATION=30s \
  -e SPIKE_PEAK_VUS=100 \
  -e SPIKE_CYCLES=3 \
  -e PAYLOAD_CPU_NUMBER=999999999989 \
  -e PAYLOAD_PARALLEL_TASKS=5000 \
  spike.js
```

### Exemplo completo — Load (warm start)

```bash
k6 run \
  -e URL_GO_CPU="https://abc123.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_PARALLEL="https://def456.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_IO="https://ghi789.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CPU="https://jkl012.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_PARALLEL="https://mno345.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_IO="https://pqr678.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=all \
  -e LOAD_RAMP_UP_DURATION=2m \
  -e LOAD_STEADY_DURATION=10m \
  -e LOAD_RAMP_DOWN_DURATION=2m \
  -e LOAD_STEADY_VUS=50 \
  load.js
```

### Smoke test rápido (1 VU, 10s)

Útil para validar conectividade antes de rodar a bateria completa:

```bash
k6 run \
  -e URL_GO_CPU="https://..." \
  -e TARGETS=go-cpu \
  --vus 1 --duration 10s \
  load.js
```

> Para smoke tests ad hoc, as flags `--vus` e `--duration` da CLI sobrescrevem temporariamente os scenarios definidos no script.

### Exportar resultados

```bash
# JSON para pós-processamento
k6 run --out json=results/spike.json spike.js

# CSV
k6 run --out csv=results/spike.csv spike.js
```

## Variáveis opcionais adicionais

| Variável | Padrão | Descrição |
|---|---|---|
| `PAYLOAD_CPU_NUMBER` | `999999999989` | Número para fatoração (CPU) |
| `PAYLOAD_PARALLEL_TASKS` | `5000` | Quantidade de tasks/goroutines |
| `HTTP_TIMEOUT` | `60s` | Timeout por requisição HTTP |
| `GRACEFUL_RAMP_DOWN` | `30s` | Tempo de ramp-down gracioso |
| `THRESHOLD_HTTP_FAIL_RATE` | `0.05` | Limite de taxa de falha HTTP |
| `THRESHOLD_SUCCESS_RATE` | `0.95` | Limite mínimo de sucesso |
| `THRESHOLD_P95_GO_MS` | `30000` | p95 máximo para Go (ms) |
| `THRESHOLD_P95_QUARKUS_MS` | `30000` | p95 máximo para Quarkus (ms) |

Consulte `.env.example` para a lista completa.

## Interpretação dos resultados

Compare as métricas segmentadas por tag no sumário final do K6:

```
http_req_duration..............: avg=XXXms  p(95)=XXXms
  { language:go, route:cpu }...: avg=XXXms  p(95)=XXXms
  { language:quarkus, route:cpu }: avg=XXXms  p(95)=XXXms
```

No perfil **Spike**, latências elevadas nos primeiros segundos após cada idle indicam cold start. No perfil **Load**, latências estáveis ao longo do platô indicam warm start.

## Notas

- As Lambdas esperam requisições `POST` com `Content-Type: application/json`.
- O Terraform provisiona **Lambda Function URL** pública (`AuthType = NONE`) quando `enable_lambda_function_urls = true`. Obtenha as URLs via `terraform output -json lambda_function_urls` e passe-as nas variáveis `URL_*`.
- Desabilite as Function URLs fora de janelas de teste — os endpoints ficam publicamente acessíveis enquanto habilitados.
- Ajuste `SPIKE_PEAK_VUS` e `LOAD_STEADY_VUS` conforme os limites de concorrência da sua conta AWS.
