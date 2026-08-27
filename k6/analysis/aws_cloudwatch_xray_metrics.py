#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aws_cloudwatch_xray_metrics.py
================================

Coleta as metricas "de verdade" (ground truth da AWS) para o intervalo de
tempo de uma execucao de teste k6: Init Duration (cold start), Duration,
Billed Duration e Max Memory Used, via AWS CloudWatch Logs Insights sobre as
linhas REPORT que o runtime da Lambda escreve a cada invocacao (funciona
independente de X-Ray). Suporta opcionalmente cruzar com o AWS X-Ray
(GetTraceSummaries + BatchGetTraces) para o detalhamento do segmento
"Initialization" de cada trace via --with-xray, mas essa flag esta OBSOLETA:
o X-Ray Active Tracing foi desativado nas Lambdas em 27/08/2026 (custava
dinheiro e, mesmo quando estava ligado, o segmento "Initialization" nunca
apareceu nos traces do MVP - ver k6/results/mvp-spike-aws_relatorio.md secao
9). Nao ha mais motivo para usar --with-xray.

Por que isso complementa o k6:
    - O k6 so enxerga o tempo de resposta HTTP fim-a-fim (rede + fila +
      init + execucao). Ele NAO sabe dizer com certeza se uma requisicao
      foi cold ou warm start.
    - O CloudWatch Logs (linha REPORT ... Init Duration: X ms) e a fonte
      de verdade da AWS: toda invocacao que envolveu inicializar um novo
      ambiente de execucao tem o campo "Init Duration" preenchido; toda
      invocacao warm NAO tem esse campo. Isso vem do runtime da Lambda,
      nao do X-Ray - continua funcionando com tracing desligado.
    - Por isso este script nao tenta casar requisicao-a-requisicao com o k6
      (as Lambdas deste projeto nao devolvem um request id no corpo da
      resposta - ver apps/go/cpu/main.go e CpuLambda.java). Em vez disso,
      ele filtra por JANELA DE TEMPO (a mesma do teste k6) e por FUNCAO, o
      que e suficiente porque o k6 nunca roda dois testes/perfis em paralelo
      contra a mesma Lambda (ver k6/README.md secao "Ordem de execucao
      recomendada").

Pre-requisitos (rode isto onde voce tem credenciais AWS configuradas -
tipicamente o seu terminal local, NAO dentro do assistente):
    pip install boto3
    aws configure     # ou AWS_PROFILE / AWS_ACCESS_KEY_ID+SECRET no ambiente
    # a role/usuario precisa de logs:StartQuery, logs:GetQueryResults (somente leitura)
    # (xray:GetTraceSummaries/BatchGetTraces so sao necessarias se ainda
    # usar --with-xray, o que nao e mais recomendado - ver acima)

Uso:
    python3 aws_cloudwatch_xray_metrics.py \
        --functions tcc-lambda-benchmark-dev-go-cpu tcc-lambda-benchmark-dev-quarkus-cpu \
        --start "2026-08-24T22:11:48-03:00" \
        --end   "2026-08-24T22:27:35-03:00" \
        --region us-east-1 \
        --out-prefix results/spike-cpu-aws \
        --memory-mb 512

O intervalo --start/--end deve cobrir o t0..t_fim do arquivo k6 correspondente
(ver campo "t0" em <prefix>_summary.json gerado por extract_k6_metrics.py; para
o fim, use o ultimo timestamp do arquivo -- ex.: `tail -c 2000 results/spike-cpu.json`).
Vale dar uma folga de alguns segundos para cada lado.

Gera, por funcao:
    <prefix>_<funcao>_invocations.csv
        request_id,timestamp,duration_ms,billed_duration_ms,memory_size_mb,
        max_memory_used_mb,init_duration_ms,is_cold_start
    <prefix>_summary.json
        stats (count/mean/median/stdev/min/max/p90/p95/p99) separadas para
        cold starts (init_duration presente) e warm starts, por funcao,
        alem de:
          - cold_start_rate (cold / total)
          - estimativa de custo (USD) com base no billing real observado
            (Billed Duration x Memory Size) e projecao para N invocacoes/mes
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
import time
from collections import defaultdict

# Precos AWS Lambda x86_64, sob demanda, us-east-1 (conferir em
# https://aws.amazon.com/lambda/pricing/ antes de usar em producao/no TCC -
# consultado em agosto/2026):
DEFAULT_PRICE_PER_1M_REQUESTS_USD = 0.20
DEFAULT_PRICE_PER_GB_SECOND_USD = 0.0000166667

REPORT_RE = re.compile(
    r"REPORT RequestId:\s*(?P<request_id>\S+)\s+"
    r"Duration:\s*(?P<duration>[\d.]+)\s*ms\s+"
    r"Billed Duration:\s*(?P<billed_duration>[\d.]+)\s*ms\s+"
    r"Memory Size:\s*(?P<memory_size>\d+)\s*MB\s+"
    r"Max Memory Used:\s*(?P<max_memory_used>\d+)\s*MB"
    r"(?:\s+Init Duration:\s*(?P<init_duration>[\d.]+)\s*ms)?"
)


def stats(values):
    if not values:
        return None
    s = sorted(values)

    def pct(p):
        k = (len(s) - 1) * (p / 100)
        f, c = math.floor(k), math.ceil(k)
        if f == c:
            return s[int(k)]
        return s[f] * (c - k) + s[c] * (k - f)

    return {
        "count": len(s),
        "mean": statistics.fmean(s),
        "median": pct(50),
        "stdev": statistics.pstdev(s) if len(s) > 1 else 0.0,
        "min": s[0],
        "max": s[-1],
        "p90": pct(90),
        "p95": pct(95),
        "p99": pct(99),
    }


def fetch_report_lines(logs_client, log_group, start_ms, end_ms):
    """Roda uma query no CloudWatch Logs Insights e devolve as linhas REPORT
    cruas (campo @message) do grupo de log da funcao, no intervalo dado."""
    query = (
        'fields @timestamp, @message '
        '| filter @message like /^REPORT/ '
        '| sort @timestamp asc '
        '| limit 10000'
    )
    start_query = logs_client.start_query(
        logGroupName=log_group,
        startTime=start_ms // 1000,
        endTime=end_ms // 1000 + 1,
        queryString=query,
    )
    query_id = start_query["queryId"]

    while True:
        result = logs_client.get_query_results(queryId=query_id)
        status = result["status"]
        if status in ("Complete", "Failed", "Cancelled", "Timeout"):
            break
        time.sleep(1)

    if status != "Complete":
        print(f"AVISO: query no log group {log_group} terminou com status {status}", file=sys.stderr)

    rows = []
    for record in result.get("results", []):
        as_dict = {f["field"]: f["value"] for f in record}
        rows.append(as_dict)
    return rows


def parse_report_rows(rows):
    invocations = []
    for row in rows:
        message = row.get("@message", "")
        m = REPORT_RE.search(message)
        if not m:
            continue
        d = m.groupdict()
        invocations.append({
            "timestamp": row.get("@timestamp"),
            "request_id": d["request_id"],
            "duration_ms": float(d["duration"]),
            "billed_duration_ms": float(d["billed_duration"]),
            "memory_size_mb": int(d["memory_size"]),
            "max_memory_used_mb": int(d["max_memory_used"]),
            "init_duration_ms": float(d["init_duration"]) if d["init_duration"] else None,
            "is_cold_start": d["init_duration"] is not None,
        })
    return invocations


def estimate_cost(invocations, price_per_1m_requests, price_per_gb_second, projected_monthly_invocations=None):
    n = len(invocations)
    if n == 0:
        return None
    total_gb_seconds = sum(
        (inv["billed_duration_ms"] / 1000.0) * (inv["memory_size_mb"] / 1024.0)
        for inv in invocations
    )
    request_cost = n * (price_per_1m_requests / 1_000_000)
    compute_cost = total_gb_seconds * price_per_gb_second
    result = {
        "invocations": n,
        "total_gb_seconds": total_gb_seconds,
        "avg_gb_seconds_per_invocation": total_gb_seconds / n,
        "observed_request_cost_usd": request_cost,
        "observed_compute_cost_usd": compute_cost,
        "observed_total_cost_usd": request_cost + compute_cost,
        "price_per_1m_requests_usd": price_per_1m_requests,
        "price_per_gb_second_usd": price_per_gb_second,
    }
    if projected_monthly_invocations:
        avg_gb_s = total_gb_seconds / n
        proj_request_cost = projected_monthly_invocations * (price_per_1m_requests / 1_000_000)
        proj_compute_cost = projected_monthly_invocations * avg_gb_s * price_per_gb_second
        result["projected_monthly_invocations"] = projected_monthly_invocations
        result["projected_monthly_cost_usd"] = proj_request_cost + proj_compute_cost
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--functions", nargs="+", required=True,
                     help="nomes das funcoes Lambda (ex: tcc-lambda-benchmark-dev-go-cpu tcc-lambda-benchmark-dev-quarkus-cpu)")
    ap.add_argument("--start", required=True, help="inicio da janela, ISO8601 (ex: 2026-08-24T22:11:48-03:00)")
    ap.add_argument("--end", required=True, help="fim da janela, ISO8601")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--profile", default=None, help="AWS profile (opcional)")
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--with-xray", action="store_true",
                 help="OBSOLETO: X-Ray Active Tracing foi desativado nas Lambdas em 27/08/2026 ""(gerava custo sem dado util); esta flag so funcionava plenamente antes disso e mesmo assim ""o segmento Initialization nunca foi encontrado (ver mvp-spike-aws_relatorio.md)")
    ap.add_argument("--projected-monthly-invocations", type=int, default=None,
                     help="para projetar custo mensal a partir do perfil observado (ex: 1000000)")
    ap.add_argument("--price-per-1m-requests", type=float, default=DEFAULT_PRICE_PER_1M_REQUESTS_USD)
    ap.add_argument("--price-per-gb-second", type=float, default=DEFAULT_PRICE_PER_GB_SECOND_USD)
    args = ap.parse_args()

    if args.with_xray:
        print("AVISO: --with-xray e obsoleto - X-Ray Active Tracing foi desativado nas "
              "Lambdas em 27/08/2026 (custava dinheiro sem gerar dado usado no TCC). Esta "
              "consulta provavelmente nao vai encontrar traces novos. Ver terraform/modules/"
              "lambda/main.tf e k6/analysis/README.md.", file=sys.stderr)

    try:
        import boto3
    except ImportError:
        print("ERRO: este script precisa do boto3 (`pip install boto3`) e de credenciais AWS "
              "configuradas no ambiente onde ele roda.", file=sys.stderr)
        sys.exit(1)
    from datetime import datetime

    start_dt = datetime.fromisoformat(args.start)
    end_dt = datetime.fromisoformat(args.end)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    logs_client = session.client("logs")
    xray_client = session.client("xray") if args.with_xray else None

    summary = {"window": {"start": args.start, "end": args.end}, "functions": {}}

    for function_name in args.functions:
        log_group = f"/aws/lambda/{function_name}"
        print(f"Consultando {log_group} ...", file=sys.stderr)
        try:
            rows = fetch_report_lines(logs_client, log_group, start_ms, end_ms)
        except Exception as exc:
            print(f"ERRO ao consultar {log_group}: {exc}", file=sys.stderr)
            continue
        invocations = parse_report_rows(rows)
        print(f"  {len(invocations)} invocacoes (linhas REPORT) encontradas", file=sys.stderr)

        out_csv = f"{args.out_prefix}_{function_name}_invocations.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["request_id", "timestamp", "duration_ms", "billed_duration_ms",
                        "memory_size_mb", "max_memory_used_mb", "init_duration_ms", "is_cold_start"])
            for inv in invocations:
                w.writerow([inv["request_id"], inv["timestamp"], inv["duration_ms"],
                            inv["billed_duration_ms"], inv["memory_size_mb"],
                            inv["max_memory_used_mb"], inv["init_duration_ms"] or "",
                            inv["is_cold_start"]])
        print(f"  -> {out_csv}", file=sys.stderr)

        cold = [inv for inv in invocations if inv["is_cold_start"]]
        warm = [inv for inv in invocations if not inv["is_cold_start"]]

        func_summary = {
            "log_group": log_group,
            "total_invocations": len(invocations),
            "cold_start_count": len(cold),
            "cold_start_rate": (len(cold) / len(invocations)) if invocations else None,
            "cold_start_init_duration_ms": stats([i["init_duration_ms"] for i in cold]),
            "cold_start_total_duration_ms": stats([i["duration_ms"] for i in cold]),
            "warm_start_duration_ms": stats([i["duration_ms"] for i in warm]),
            "billed_duration_ms_all": stats([i["billed_duration_ms"] for i in invocations]),
            "max_memory_used_mb_all": stats([i["max_memory_used_mb"] for i in invocations]),
            "cost_estimate": estimate_cost(
                invocations, args.price_per_1m_requests, args.price_per_gb_second,
                args.projected_monthly_invocations,
            ),
        }

        if args.with_xray:
            try:
                trace_summaries = []
                next_token = None
                while True:
                    kwargs = dict(
                        StartTime=start_dt,
                        EndTime=end_dt,
                        FilterExpression=f'service("{function_name}")',
                    )
                    if next_token:
                        kwargs["NextToken"] = next_token
                    resp = xray_client.get_trace_summaries(**kwargs)
                    trace_summaries.extend(resp.get("TraceSummaries", []))
                    next_token = resp.get("NextToken")
                    if not next_token:
                        break
                init_subsegment_ms = []
                trace_ids = [t["Id"] for t in trace_summaries]
                for i in range(0, len(trace_ids), 5):
                    batch = xray_client.batch_get_traces(TraceIds=trace_ids[i:i + 5])
                    for trace in batch.get("Traces", []):
                        for seg in trace.get("Segments", []):
                            doc = json.loads(seg["Document"])
                            for sub in doc.get("subsegments", []) or []:
                                if sub.get("name") == "Initialization":
                                    init_subsegment_ms.append(
                                        (sub["end_time"] - sub["start_time"]) * 1000
                                    )
                func_summary["xray_trace_count"] = len(trace_summaries)
                func_summary["xray_initialization_subsegment_ms"] = stats(init_subsegment_ms)
            except Exception as exc:
                print(f"  AVISO: falha ao consultar X-Ray para {function_name}: {exc}", file=sys.stderr)

        summary["functions"][function_name] = func_summary

    # comparativo direto go vs quarkus, se ambos presentes
    with open(f"{args.out_prefix}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"-> {args.out_prefix}_summary.json", file=sys.stderr)


if __name__ == "__main__":
    main()
