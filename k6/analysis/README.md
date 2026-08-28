# Pipeline de análise — k6 + CloudWatch + X-Ray (Go vs Quarkus)

Este diretório reúne as ferramentas para extrair, do jeito que o TCC pede
(seção 4.2 do artigo: Cold Start Latency, Warm Start Execution Time, Consumo
Máximo de Memória, Custo Financeiro Estimado; seção 4.1 etapa 5: média,
mediana, p90, p99), as métricas de comparação entre as Lambdas Go e Quarkus.

## Achado 1: o `spike.js` original não estava produzindo cold starts reais

Ao analisar `results/spike-cpu.json`, a taxa de "cold start" detectada foi de
apenas 16-17 requisições em 56 mil (~0,03%), e mesmo essas não mostravam o
salto de latência esperado. Investigando a série temporal de requisições por
segundo (gerada por `extract_k6_metrics.py`), o motivo apareceu: durante os
períodos "idle" a taxa de requisições nunca caiu a zero, ficando em ~5 req/s
constantes, e depois de cada pico ela decaía **gradualmente ao longo de todo
o `SPIKE_IDLE_DURATION` seguinte** (5 minutos), em vez de cair a zero rápido.

Causa raiz: o executor `ramping-vus` do k6 interpola o número de VUs
**linearmente ao longo de toda a duração do stage**, partindo do valor final
do stage anterior. Um stage `{ duration: '5m', target: 0 }` logo após um
pico não derruba as VUs a 0 de imediato — ele as reduz aos poucos durante os
5 minutos inteiros. Isso mantém tráfego residual constante contra a Lambda,
o que tende a manter o contêiner quente e **impede o cold start que o teste
deveria forçar**.

Correção aplicada em `k6/config/env.js` (`getSpikeStages`) e
`k6/lib/scenarios.js` (`startVUs: 0`): cada ciclo ganhou um stage curto
extra (`SPIKE_RAMPDOWN_DURATION`, padrão `2s`) logo após o pico, que derruba
as VUs a 0 rapidamente; o stage de idle seguinte já começa (e permanece) em
0 pelo tempo configurado.

## Achado 2: ~53% das requisições falharam com HTTP 429 (throttling de concorrência)

Igualmente para Go e Quarkus — não é diferença de linguagem, é o teto de
"Concurrent Executions" da conta/função AWS sendo estourado pelos 30 VUs
simultâneos de cada Lambda (mais ainda somando as duas rodando juntas). Se
você não tem como pedir aumento de cota nem configurar concorrência
reservada, a saída é **descobrir esse teto na prática e desenhar o teste
para nunca ultrapassá-lo**. Passo a passo:

### 2.1. Descubra o teto com `discover-concurrency.js`

Novo script que sobe VUs em degraus curtos (1, 2, 4, 8, 16, 32, 64 por
padrão, ~15s cada = ~2 minutos no total) contra **um único target por vez**
e registra em que degrau começam a aparecer 429:

```bash
cd k6
k6 run -e URL_GO_CPU="<sua-url>" -e TARGETS=go-cpu \
    -e DISCOVERY_VU_STEPS=1,2,4,8,16,32,64 -e DISCOVERY_STEP_DURATION=15s \
    --out json=results/mvps/discovery-go-cpu.json \
    discover-concurrency.js
```

Depois analise:

```bash
python3 analysis/analyze_discovery.py results/mvps/discovery-go-cpu.json \
    --steps 1,2,4,8,16,32,64 --step-duration 15s
```

Isso imprime uma tabela com o total de requisições, sucessos (200) e
throttling (429) por degrau, e recomenda um `SPIKE_PEAK_VUS` seguro (70% do
maior degrau limpo). Repita com `TARGETS=quarkus-cpu` — o teto costuma ser
da **conta**, não da função, então os dois devem bater num número parecido;
se não baterem, o teto real é o menor dos dois.

Se **já 1 VU** gerar 429, o problema não é o pico de carga — pode ser
`reserved_concurrent_executions = 0` em algum lugar (não é o caso deste
projeto, já conferi o Terraform) ou outro throttling na conta; nesse caso
vale olhar a aba **Service Quotas → AWS Lambda → Concurrent executions** no
console AWS (isso é só leitura, não precisa pedir nada) para confirmar o
valor aplicado — em contas novas/educacionais às vezes é bem mais baixo que
o padrão de 1000.

