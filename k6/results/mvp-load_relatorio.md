# Validação de MVP — Pipeline de Testes de Carga (k6) Go vs Quarkus, cenário CPU, perfil Load

**Objetivo deste MVP:** validar que o fluxo completo do perfil **Load**
(warm start) funciona corretamente — mesma validação que já tinha sido
feita para o **Spike** (`mvp-spike_relatorio.md`) — antes de rodar a coleta
definitiva. **Não é o resultado final do TCC**: é uma única execução, em
escala reduzida frente à rodada definitiva (`.env`: `LOAD_STEADY_DURATION`
padrão de 10min / `LOAD_STEADY_VUS=6`), só para confirmar que o teste de
carga sustentada roda sem 429, mantém os containers aquecidos e que o
pipeline `k6 → extract_k6_metrics.py → aws_cloudwatch_xray_metrics.py`
também funciona para esse perfil.

## 1. Configuração do teste

| Parâmetro | Valor |
| --- | --- |
| Cenário | `cpu` (fatoração de números primos) — `go-cpu` vs `quarkus-cpu` |
| Perfil | Load (`load.js`) — ramp-up → platô → ramp-down, sem períodos de inatividade |
| `STAGGER_TARGETS` | `true` — go-cpu rodou primeiro (20:37:35–20:38:41), quarkus-cpu em seguida (20:38:46–20:39:51), gap de ~5s entre os dois |
| Duração observada por target | ~65,3s (go) / ~64,7s (quarkus) |
| Formato de carga observado (via `mvp-load_timeseries.csv`) | ramp-up ~0–20s, platô ~21–56s (~35s), ramp-down ~57s em diante |
| Payload | corpo de requisição consistente com `PAYLOAD_CPU_NUMBER` padrão (999999999989) — tamanho médio de `data_sent` (~214-220 bytes) bate com o esperado para esse payload |
| Arquivo fonte | `k6/results/mvp-load.json` |

> **Nota:** os valores exatos de `LOAD_RAMP_UP_DURATION` / `LOAD_STEADY_DURATION` /
> `LOAD_STEADY_VUS` usados no `k6 run` não ficam gravados no JSON de métricas
> do k6 (só aparecem no `console.log` do `setup()`, que vai para o stdout do
> terminal, não para o `--out json`) — os valores acima foram **inferidos a
> partir da série temporal observada** (`mvp-load_timeseries.csv`), não lidos
> de um parâmetro registrado. Para a rodada definitiva, recomenda-se
> redirecionar o stdout do `k6 run` para um arquivo de log (`... | tee
> results/mvp-load.log`) para não depender de inferência.

## 2. Volume e taxa de sucesso

| Linguagem | Requisições | Sucesso (200) | Falhas / 429 | Taxa de sucesso |
| --- | ---: | ---: | ---: | ---: |
| Go | 1.352 | 1.352 | 0 | 100% |
| Quarkus | 1.282 | 1.282 | 0 | 100% |

Nenhum HTTP 429 nas 2.634 requisições combinadas — o nível de carga usado
ficou dentro do teto de concorrência da conta (calibrado previamente em
`discover-concurrency.js`), mesmo em regime sustentado por mais de um
minuto (diferente do Spike, que só sustenta o pico por segundos).

## 3. Perfil de carga realizado (throughput por fase)

| Fase | Go — req/s médio | Quarkus — req/s médio |
| --- | ---: | ---: |
| Ramp-up (0–20s) | 16,3 | 16,0 |
| Platô (21–56s) | 24,9 | 23,6 |
| Ramp-down (57s+) | 12,6 | 11,9 |
| Pico observado | 28 req/s | 29 req/s |

As duas linguagens realizaram um perfil de carga praticamente idêntico
(diferença de throughput no platô <6%), o que é importante para a
comparação ser justa — nenhuma das duas foi submetida a mais requisições
por segundo que a outra.

## 4. Desempenho — latência HTTP fim-a-fim (todas as requisições, ms)

