# Métricas AWS (CloudWatch Logs) — Validação do MVP Load, cenário CPU

**Objetivo deste relatório:** registrar os dados reais da AWS (via
`k6/analysis/aws_cloudwatch_xray_metrics.py`) para a janela do
`k6/results/mvp-load.json`, complementando o `mvp-load_relatorio.md`
(que só enxerga a latência HTTP fim-a-fim) com Tempo de Execução em Warm
Start (*Duration*), Consumo Máximo de Memória e Custo Financeiro reais.
**Ainda é dado de MVP** (uma única execução) — serve para validar o
pipeline e já dá uma primeira leitura direcional, mas não é o número final
do capítulo de Resultados.

> Nota: esta consulta **não usou `--with-xray`** — o AWS X-Ray Active
> Tracing foi desativado nas 6 Lambdas em 27/08/2026 (`tracing_config` virou
> `PassThrough` no Terraform) porque gerava custo sem contribuir nenhum dado
> usado no TCC; as métricas abaixo vêm inteiramente das linhas `REPORT` do
> CloudWatch Logs, que não dependem do X-Ray.

## 1. Parâmetros da consulta

| Parâmetro | Valor |
| --- | --- |
| Funções consultadas | `tcc-lambda-benchmark-dev-go-cpu`, `tcc-lambda-benchmark-dev-quarkus-cpu` |
| Região | `us-east-1` |
| Janela solicitada | `2026-08-27T20:37:25-03:00` → `2026-08-27T20:40:00-03:00` |
| Fonte | linhas `REPORT` do CloudWatch Logs (Logs Insights) |
| Arquivo de origem | `k6/results/mvp-load.json` (mesma rodada do `mvp-load_relatorio.md`) |
| Saída bruta | `mvp-load-aws_summary.json`, `mvp-load-aws_tcc-lambda-benchmark-dev-go-cpu_invocations.csv`, `mvp-load-aws_tcc-lambda-benchmark-dev-quarkus-cpu_invocations.csv` |
| Memória configurada | 128 MB (confirmado via `memory_size_mb` do CloudWatch, igual ao MVP Spike) |

## 2. Volume de dados

| Função | Invocações (REPORT) | Cold starts | Taxa de cold start |
| --- | ---: | ---: | ---: |
| Go (`go-cpu`) | 1.352 | 4 | 0,30% |
| Quarkus (`quarkus-cpu`) | 1.282 | 5 | 0,39% |

Os números batem com os do `mvp-load_relatorio.md` (1.352 Go, 1.282
Quarkus, ambos 100% de sucesso HTTP) — confirma que a janela consultada
cobriu exatamente a rodada correta. A taxa de cold start (<0,4%) é
consistente com o objetivo do perfil Load: manter os containers aquecidos
— bem diferente da taxa observada por desenho no Spike (lá o objetivo é
justamente forçar cold starts a cada ciclo).

## 3. Latência de Cold Start — Init Duration real (ms)

| Linguagem | n | Média | Mediana | Mín | Máx | p90 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 4 | 55,80 | 57,83 | 48,16 | 59,36 | 58,97 | 59,17 | 59,32 |
| Quarkus | 5 | 237,21 | 239,59 | 224,01 | 243,08 | 242,58 | 242,83 | 243,03 |

**Achado relevante:** esses valores são quase idênticos aos medidos no
MVP Spike, dois dias antes e num perfil de carga completamente diferente
(Go: 55,80ms aqui vs 55,99ms no Spike, dif. 0,3%; Quarkus: 237,21ms aqui vs
236,34ms no Spike, dif. 0,4%). Isso é um bom sinal de que a Latência de
Cold Start é uma característica estável do runtime (JVM/Quarkus vs binário
Go nativo), não um artefato do perfil de teste — reforça a validade da
metodologia para a coleta definitiva.

## 4. Tempo de Execução em Warm Start — Duration real (ms)

| Linguagem | n | Média | Mediana | Mín | Máx | p90 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 1.348 | 45,47 | 51,12 | 2,21 | 119,44 | 80,03 | 84,29 | 94,04 |
| Quarkus | 1.277 | 64,87 | 71,73 | 2,51 | 100,51 | 83,03 | 84,98 | 92,94 |

