# Testes de Performance com K6

## Pré-requisitos

- [K6](https://grafana.com/docs/k6/latest/set-up/install-k6/) instalado localmente
- URLs HTTP públicas das 6 Lambdas (Function URL)
- Lambdas implantadas e acessíveis via `POST` com corpo JSON

## Endpoints testados


| Target                | URL                                                                     | Cenário             | Payload                    |
| --------------------- | ----------------------------------------------------------------------- | ------------------- | -------------------------- |
| `go-concurrency`      | `https://mrdrtaib4l2rmlgjzl6mlyyz3i0ubqug.lambda-url.us-east-1.on.aws/` | Concorrência        | `{"tasks": 5000}`          |
| `go-cpu`              | `https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/` | Fatoração de primos | `{"number": 999999999989}` |
| `go-io`               | `https://qssbxz636rm46rka7yk4xqhivy0fzhcc.lambda-url.us-east-1.on.aws/` | DynamoDB R/W        | `{}`                       |
| `quarkus-concurrency` | `https://jr5yv5l6qk66ly26zw7kh3m2qy0gxycq.lambda-url.us-east-1.on.aws/` | Concorrência        | `{"tasks": 5000}`          |
| `quarkus-cpu`         | `https://gjgjwhul6bi6ranv2trses7cbu0nocat.lambda-url.us-east-1.on.aws/` | Fatoração de primos | `{"number": 999999999989}` |
| `quarkus-io`          | `https://aopawemhehbwyhoxuxebbr56tq0fjvqq.lambda-url.us-east-1.on.aws/` | DynamoDB R/W        | `{}`                       |




## Perfis de teste

Cada perfil é um **entry point independente** (`spike.js` e `load.js`). Eles nunca devem rodar ao mesmo tempo contra as mesmas Lambdas — veja [Ordem de execução recomendada](#ordem-de-execução-recomendada) abaixo.

### Spike (`spike.js`) — Cold Start

Simula períodos longos de inatividade (0 VUs) intercalados com picos abruptos de carga. Objetivo: forçar a plataforma a instanciar novos contêineres.


| Variável               | Padrão | Descrição                              |
| ---------------------- | ------ | -------------------------------------- |
| `SPIKE_IDLE_DURATION`  | `5m`   | Duração de cada período de inatividade |
| `SPIKE_SPIKE_DURATION` | `30s`  | Duração de cada pico de carga          |
| `SPIKE_PEAK_VUS`       | `100`  | VUs no pico                            |
| `SPIKE_CYCLES`         | `3`    | Quantidade de ciclos idle → spike      |




### Load (`load.js`) — Warm Start

Mantém alta concorrência contínua para avaliar o regime estável com contêineres aquecidos.


| Variável                  | Padrão | Descrição                 |
| ------------------------- | ------ | ------------------------- |
| `LOAD_RAMP_UP_DURATION`   | `2m`   | Ramp-up inicial           |
| `LOAD_STEADY_DURATION`    | `10m`  | Platô com carga constante |
| `LOAD_RAMP_DOWN_DURATION` | `2m`   | Ramp-down final           |
| `LOAD_STEADY_VUS`         | `50`   | VUs em regime estável     |




## Ordem de execução recomendada

Spike e Load **competem pelos mesmos containers Lambda**. Rodar os dois ao mesmo tempo (ou muito próximos) contamina a métrica de cold start: containers deixados "quentes" por um teste são potencialmente reaproveitados pelo outro.

Ordem recomendada:

1. **Rode o Spike primeiro**, logo após um deploy/redeploy (ambiente "frio" por padrão).
2. **Aguarde um intervalo de resfriamento** de pelo menos **15–30 minutos sem nenhum tráfego** nas Lambdas antes do próximo teste. O tempo exato de reciclagem de container não é documentado pela AWS, então esse intervalo é uma margem de segurança, não uma garantia.
3. **Rode o Load depois**, isoladamente.
4. Nunca dispare os dois scripts em paralelo (mesmo em terminais diferentes) contra o mesmo conjunto de Lambdas.
5. Anote os horários de início/fim de cada execução — facilita cruzar com o CloudWatch Logs depois, caso apareça alguma anomalia (o X-Ray Active Tracing foi desativado em 27/08/2026, ver `terraform/modules/lambda/main.tf`).



## Executando os testes separadamente

Os dois comandos abaixo são **independentes** — rode um, espere o intervalo de resfriamento, depois rode o outro. Cada um já cobre as 6 Lambdas de uma vez via `TARGETS=all` (um scenario K6 paralelo por Lambda, dentro do mesmo perfil).

### 1) Rodar todos os Spikes (6 Lambdas)

```bash
k6 run \
  -e URL_GO_CPU="https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_CONCURRENCY="https://mrdrtaib4l2rmlgjzl6mlyyz3i0ubqug.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_IO="https://qssbxz636rm46rka7yk4xqhivy0fzhcc.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CPU="https://gjgjwhul6bi6ranv2trses7cbu0nocat.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CONCURRENCY="https://jr5yv5l6qk66ly26zw7kh3m2qy0gxycq.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_IO="https://aopawemhehbwyhoxuxebbr56tq0fjvqq.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=all \
  -e SPIKE_IDLE_DURATION=5m \
  -e SPIKE_SPIKE_DURATION=30s \
  -e SPIKE_PEAK_VUS=100 \
  -e SPIKE_CYCLES=3 \
  -e PAYLOAD_CPU_NUMBER=999999999989 \
  -e PAYLOAD_CONCURRENCY_TASKS=5000 \
  --out json=results/spike-all.json \
  spike.js
```

```bash
k6 run \
  -e URL_GO_CPU="https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CPU="https://gjgjwhul6bi6ranv2trses7cbu0nocat.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=all \
  -e SPIKE_IDLE_DURATION=5m \
  -e SPIKE_SPIKE_DURATION=20s \
  -e SPIKE_PEAK_VUS=30 \
  -e SPIKE_CYCLES=2 \
  -e PAYLOAD_CPU_NUMBER=999999999989 \
  --out json=results/spike-cpu.json \
  spike.js
```



### 2) Rodar todos os Loads (6 Lambdas)

> Execute **somente depois** do intervalo de resfriamento descrito acima.

```bash
k6 run \
  -e URL_GO_CPU="https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_CONCURRENCY="https://mrdrtaib4l2rmlgjzl6mlyyz3i0ubqug.lambda-url.us-east-1.on.aws/" \
  -e URL_GO_IO="https://qssbxz636rm46rka7yk4xqhivy0fzhcc.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CPU="https://gjgjwhul6bi6ranv2trses7cbu0nocat.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_CONCURRENCY="https://jr5yv5l6qk66ly26zw7kh3m2qy0gxycq.lambda-url.us-east-1.on.aws/" \
  -e URL_QUARKUS_IO="https://aopawemhehbwyhoxuxebbr56tq0fjvqq.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=all \
  -e LOAD_RAMP_UP_DURATION=2m \
  -e LOAD_STEADY_DURATION=10m \
  -e LOAD_RAMP_DOWN_DURATION=2m \
  -e LOAD_STEADY_VUS=50 \
  --out json=results/load-all.json \
  load.js
```



### Rodando apenas uma Lambda específica (opcional)

Para isolar um único cenário (útil para debug ou re-teste pontual), use `TARGETS` com uma única chave:

```bash
k6 run \
  -e URL_GO_CPU="https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=go-cpu \
  -e SPIKE_IDLE_DURATION=5m \
  -e SPIKE_SPIKE_DURATION=30s \
  -e SPIKE_PEAK_VUS=100 \
  -e SPIKE_CYCLES=3 \
  spike.js
```

Valores aceitos em `TARGETS`:

- `go-concurrency`
- `go-cpu`
- `go-io`
- `quarkus-concurrency`
- `quarkus-cpu`
- `quarkus-io`
- `all` (padrão)



### Smoke test rápido (1 VU, 10s)

Útil para validar conectividade antes de rodar a bateria completa — **não conta como medição válida**, apenas para checar se as URLs respondem:

```bash
k6 run \
  -e URL_GO_CPU="https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/" \
  -e TARGETS=go-cpu \
  --vus 1 \
  --duration 10s \
  load.js
```

> Para smoke tests ad hoc, as flags `--vus` e `--duration` da CLI sobrescrevem temporariamente os scenarios definidos no script.



## Exportar resultados

```bash
# JSON para pós-processamento
k6 run --out json=results/spike.json spike.js

# CSV
k6 run --out csv=results/spike.csv spike.js
```



## Seleção de targets

Por padrão, todos os 6 endpoints são testados em paralelo (um scenario K6 por Lambda) dentro do perfil escolhido (Spike **ou** Load, nunca os dois juntos).

Para testar apenas um subconjunto:

```bash
TARGETS=go-cpu,quarkus-cpu k6 run spike.js
```

Exemplo para testar os dois cenários de concorrência:

```bash
TARGETS=go-concurrency,quarkus-concurrency k6 run spike.js
```



## Métricas e tags

Cada requisição HTTP recebe tags para facilitar a comparação Go vs Quarkus no relatório:

- `language`: `go` ou `quarkus`
- `route`: `cpu`, `concurrency` ou `io`
- `target`: chave completa (ex: `go-cpu`)
- `test_profile`: `spike` ou `load`

**Checks aplicados:**

- Status HTTP 200
- Resposta com corpo não vazio

**Métricas customizadas:**

- `lambda_duration` — Trend da duração por tag
- `lambda_success` — Rate de sucesso (checks)
- `lambda_requests` — Counter de requisições



## Variáveis opcionais adicionais


| Variável                    | Padrão         | Descrição                                      |
| --------------------------- | -------------- | ---------------------------------------------- |
| `PAYLOAD_CPU_NUMBER`        | `999999999989` | Número para fatoração (CPU)                    |
| `PAYLOAD_CONCURRENCY_TASKS` | `5000`         | Quantidade de tasks/goroutines/virtual threads |
| `HTTP_TIMEOUT`              | `60s`          | Timeout por requisição HTTP                    |
| `GRACEFUL_RAMP_DOWN`        | `30s`          | Tempo de ramp-down gracioso                    |
| `THRESHOLD_HTTP_FAIL_RATE`  | `0.05`         | Limite de taxa de falha HTTP                   |
| `THRESHOLD_SUCCESS_RATE`    | `0.95`         | Limite mínimo de sucesso                       |
| `THRESHOLD_P95_GO_MS`       | `30000`        | p95 máximo para Go (ms)                        |
| `THRESHOLD_P95_QUARKUS_MS`  | `30000`        | p95 máximo para Quarkus (ms)                   |


Consulte `.env.example` para a lista completa.

## Interpretação dos resultados

Compare as métricas segmentadas por tag no sumário final do K6:

```text
http_req_duration................: avg=XXXms p(95)=XXXms
{ language:go, route:cpu }.......: avg=XXXms p(95)=XXXms
{ language:quarkus, route:cpu }..: avg=XXXms p(95)=XXXms
```

No perfil **Spike**, latências elevadas nos primeiros segundos após cada idle indicam comportamento compatível com cold start. No perfil **Load**, latências estáveis ao longo do platô indicam o regime de warm start.

Para a análise comparativa, recomenda-se avaliar separadamente:

- **CPU:** desempenho na fatoração de números primos;
- **Concorrência:** comportamento com múltiplas tasks simultâneas;
- **I/O:** desempenho de operações de leitura e escrita no DynamoDB;
- **Cold Start:** comportamento observado no início dos picos após períodos de inatividade;
- **Warm Start:** desempenho durante o regime estável de execução;
- **Taxa de sucesso:** proporção de requisições concluídas sem erro;
- **Latência:** média, mediana e percentis, especialmente p90, p95 e p99.



## Notas

- As Lambdas esperam requisições `POST` com `Content-Type: application/json`.
- As URLs utilizam AWS Lambda Function URL (`AuthType = NONE`), provisionadas via Terraform (`enable_lambda_function_urls = true`).
- Não há autenticação — mantenha esse recurso habilitado apenas durante as janelas de teste.
- **Nunca rode** `spike.js` **e** `load.js` **simultaneamente contra as mesmas Lambdas** — veja [Ordem de execução recomendada](#ordem-de-execução-recomendada).
- Ajuste `SPIKE_PEAK_VUS` e `LOAD_STEADY_VUS` conforme os limites de concorrência da sua conta AWS.
- As URLs acima utilizam a região `us-east-1`.
- Para testes científicos/reprodutíveis, mantenha constantes os parâmetros de carga entre as implementações Go e Quarkus correspondentes.
- Recomenda-se executar múltiplas repetições de cada perfil para reduzir o impacto de variações ocasionais da infraestrutura.