### 2.2. Configure o spike test dentro desse teto

No `.env` (ou nas flags do `k6 run`):

- `SPIKE_PEAK_VUS` = o valor recomendado pelo `analyze_discovery.py` (nunca
  o valor bruto do maior degrau — a margem de 30% evita esbarrar no teto
  outra vez por variação natural de latência da AWS).
- Se for testar `go-cpu` e `quarkus-cpu` juntos no mesmo `TARGETS`, ligue
  `STAGGER_TARGETS=true`: as duas Lambdas passam a rodar em **sequência**
  dentro da mesma execução do k6 (uma só começa quando a outra termina
  todos os stages), em vez de em paralelo — assim a concorrência das duas
  não se soma contra o mesmo teto da conta. O trade-off é que elas deixam
  de ser testadas exatamente na mesma janela de tempo; se isso for uma
  preocupação para a validade do experimento, rode-as em execuções `k6 run`
  separadas (uma de cada vez) em vez de usar `STAGGER_TARGETS`.

Exemplo com os dois ajustes:

```bash
k6 run \
  -e URL_GO_CPU="..." -e URL_QUARKUS_CPU="..." \
  -e TARGETS=go-cpu,quarkus-cpu \
  -e STAGGER_TARGETS=true \
  -e SPIKE_IDLE_DURATION=2m \
  -e SPIKE_SPIKE_DURATION=15s \
  -e SPIKE_PEAK_VUS=8 \
  -e SPIKE_CYCLES=5 \
  --out json=results/mvps/spike/spike-cpu-v2.json \
  spike.js
```

Reduzi também `SPIKE_IDLE_DURATION` (de 5m para 2m) e aumentei
`SPIKE_CYCLES` (de 2 para 5) neste exemplo: com um `SPIKE_PEAK_VUS` bem
menor, cada pico ainda força cold starts (o container precisa ser
recriado do zero mesmo com poucos VUs simultâneos, desde que a idle tenha
sido longa o bastante para o container anterior morrer), mas você
precisa de mais ciclos para ter uma amostra estatisticamente razoável de
cold starts a comparar entre Go e Quarkus. Ajuste `SPIKE_IDLE_DURATION`
para pelo menos o tempo que containers Lambda costumam levar para reciclar
(não documentado pela AWS — a prática usual é 10-15 min para ter alta
confiança, mas 2-5 min já costuma ser suficiente na maioria das contas;
os dados do X-Ray/CloudWatch da rodada te dizem se funcionou, pela
presença de `Init Duration`).

## 3. `extract_k6_metrics.py` — resume o arquivo de resultados do k6

Roda por streaming (não carrega o arquivo inteiro em memória), então funciona
mesmo em arquivos de centenas de MB a poucos GB. Rode **no seu terminal
local** (não há limite de tempo lá, ao contrário do ambiente do assistente):

```bash
cd k6
# exemplo de rodada definitiva (um target por vez - ver k6/README.md),
# arquivo salvo em results/<perfil>/<linguagem>/<rota>/:
python3 analysis/extract_k6_metrics.py results/spike/go/cpu/run1.json \
    --out-prefix results/spike/go/cpu/run1 \
    --idle 5m --spike-dur 20s --cycles 2 --cold-window 2.0
```

Use os mesmos valores de `--idle`, `--spike-dur` e `--cycles` que você usou
no `k6 run` (variáveis `SPIKE_IDLE_DURATION`, `SPIKE_SPIKE_DURATION`,
`SPIKE_CYCLES`). Gera:

- `<prefix>_summary.json` — estatísticas (count/mean/median/stdev/min/max/
  p90/p95/p99) por `(language, route)` e por métrica k6 (`http_req_duration`,
  `lambda_duration`, `iteration_duration`, taxa de sucesso etc.), mais uma
  comparação `cold` (primeiros `--cold-window` segundos de cada pico) vs
  `warm_burst` (resto do pico) vs `idle`.
