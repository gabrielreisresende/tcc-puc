# Validação de MVP — Pipeline de Testes de Carga (k6) Go vs Quarkus, cenário CPU

**Objetivo deste MVP:** validar que o fluxo completo (teste de spike no k6 →
extração de métricas) funciona corretamente após as correções aplicadas
(ramp-down explícito das VUs, `STAGGER_TARGETS` para não somar concorrência
entre as duas Lambdas, `SPIKE_PEAK_VUS` calibrado abaixo do teto de
throttling da conta). **Não é o resultado final do TCC** — amostra pequena
(1 ciclo, poucos VUs), apenas para provar que o mecanismo de coleta e
classificação cold/warm funciona antes da rodada de coleta definitiva.

## 1. Configuração do teste

| Parâmetro | Valor |
| --- | --- |
| Cenário | `cpu` (fatoração de números primos) — `go-cpu` vs `quarkus-cpu` |
| `SPIKE_IDLE_DURATION` | 2 min |
| `SPIKE_SPIKE_DURATION` | 10 s |
| `SPIKE_RAMPDOWN_DURATION` | 2 s |
| `SPIKE_PEAK_VUS` | 5 (config) / pico realizado ~3 VUs simultâneas |
| `SPIKE_CYCLES` | 1 |
| `STAGGER_TARGETS` | `true` (go-cpu e quarkus-cpu rodaram em sequência, não em paralelo) |
| Arquivo fonte | `k6/results/mvp-spike.json` |

## 2. Volume e taxa de sucesso

| Linguagem | Requisições | Sucesso (200) | Falhas / 429 | Taxa de sucesso |
| --- | ---: | ---: | ---: | ---: |
| Go | 62 | 62 | 0 | 100% |
| Quarkus | 53 | 53 | 0 | 100% |

Nenhum HTTP 429 em nenhuma das duas — confirma que `SPIKE_PEAK_VUS=5` ficou
dentro do teto de concorrência medido anteriormente (limpo até 8 VUs) e que
o `STAGGER_TARGETS` evitou a soma de concorrência entre as duas Lambdas.

## 3. Desempenho — latência HTTP fim-a-fim (todas as requisições, ms)

| Linguagem | Média | Mediana | p90 | p95 | p99 | Mín | Máx |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 213,1 | 191,5 | 253,4 | 331,6 | 504,3 | 159,0 | 652,3 |
| Quarkus | 245,6 | 215,5 | 251,0 | 329,0 | 930,4 | 176,3 | 1094,9 |

Nesse recorte (amostra pequena, uma única rajada), Go teve latência média e
p50 um pouco menores; a cauda (p99) do Quarkus foi puxada para cima por
poucas requisições no início da rajada — o que já aponta para o sinal de
cold start detalhado a seguir.

## 4. Sinal de Cold Start (aproximação via k6 — não é a métrica oficial)

Classificação: **cold** = requisições no primeiro segundo da rajada, logo
após os 2 minutos de inatividade; **warm_burst** = requisições no restante
da mesma rajada (containers já aquecidos pela primeira leva).

| Linguagem | n (cold) | Méd. cold (ms) | Mediana cold (ms) | Máx cold (ms) | n (warm) | Méd. warm (ms) | Mediana warm (ms) | Razão méd. cold/warm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Go | 4 | 400,5 | 357,2 | 652,3 | 58 | 200,2 | 187,9 | 2,00× |
| Quarkus | 5 | 407,9 | 245,1 | 1094,9 | 48 | 228,7 | 215,3 | 1,78× |

**Leitura:** nos dois casos a latência das primeiras requisições após a
inatividade é claramente mais alta que o restante da rajada (~1,8-2×),
indicando que o mecanismo de detecção está funcionando e capturando um
efeito compatível com cold start. A amostra é pequena demais (n=4-5) para
qualquer conclusão comparativa entre Go e Quarkus — serve só como prova de
que o pipeline funciona.

## 5. Custo estimado (proxy client-side — não é o valor oficial)

Estimativa usando a duração observada pelo k6 (inclui rede) como
substituta da *Billed Duration* real da AWS, e memória assumida em 512 MB
(padrão documentado em `terraform.tfvars.example` — **não confirmado** para
o deploy real, que usa `terraform.tfvars`, não versionado). Preço AWS
Lambda x86 on-demand em `us-east-1`: US$ 0,20 / 1M requisições + US$
0,0000166667 / GB-s (aws.amazon.com/lambda/pricing, ago/2026).

| Linguagem | Requisições | GB-s estimado | Custo estimado (USD) |
| --- | ---: | ---: | ---: |
| Go | 62 | 6,61 | US$ 0,00011 |
| Quarkus | 53 | 6,51 | US$ 0,00011 |
| **Total** | **115** | **13,12** | **US$ 0,00024** |

Praticamente gratuito — bem dentro do free tier (1M requisições + 400.000
GB-s/mês). Esse número tende a **superestimar** o custo real, porque a
duração do k6 inclui o tempo de rede (ida e volta até `us-east-1`), que a
AWS não cobra — só o tempo de execução dentro da Lambda entra na *Billed
Duration*.

## 6. Limitações deste MVP e o que falta para os números finais do TCC

- **Amostra mínima**: 1 ciclo só, ~3 VUs de pico. A rodada definitiva
  (`SPIKE_CYCLES=5`, `SPIKE_PEAK_VUS=5`) já está calibrada e pronta para
  rodar quando for hora de coletar os dados do capítulo de resultados.
- **Cold start é aproximado**: a classificação acima usa só a latência HTTP
  vista pelo k6 (rede + fila + init + execução misturados). A métrica que o
  artigo define na seção 4.2 ("Latência de Cold Start") é o *Init Duration*
  que a própria AWS registra no CloudWatch — só ele isola de fato o tempo
  de inicialização do ambiente de execução.
- **Custo é aproximado**: pelo mesmo motivo, a *Billed Duration* real
  (CloudWatch) tende a ser menor que a duração do k6 usada aqui.

**Precisa rodar o `aws_cloudwatch_xray_metrics.py`?** Não para este MVP —
ele já cumpriu o papel de provar que o fluxo (teste corrigido → extração →
tabela) funciona sem 429 e com sinal de cold start coerente. Mas **sim,
antes de usar números no capítulo de resultados do TCC**: é a única forma
de trocar as duas aproximações acima (cold start e custo) pelos valores
reais que o artigo se propõe a medir (*Init Duration*, *Billed Duration* ×
memória). O script já está pronto em `k6/analysis/aws_cloudwatch_xray_metrics.py`
— falta só rodá-lo no seu terminal local (com `boto3` + credenciais AWS)
apontando para a mesma janela de tempo da rodada de coleta definitiva.