| Linguagem | Média | Mediana | p90 | p95 | p99 | Mín | Máx |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 198,3 | 195,9 | 234,3 | 241,3 | 257,1 | 147,0 | 439,3 |
| Quarkus | 209,4 | 210,1 | 234,1 | 240,4 | 257,3 | 150,4 | 1000,6 |

Em regime de carga sustentada (quase tudo warm start — ver seção 5), Go e
Quarkus ficam muito próximos no p90/p95/p99 (diferença <1ms em p90); a
média do Quarkus é ~11ms maior, puxada pela cauda (`max` de 1000,6ms é um
outlier isolado, provavelmente um dos poucos cold starts do início do
ramp-up). Isso já é um sinal distinto do Spike: lá a diferença Go vs
Quarkus era mais visível porque cold starts pesavam mais na amostra
pequena; aqui, com >1.300 requisições majoritariamente warm por
linguagem, a latência fim-a-fim (dominada por rede, não por execução)
converge bastante entre as duas.

## 5. Cold starts neste perfil (raros, ao contrário do Spike)

A classificação cold/warm por janela de tempo do `extract_k6_metrics.py`
não faz sentido aqui (não existe idle entre ciclos no perfil Load — é
platô contínuo), então essa comparação foi feita com o dado real da AWS
(ver `mvp-load-aws_relatorio.md`): apenas **4 cold starts em 1.352**
requisições Go (0,30%) e **5 em 1.282** Quarkus (0,39%), todos concentrados
nos primeiros segundos do ramp-up — exatamente o esperado para um perfil
que existe para manter os containers aquecidos, ao contrário do Spike, que
existe para forçá-los a esfriar.

## 6. Custo estimado (proxy client-side — não é o valor oficial)

Estimativa usando a duração observada pelo k6 (inclui rede) como
substituta da *Billed Duration* real, já com a memória real confirmada de
**128 MB** (achado do MVP Spike, `mvp-spike-aws_relatorio.md` seção 1).
Preço AWS Lambda x86 on-demand em `us-east-1`: US$ 0,20 / 1M requisições +
US$ 0,0000166667 / GB-s.

| Linguagem | Requisições | GB-s estimado | Custo estimado (USD) |
| --- | ---: | ---: | ---: |
| Go | 1.352 | 33,52 | US$ 0,00083 |
| Quarkus | 1.282 | 33,56 | US$ 0,00082 |
| **Total** | **2.634** | **67,08** | **US$ 0,00164** |

Como no MVP Spike, esse proxy **superestima** o custo real porque a
duração do k6 mistura rede + fila + execução — ver seção 10 do
`mvp-load-aws_relatorio.md` para a comparação com o valor real medido via
CloudWatch (~2,0x menor).

## 7. Limitações deste MVP e o que falta para os números finais do TCC

- **Amostra de uma única execução**: apesar do volume de requisições ser
  bem maior que o MVP Spike (1.282–1.352 vs 53–62), ainda é **uma rodada
  só**. A rodada definitiva deve usar os parâmetros de escala cheia
  (`LOAD_RAMP_UP_DURATION=2m`, `LOAD_STEADY_DURATION=10m`,
  `LOAD_RAMP_DOWN_DURATION=2m`, `LOAD_STEADY_VUS=6`, já calibrados no
  `.env`) e, segundo a recomendação do `k6/README.md`, **repetida algumas
  vezes** para reduzir ruído de infraestrutura antes de consolidar os
  números do capítulo de Resultados.
- **Parâmetros de stage não registrados**: ver nota na seção 1 — registrar
  o stdout do `k6 run` nas próximas execuções.
- **Custo é aproximado**: pelo mesmo motivo do MVP Spike, a *Billed
  Duration* real (CloudWatch) é menor que a duração do k6 usada aqui — ver
  `mvp-load-aws_relatorio.md`.
- **Já rodou o `aws_cloudwatch_xray_metrics.py`?** Sim — ver
  `mvp-load-aws_relatorio.md` para o Tempo de Execução em Warm Start, o
  Consumo Máximo de Memória e o Custo Financeiro reais desta mesma janela.