- `<prefix>_cycle_buckets.csv` — a curva de latência dentro de cada pico, em
  buckets de 1s (`--bucket-seconds`), por linguagem. É o gráfico mais direto
  para mostrar visualmente a diferença Go vs Quarkus no cold start.
- `<prefix>_timeseries.csv` — requisições por segundo por target, útil para
  conferir se a carga realizada bateu com o esperado e plotar throughput —
  foi assim que os achados 1 e 2 acima foram descobertos.

Funciona para qualquer arquivo de saída do k6 (`spike-all.json`,
`load-all.json` etc.) — basta apontar o `--idle`/`--spike-dur`/`--cycles`
corretos (para `load.js` esses três parâmetros não se aplicam; a
classificação cold/warm só faz sentido para o perfil spike).

## 4. `aws_cloudwatch_xray_metrics.py` — a métrica de cold start "de verdade"

O k6 só enxerga o tempo de resposta HTTP fim-a-fim (rede + fila + init +
execução) — ele não sabe dizer com certeza se uma requisição foi cold ou
warm start. A AWS sabe: toda invocação que criou um novo ambiente de
execução grava, no CloudWatch Logs, uma linha `REPORT ... Init Duration: X
ms`; toda invocação warm não tem esse campo. Esse script consulta o
CloudWatch Logs Insights para extrair essa métrica diretamente, sem
depender do k6. Existe um cruzamento opcional com o X-Ray (`--with-xray`),
mas o X-Ray Active Tracing foi desativado nas Lambdas em 27/08/2026 (gerava
custo e, no MVP rodado, não trouxe nenhum dado utilizável — ver seção 9 do
`results/mvps/spike/mvp-spike-aws_relatorio.md`), então não há mais motivo para usar essa flag.

**Importante:** este ambiente (assistente) não tem acesso à sua conta AWS
nem rede liberada para chamar a API da AWS — rode este script no seu
terminal local, onde você já tem `aws configure` / `AWS_PROFILE`
configurados:

```bash
pip install boto3

python3 k6/analysis/aws_cloudwatch_xray_metrics.py \
    --functions tcc-lambda-benchmark-dev-go-cpu \
    --start "2026-08-24T22:11:48-03:00" \
    --end   "2026-08-24T22:27:35-03:00" \
    --region us-east-1 \
    --out-prefix k6/results/spike/go/cpu/run1-aws
```

(Sem `--with-xray` — X-Ray Active Tracing foi desativado nas Lambdas, então
essa consulta não encontraria mais nenhum trace.)

- Ajuste `--functions` para os nomes reais das suas Lambdas (padrão de
  nomenclatura: `${project_name}-${environment}-<chave>`, ex.
  `tcc-lambda-benchmark-dev-go-cpu` — confira com
  `terraform output -json lambda_function_names` dentro de `terraform/`).
- `--start`/`--end`: use o campo `"t0"` do `<prefix>_summary.json` gerado
  pelo `extract_k6_metrics.py` para o início, e o timestamp da última linha
  do arquivo k6 (`tail -c 2000 results/spike/go/cpu/run1.json`) para o fim. Dê uma
  folga de alguns segundos para os dois lados.
- Sem correlação requisição-a-requisição com o k6: as Lambdas deste projeto
  não devolvem um request id no corpo da resposta (conferido em
  `apps/go/cpu/main.go` e `CpuLambda.java`), então o script filtra por
  função + janela de tempo, o que é suficiente porque o k6 nunca roda dois
  perfis em paralelo contra a mesma Lambda.

Gera, por função: `<prefix>_<funcao>_invocations.csv` (uma linha por
invocação, com `duration_ms`, `billed_duration_ms`, `memory_size_mb`,
`max_memory_used_mb`, `init_duration_ms`, `is_cold_start`) e um
`<prefix>_summary.json` consolidado com:

