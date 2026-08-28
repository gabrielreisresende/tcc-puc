# Métricas AWS (CloudWatch Logs + X-Ray) — Validação do MVP Spike, cenário CPU

**Objetivo deste relatório:** registrar os dados "de verdade" da AWS (via
`k6/analysis/aws_cloudwatch_xray_metrics.py`) para a mesma janela de tempo do
`k6/results/mvp-spike_relatorio.md`, substituindo as duas aproximações que
aquele relatório baseado só no k6 deixou em aberto: Latência de Cold Start
(*Init Duration*) e Custo Financeiro Estimado (*Billed Duration* × memória).
**Ainda é dado de MVP** (1 ciclo, amostra pequena) — serve como fonte inicial
de coleta e prova de que o pipeline `k6 → CloudWatch/X-Ray` funciona
ponta a ponta, não como número final do capítulo de Resultados do TCC.

## 1. Parâmetros da consulta

| Parâmetro | Valor |
| --- | --- |
| Funções consultadas | `tcc-lambda-benchmark-dev-go-cpu`, `tcc-lambda-benchmark-dev-quarkus-cpu` |
| Região | `us-east-1` |
| Janela solicitada | `2026-08-25T19:39:26-03:00` → `2026-08-25T19:46:00-03:00` |
| Fonte | linhas `REPORT` do CloudWatch Logs (Logs Insights) + `GetTraceSummaries`/`BatchGetTraces` do X-Ray |
| Arquivo de origem | `k6/results/mvp-spike.json` (mesma rodada do `mvp-spike_relatorio.md`) |
| Saída bruta | `mvp-spike-aws_summary.json`, `mvp-spike-aws_tcc-lambda-benchmark-dev-go-cpu_invocations.csv`, `mvp-spike-aws_tcc-lambda-benchmark-dev-quarkus-cpu_invocations.csv` |

Os CSVs mostram que as invocações reais do Go ocorreram entre
`22:41:36.179` e `22:41:43.855` (UTC) e as do Quarkus entre `22:45:48.780` e
`22:45:55.748` (UTC) — equivalente a `19:41:36`–`19:41:43` e
`19:45:48`–`19:45:55` em horário de São Paulo, ambas dentro da janela
consultada. O intervalo entre as duas rajadas confirma que `STAGGER_TARGETS`
funcionou: Go e Quarkus rodaram em sequência, não em paralelo.

**Achado adicional:** o `memory_size_mb` reportado pelo CloudWatch é
**128 MB** para as duas funções — não os 512 MB assumidos por padrão no
`mvp-spike_relatorio.md` (que citava `terraform.tfvars.example` como
suposição, sem confirmação do `terraform.tfvars` real). Use 128 MB como
valor correto de memória configurada ao documentar a metodologia do TCC,
a menos que o `terraform.tfvars` do deploy atual diga outra coisa.

## 2. Volume de dados

| Função | Invocações (REPORT) | Cold starts | Traces X-Ray capturados |
| --- | ---: | ---: | ---: |
| Go (`go-cpu`) | 62 | 2 (3,23%) | 62 |
| Quarkus (`quarkus-cpu`) | 53 | 2 (3,77%) | 52 |

Os números de invocações batem com os do `mvp-spike_relatorio.md` (62 Go,
53 Quarkus, ambos 100% de sucesso HTTP) — confirma que a janela de tempo
consultada cobriu exatamente a mesma rodada.

## 3. Latência de Cold Start — Init Duration real (ms)

Métrica oficial da AWS (campo `Init Duration` da linha `REPORT`), a que o
artigo define na seção 4.2 como "Latência de Cold Start".

| Linguagem | n | Média | Mediana | Mín | Máx | p90 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 2 | 55,99 | 55,99 | 53,34 | 58,63 | 58,10 | 58,37 | 58,58 |
| Quarkus | 2 | 236,34 | 236,34 | 234,65 | 238,02 | 237,68 | 237,85 | 237,99 |

**Leitura:** o Init Duration real do Quarkus é ~4,2× maior que o do Go
(236 ms vs 56 ms) — consistente com o esperado para JVM (mesmo com Quarkus)
vs um binário Go compilado nativamente. `n=2` por função é insuficiente
para qualquer teste estatístico; serve só de indício inicial.

## 4. Tempo de Execução em Warm Start — Duration real (ms)

| Linguagem | n | Média | Mediana | Mín | Máx | p90 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 60 | 30,68 | 17,69 | 2,59 | 84,78 | 67,87 | 74,91 | 81,73 |
| Quarkus | 51 | 72,67 | 71,79 | 48,89 | 86,38 | 81,63 | 82,93 | 85,62 |

**Leitura:** em warm start o Quarkus também executa ~2,4× mais devagar em
média (72,7 ms vs 30,7 ms). O Go tem variância bem maior (stdev 24,75 vs
7,94 do Quarkus) — mediana bem abaixo da média sugere distribuição com
cauda longa em algumas requisições Go, vale investigar na rodada definitiva
com amostra maior.

## 5. Duração cobrada (Billed Duration, ms) — todas as invocações

| Linguagem | n | Média | Mediana | Mín | Máx | p90 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 62 | 33,18 | 19,50 | 3,0 | 111,0 | 71,9 | 77,0 | 95,14 |
| Quarkus | 53 | 92,91 | 73,00 | 49,0 | 600,0 | 83,0 | 85,8 | 595,84 |