Quarkus continua mais lento que Go em execução pura (~1,4x aqui, vs ~2,4x
no MVP Spike), mas repare que a amostra agora é ~25x maior (n=1.348/1.277
vs n=60/51) — este número já tem bem mais peso estatístico que o do Spike.
Vale registrar uma diferença frente ao Spike: o Go ficou **mais lento**
sob carga sustentada (45,47ms aqui vs 30,68ms no Spike, +48%), enquanto o
Quarkus ficou **mais rápido** (64,87ms vs 72,67ms, -11%). Não dá para
afirmar a causa com uma única rodada de cada perfil — pode ser contenção
de CPU real sob concorrência sustentada (a memória de 128 MB mapeia para
uma fração pequena de vCPU, mais sensível a isso em termos relativos para
um runtime tão rápido quanto o Go) ou apenas ruído de infraestrutura;
recomenda-se confirmar esse padrão com múltiplas repetições antes de
tirar qualquer conclusão para o TCC.

## 5. Duração cobrada (Billed Duration, ms) — todas as invocações

| Linguagem | n | Média | Mediana | Mín | Máx | p90 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 1.352 | 46,18 | 52,0 | 3,0 | 137,0 | 81,0 | 85,0 | 95,49 |
| Quarkus | 1.282 | 67,41 | 72,0 | 3,0 | 616,0 | 84,0 | 86,0 | 95,0 |

O `máx` do Quarkus (616ms) é uma das 5 invocações de cold start — mas,
diluído em 1.282 amostras (vs 53 no Spike), o efeito na média e nos
percentis usuais é bem menor do que foi no MVP Spike (lá o p99 chegava a
595,84ms; aqui o p99 já volta para 95,0ms). Boa ilustração de por que
amostra maior estabiliza os percentis de cauda.

## 6. Consumo Máximo de Memória (Max Memory Used, MB)

| Linguagem | n | Média | Mediana | Mín | Máx | Memória alocada |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 1.352 | 20,31 | 20,0 | 18 | 23 | 128 MB |
| Quarkus | 1.282 | 54,37 | 54,0 | 48 | 65 | 128 MB |

Os dois consumiram um pouco mais de memória sob carga sustentada do que no
MVP Spike (Go: 18,0→20,3MB, +13%; Quarkus: 48,8→54,4MB, +11%) — dentro do
esperado, mas vale acompanhar se o padrão se repete na coleta definitiva.
Ambos seguem bem abaixo dos 128 MB alocados.

## 7. Custo Financeiro Estimado (USD)

Cálculo real: `Billed Duration × Memory Size`, preços sob demanda AWS
Lambda x86 em `us-east-1` (US$ 0,20 / 1M requisições + US$ 0,0000166667 /
GB-s).