- `cold_start_rate` e estatísticas de `init_duration_ms` (a métrica "Latência
  de Cold Start" da seção 4.2 do artigo) por função;
- estatísticas de `duration_ms` para warm start (a métrica "Tempo de
  Execução em Warm Start");
- estatísticas de `max_memory_used_mb` (a métrica "Consumo Máximo de
  Memória");
- estimativa de custo em USD (a métrica "Custo Financeiro Estimado"),
  calculada com `Billed Duration × Memory Size` e os preços atuais do AWS
  Lambda on-demand x86 em `us-east-1` (US$ 0,20 por 1M requisições + US$
  0,0000166667 por GB-segundo — conferido em aws.amazon.com/lambda/pricing
  em agosto/2026; passe `--price-per-1m-requests`/`--price-per-gb-second`
  se quiser atualizar); use `--projected-monthly-invocations N` para
  projetar o custo mensal a partir do perfil observado no teste.
- (`--with-xray`, legado): `xray_initialization_subsegment_ms`. Não usar mais
  — o X-Ray Active Tracing foi desativado nas Lambdas (ver `terraform/modules/lambda/main.tf`),
  e mesmo quando estava ligado esse campo veio `null` no MVP.

## 5. Como isso mapeia para o capítulo de Resultados do TCC

| Métrica do artigo (seção 4.2)      | De onde vem                                                        |
| ----------------------------------- | -------------------------------------------------------------------- |
| Latência de Cold Start (ms)         | `aws_cloudwatch_xray_metrics.py` → `cold_start_init_duration_ms`     |
| Tempo de Execução em Warm Start (ms)| `aws_cloudwatch_xray_metrics.py` → `warm_start_duration_ms`; cruzar com `extract_k6_metrics.py` → `cold_vs_warm_http_req_duration_ms.warm_burst`/`idle` |
| Consumo Máximo de Memória (MB)      | `aws_cloudwatch_xray_metrics.py` → `max_memory_used_mb_all`          |
| Custo Financeiro Estimado (USD)     | `aws_cloudwatch_xray_metrics.py` → `cost_estimate`                   |
| Estatística descritiva (média, mediana, p90, p99) | já calculada em ambos os scripts para cada métrica acima |

Recomendação de fluxo por rodada de teste:

1. Se ainda não sabe o teto de concorrência da conta, rodar
   `discover-concurrency.js` + `analyze_discovery.py` (seção 2) uma vez.
2. Rodar o spike já ajustado (`SPIKE_PEAK_VUS` seguro, `SPIKE_RAMPDOWN_DURATION`
   aplicado, `STAGGER_TARGETS=true` se for testar as duas linguagens juntas).
3. `extract_k6_metrics.py` no arquivo gerado → visão do lado do cliente
   (latência HTTP, throughput realizado, taxa de sucesso — confira que a
   taxa de 429 caiu para perto de 0%).
4. `aws_cloudwatch_xray_metrics.py` na mesma janela de tempo → visão do
   lado do servidor (cold start real, memória, custo).
5. Repetir para `go-cpu` vs `quarkus-cpu`, depois para os outros cenários
   (`concurrency`, `io`) e para o perfil `load` (aí sem classificação
   cold/warm — é só warm start em regime estável).
6. Repetir a rodada completa algumas vezes (o próprio artigo recomenda
   múltiplas repetições, seção "Notas" do `k6/README.md`) para reduzir
   ruído de infraestrutura antes de consolidar os números finais.

## 6. Nota sobre o PDF do artigo

O arquivo `artigo/TCC_GabrielResende.pdf` versionado atualmente no repositório
está corrompido — cerca de 68% dos bytes binários foram substituídos pelo
caractere de substituição Unicode (`U+FFFD`), o que indica que, em algum
ponto, o arquivo foi lido/regravado como texto UTF-8 em vez de binário (git
sem `.gitattributes` marcando `*.pdf` como binário é a causa mais provável —
já criei um `.gitattributes` para isso). Recuperei uma versão anterior e
íntegra a partir do commit `310c6ff` (`artigo/TCC_GabrielResende_v1_git310c6ff.pdf`,
10 páginas — é a versão de qualificação/TCC I, sem o capítulo de
resultados). Essa versão foi a que usei para seguir a metodologia do artigo
nesta análise. **Recomendo recomitar uma cópia íntegra da versão atual/completa
do artigo** (exportando de novo do Overleaf/LaTeX) assim que possível.