O `p99` do Quarkus (595,84 ms) é puxado pelas 2 invocações de cold start
(600 ms e 592 ms de billed duration) — com `n=53` esses 2 outliers já pesam
no percentil 99. Nítido lembrete de que, com amostra maior na coleta
definitiva, esse efeito de cauda deve diluir.

## 6. Consumo Máximo de Memória (Max Memory Used, MB)

| Linguagem | n | Média | Mediana | Mín | Máx | Memória alocada |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 62 | 18,0 | 18,0 | 18 | 18 | 128 MB |
| Quarkus | 53 | 48,79 | 49,0 | 48 | 50 | 128 MB |

Go usa consistentemente 18 MB (stdev 0 — nenhuma variação), Quarkus usa
~48-50 MB (~2,7× mais memória). Ambos ficam bem abaixo dos 128 MB alocados
— indício de que 128 MB é suficiente, mas também que não há muita margem
para explorar diferenças de custo via ajuste de memória sem antes medir CPU
disponível por tier de memória.

## 7. Custo Financeiro Estimado (USD)

Cálculo real: `Billed Duration × Memory Size`, preços sob demanda
AWS Lambda x86 em `us-east-1` (US$ 0,20 / 1M requisições + US$ 0,0000166667
/ GB-s).

| Linguagem | Invocações | GB-s total | Custo requisições (USD) | Custo computação (USD) | Custo total (USD) | Custo médio/invocação (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 62 | 0,257125 | 0,0000124 | 0,0000043 | 0,0000167 | 0,00000027 |
| Quarkus | 53 | 0,6155 | 0,0000106 | 0,0000103 | 0,0000209 | 0,00000039 |

Valores absolutos irrelevantes nessa escala (fração de centavo, dentro do
free tier). O que importa para o TCC é a **razão**: o Quarkus custa
~1,46× mais por invocação que o Go nesta amostra, refletindo diretamente o
billed duration mais alto. Para uma projeção de custo mensal realista, use
`--projected-monthly-invocations` na rodada definitiva.

## 8. Comparação com a aproximação client-side do k6 (mvp-spike_relatorio.md)

| Métrica | Aproximação k6 (client-side) | Valor real (AWS) |
| --- | --- | --- |
| Cold start Go (ms) | ~400,5 (média, n=4, HTTP e2e) | Init Duration: 55,99 (n=2) |
| Cold start Quarkus (ms) | ~407,9 (média, n=5, HTTP e2e) | Init Duration: 236,34 (n=2) |
| Warm Go (ms) | ~200,2 (HTTP e2e, inclui rede) | Duration: 30,68 (execução pura) |
| Warm Quarkus (ms) | ~228,7 (HTTP e2e, inclui rede) | Duration: 72,67 (execução pura) |
| Custo total (62+53 req) | não medido diretamente (proxy: US$ 0,00024) | US$ 0,0000376 |

Confirma a hipótese do `mvp-spike_relatorio.md`: a latência vista pelo k6
mistura rede + fila + init + execução, então superestima tanto o cold start
quanto o warm start isolados — e o custo real (baseado em Billed Duration)
é bem menor que o proxy calculado a partir da duração do k6.

## 9. Limitações desta rodada

- **Amostra mínima**: `n=2` cold starts por função, `SPIKE_CYCLES=1`. Não
  dá para tirar conclusão estatística — só confirma que o pipeline extrai o
  dado certo.
- **X-Ray sem segmento "Initialization"**: `xray_initialization_subsegment_ms`
  veio `null` para as duas funções — o `BatchGetTraces` não encontrou um
  subsegmento chamado `"Initialization"` nos traces coletados (comum quando
  o X-Ray SDK/runtime não instrumenta explicitamente a fase de init da
  Lambda). Portanto, a única fonte confiável de Init Duration nesta rodada
  foi o CloudWatch Logs (`REPORT` lines), não o X-Ray. Se a validação
  cruzada com X-Ray for importante para o TCC, investigar se a
  instrumentação X-Ray das Lambdas Go/Quarkus precisa de ajuste antes da
  coleta definitiva.
- **Memória configurada corrigida**: 128 MB confirmado via `memory_size_mb`
  do CloudWatch — atualizar qualquer texto do TCC que ainda cite 512 MB.
- **Não é o dado final do TCC**: repetir com `SPIKE_CYCLES=5`,
  `SPIKE_PEAK_VUS=5` (configuração já calibrada no `.env`) para a coleta
  que vai efetivamente para o capítulo de Resultados, e idealmente repetir
  a rodada completa algumas vezes para reduzir ruído de infraestrutura,
  como o `k6/analysis/README.md` recomenda.

## 10. Mapeamento para a seção 4.2 do artigo

| Métrica do artigo | Valor nesta rodada (Go) | Valor nesta rodada (Quarkus) | Fonte |
| --- | --- | --- | --- |
| Latência de Cold Start (ms) | 55,99 (média) | 236,34 (média) | `cold_start_init_duration_ms` |
| Tempo de Execução em Warm Start (ms) | 30,68 (média) | 72,67 (média) | `warm_start_duration_ms` |
| Consumo Máximo de Memória (MB) | 18,0 (média) | 48,79 (média) | `max_memory_used_mb_all` |
| Custo Financeiro Estimado (USD) | 0,0000167 (total, 62 inv.) | 0,0000209 (total, 53 inv.) | `cost_estimate` |