| Linguagem | Invocações | GB-s total | Custo requisições (USD) | Custo computação (USD) | Custo total (USD) | Custo médio/invocação (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 1.352 | 7,805 | 0,0002704 | 0,0001301 | 0,0004005 | 0,00000030 |
| Quarkus | 1.282 | 10,802 | 0,0002564 | 0,0001800 | 0,0004364 | 0,00000034 |
| **Total** | **2.634** | **18,607** | **0,0005268** | **0,0003101** | **0,0008369** | — |

**Achado interessante para o TCC:** a razão de custo Quarkus/Go **encolhe**
sob carga sustentada — de ~1,46x no MVP Spike (dominado por poucas
invocações, incluindo cold starts caros) para ~1,15x aqui (2.634
invocações majoritariamente warm). Isso sugere que boa parte da
desvantagem de custo do Quarkus vem do cold start, e se dilui à medida que
o container fica aquecido por mais tempo — hipótese que vale a pena
formalizar e testar com a rodada definitiva (mais VUs/tempo de platô).

## 8. Comparação com o MVP Spike (mesmo cenário CPU)

| Métrica | Spike (25/08, n pequeno) | Load (27/08, n grande) |
| --- | --- | --- |
| Cold start Go — Init Duration (ms) | 55,99 (n=2) | 55,80 (n=4) |
| Cold start Quarkus — Init Duration (ms) | 236,34 (n=2) | 237,21 (n=5) |
| Warm Go — Duration (ms) | 30,68 (n=60) | 45,47 (n=1.348) |
| Warm Quarkus — Duration (ms) | 72,67 (n=51) | 64,87 (n=1.277) |
| Memória Go (MB) | 18,0 (n=62) | 20,3 (n=1.352) |
| Memória Quarkus (MB) | 48,8 (n=53) | 54,4 (n=1.282) |
| Custo Quarkus/Go (razão) | ~1,46x | ~1,15x |

A Latência de Cold Start é a métrica mais estável entre os dois perfis
(diferença <0,5%) — esperado, já que independe de quanto tempo o container
fica sob carga depois de inicializado. As demais métricas (Duration,
memória, custo) variam mais entre os perfis, o que reforça a necessidade
de reportar os dois perfis separadamente no TCC (não misturar números de
Spike com números de Load) e de repetir cada perfil múltiplas vezes antes
de consolidar.

## 9. Comparação com a aproximação client-side do k6 (mvp-load_relatorio.md)

| Métrica | Aproximação k6 (client-side) | Valor real (AWS) | Razão |
| --- | --- | --- | --- |
| Duração Go (ms) | 198,31 (HTTP e2e) | 45,47 (execução pura, warm) | 4,36x |
| Duração Quarkus (ms) | 209,41 (HTTP e2e) | 64,87 (execução pura, warm) | 3,23x |
| Custo total (2.634 req) | US$ 0,00164 (proxy, já com 128 MB) | US$ 0,00084 (real) | 1,97x |

Diferente do MVP Spike — onde o proxy de custo usava por engano 512 MB e
por isso inflava o número por dois motivos ao mesmo tempo (memória errada
+ rede) —, aqui o proxy do `mvp-load_relatorio.md` já usa os 128 MB
corretos. A diferença remanescente (~2x) é só o efeito de rede/fila que o
k6 mede e a AWS não cobra, exatamente a mesma lógica da seção 8 do
`mvp-spike-aws_relatorio.md`.

## 10. Limitações desta rodada

- **Uma única execução**: apesar do volume de requisições ser grande
  (1.282–1.352, bem mais que os 53–62 do MVP Spike), ainda é um único run.
  As diferenças observadas frente ao Spike na seção 8 (Go mais lento sob
  carga, Quarkus mais rápido, custo relativo menor) são hipóteses a
  confirmar, não conclusões — repetir a rodada (idealmente em escala cheia:
  `LOAD_STEADY_DURATION=10m`, `LOAD_STEADY_VUS=6`) antes de usar esses
  números no capítulo de Resultados.
- **Sem X-Ray**: como o Active Tracing foi desligado, não há mais
  `xray_initialization_subsegment_ms` para cruzar — mas isso não é perda,
  já que esse campo nunca trouxe dado usável no MVP Spike (sempre `null`).
- **Não é o dado final do TCC**: repetir com os parâmetros de escala cheia
  já calibrados no `.env`, idealmente várias vezes, como recomenda o
  `k6/README.md`.

## 11. Mapeamento para a seção 4.2 do artigo

| Métrica do artigo | Valor nesta rodada (Go) | Valor nesta rodada (Quarkus) | Fonte |
| --- | --- | --- | --- |
| Latência de Cold Start (ms) | 55,80 (média, n=4) | 237,21 (média, n=5) | `cold_start_init_duration_ms` |
| Tempo de Execução em Warm Start (ms) | 45,47 (média, n=1.348) | 64,87 (média, n=1.277) | `warm_start_duration_ms` |
| Consumo Máximo de Memória (MB) | 20,31 (média) | 54,37 (média) | `max_memory_used_mb_all` |
| Custo Financeiro Estimado (USD) | 0,0004005 (total, 1.352 inv.) | 0,0004364 (total, 1.282 inv.) | `cost_estimate` |
