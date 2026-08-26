#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_k6_metrics.py
======================

Faz o streaming de um arquivo de resultados k6 (`--out json=results/xxx.json`,
formato NDJSON) e resume as metricas necessarias para o TCC (comparacao
Go vs Quarkus nas AWS Lambdas), sem nunca carregar o arquivo inteiro em
memoria.

Projetado para arquivos grandes (centenas de MB a poucos GB).

Uso:
    python3 extract_k6_metrics.py <arquivo.json> \
        --out-prefix results/spike-cpu \
        --idle 5m --spike-dur 20s --rampdown 2s --cycles 2

As janelas de burst sao calculadas a partir do PRIMEIRO request observado
para cada target (nao de um t0 global) - por isso funciona corretamente
tanto com STAGGER_TARGETS=true (cada target comeca em um instante
diferente) quanto sem.

Gera:
    <prefix>_summary.json    -> stats descritivas por (language, route, metric)
                                 + comparacao cold-window vs resto do burst
    <prefix>_cycle_buckets.csv -> curva de latencia (buckets de 1s) dentro
                                 de cada spike/burst, por linguagem
    <prefix>_timeseries.csv  -> requisicoes por segundo por target (para
                                 conferir se o padrao de carga realizado bate
                                 com o esperado / plotar throughput)

As janelas de "cold start" sao aproximadas a partir da agenda de stages
conhecida (SPIKE_IDLE_DURATION / SPIKE_SPIKE_DURATION / SPIKE_CYCLES) -
e apenas uma aproximacao via latencia HTTP. Para o numero real de cold
starts e o Init Duration reportado pela AWS, cruzar com
`aws_cloudwatch_xray_metrics.py` (usa CloudWatch Logs Insights / X-Ray).
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime

METRICS_OF_INTEREST = {
    "http_req_duration",
    "http_req_waiting",
    "http_req_failed",
    "iteration_duration",
    "lambda_duration",
    "lambda_success",
    "lambda_requests",
    "checks",
    "http_reqs",
    "vus",
    "data_sent",
    "data_received",
}

_DUR_RE = re.compile(r"(\d+(?:\.\d+)?)(h|m|s)")
_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?([+-]\d{2}:\d{2}|Z)?$"
)


def parse_duration(s):
    if not s:
        return 0.0
    total = 0.0
    for value, unit in _DUR_RE.findall(s):
        value = float(value)
        if unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        else:
            total += value
    return total


def parse_ts(s):
    """Parser tolerante para timestamps RFC3339 do k6 (fracao de segundos
    com numero variavel de digitos), sem depender de timezone real -
    usado apenas para calcular tempo decorrido dentro do mesmo arquivo."""
    m = _TS_RE.match(s)
    if not m:
        return None
    y, mo, d, h, mi, se, frac, _off = m.groups()
    micro = int((frac or "0").ljust(6, "0")[:6])
    return datetime(int(y), int(mo), int(d), int(h), int(mi), int(se), micro)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def stats(values):
    if not values:
        return None
    s = sorted(values)
    return {
        "count": len(s),
        "mean": statistics.fmean(s),
        "median": percentile(s, 50),
        "stdev": statistics.pstdev(s) if len(s) > 1 else 0.0,
        "min": s[0],
        "max": s[-1],
        "p90": percentile(s, 90),
        "p95": percentile(s, 95),
        "p99": percentile(s, 99),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="arquivo de resultados k6 (NDJSON)")
    ap.add_argument("--out-prefix", default=None, help="prefixo dos arquivos de saida")
    ap.add_argument("--idle", default="5m", help="SPIKE_IDLE_DURATION usado no teste")
    ap.add_argument("--spike-dur", default="20s", help="SPIKE_SPIKE_DURATION usado no teste")
    ap.add_argument("--rampdown", default="2s", help="SPIKE_RAMPDOWN_DURATION usado no teste (default do k6/config/env.js: 2s)")
    ap.add_argument("--cycles", type=int, default=2, help="SPIKE_CYCLES usado no teste")
    ap.add_argument("--cold-window", type=float, default=2.0,
                     help="segundos apos o inicio de cada burst considerados 'janela fria' (default: 2.0)")
    ap.add_argument("--bucket-seconds", type=float, default=1.0,
                     help="tamanho do bucket (s) para a curva dentro do burst e para a serie temporal")
    ap.add_argument("--progress-every", type=int, default=2_000_000,
                     help="a cada N linhas lidas, imprime progresso em stderr")
    args = ap.parse_args()

    prefix = args.out_prefix or args.input.rsplit(".", 1)[0]
    idle_s = parse_duration(args.idle)
    spike_s = parse_duration(args.spike_dur)
    rampdown_s = parse_duration(args.rampdown)
    cycle_len = idle_s + spike_s + rampdown_s

    # bursts[i] = (start_elapsed, end_elapsed), com elapsed medido a partir
    # do PRIMEIRO request observado para aquele target (t0_by_target) - nao
    # do inicio "teorico" do scenario. Se o stage de idle realmente suprime
    # todo o trafego (como deveria, com o fix de SPIKE_RAMPDOWN_DURATION +
    # startVUs:0), a primeira requisicao de cada target JA E o inicio do
    # primeiro burst - por isso o burst 0 comeca em elapsed=0, nao em
    # elapsed=idle_s. Bursts seguintes ficam espacados por cycle_len.
    bursts = [(i * cycle_len, i * cycle_len + spike_s) for i in range(args.cycles)]

    groups = defaultdict(lambda: defaultdict(list))          # (lang, route)[metric] -> [values]
    cold_vs_warm = defaultdict(lambda: defaultdict(list))    # (lang, route)["cold"|"warm_burst"|"idle"] -> [http_req_duration]
    cycle_buckets = defaultdict(list)                        # (lang, route, burst_idx, bucket_idx) -> [values]
    per_second_reqs = defaultdict(lambda: defaultdict(int))  # target -> second_bucket -> count

    # t0 por TARGET (nao um t0 global unico): com STAGGER_TARGETS=true cada
    # target comeca seus stages em um instante diferente dentro do mesmo
    # arquivo, entao "tempo decorrido desde o inicio do teste" so faz
    # sentido calculado a partir do primeiro timestamp daquele MESMO target.
    t0_by_target = {}
    t0_global = None
    n_lines = 0
    n_points = 0
    n_bad_ts = 0
    metric_names_seen = set()

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            n_lines += 1
            if args.progress_every and n_lines % args.progress_every == 0:
                print(f"[{n_lines:,} linhas lidas | {n_points:,} points processados]", file=sys.stderr)

            if '"type":"Point"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "Point":
                continue

            metric = obj.get("metric")
            if metric not in METRICS_OF_INTEREST:
                continue
            metric_names_seen.add(metric)

            data = obj.get("data", {})
            tags = data.get("tags", {})
            lang = tags.get("language")
            route = tags.get("route")
            target = tags.get("target")
            value = data.get("value")
            ts_raw = data.get("time")

            ts = parse_ts(ts_raw) if ts_raw else None
            if ts is None and ts_raw:
                n_bad_ts += 1

            if ts is not None and t0_global is None:
                t0_global = ts

            elapsed = None
            if ts is not None and target:
                if target not in t0_by_target:
                    t0_by_target[target] = ts
                elapsed = (ts - t0_by_target[target]).total_seconds()

            if lang and route and value is not None:
                groups[(lang, route)][metric].append(value)

            if metric == "http_req_duration" and lang and route and elapsed is not None:
                key = (lang, route)
                bucket_label = "idle"
                for bi, (bstart, bend) in enumerate(bursts):
                    if bstart <= elapsed < bend:
                        bucket_label = "warm_burst" if (elapsed - bstart) >= args.cold_window else "cold"
                        bucket_idx = int((elapsed - bstart) // args.bucket_seconds)
                        cycle_buckets[(lang, route, bi, bucket_idx)].append(value)
                        break
                cold_vs_warm[key][bucket_label].append(value)

            if metric == "http_reqs" and target and elapsed is not None:
                sec_bucket = int(elapsed // args.bucket_seconds)
                per_second_reqs[target][sec_bucket] += 1

            n_points += 1

    # ---- monta summary.json -------------------------------------------------
    summary = {
        "input_file": args.input,
        "lines_read": n_lines,
        "points_processed": n_points,
        "bad_timestamps": n_bad_ts,
        "metric_names_seen": sorted(metric_names_seen),
        "t0": t0_global.isoformat() if t0_global else None,
        "t0_by_target": {t: ts.isoformat() for t, ts in sorted(t0_by_target.items())},
        "config": {
            "idle_seconds": idle_s,
            "spike_seconds": spike_s,
            "rampdown_seconds": rampdown_s,
            "cycles": args.cycles,
            "cold_window_seconds": args.cold_window,
            "bursts_elapsed_seconds_from_target_first_request": bursts,
        },
        "by_language_route": {},
        "cold_vs_warm_http_req_duration_ms": {},
    }

    for (lang, route), metrics in sorted(groups.items()):
        key = f"{lang}:{route}"
        summary["by_language_route"][key] = {m: stats(v) for m, v in sorted(metrics.items())}
        # taxa de sucesso a partir de http_req_failed (0/1) quando presente
        if "http_req_failed" in metrics:
            failed = metrics["http_req_failed"]
            summary["by_language_route"][key]["success_rate"] = 1 - (sum(failed) / len(failed))

    for (lang, route), buckets in sorted(cold_vs_warm.items()):
        key = f"{lang}:{route}"
        summary["cold_vs_warm_http_req_duration_ms"][key] = {
            label: stats(values) for label, values in buckets.items()
        }

    with open(f"{prefix}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ---- cycle_buckets.csv (curva de latencia dentro do burst) -------------
    with open(f"{prefix}_cycle_buckets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["language", "route", "burst_index", "bucket_start_s", "count", "mean_ms", "median_ms", "p90_ms", "p95_ms", "max_ms"])
        for (lang, route, bi, bidx), values in sorted(cycle_buckets.items()):
            st = stats(values)
            w.writerow([
                lang, route, bi, round(bidx * args.bucket_seconds, 3),
                st["count"], round(st["mean"], 3), round(st["median"], 3),
                round(st["p90"], 3), round(st["p95"], 3), round(st["max"], 3),
            ])

    # ---- timeseries.csv (requisicoes por segundo por target) ---------------
    with open(f"{prefix}_timeseries.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["target", "second_bucket_start_s", "request_count"])
        for target, buckets in sorted(per_second_reqs.items()):
            for sec, count in sorted(buckets.items()):
                w.writerow([target, sec * args.bucket_seconds, count])

    print(f"OK. linhas={n_lines:,} points={n_points:,} bad_ts={n_bad_ts}", file=sys.stderr)
    print(f"-> {prefix}_summary.json", file=sys.stderr)
    print(f"-> {prefix}_cycle_buckets.csv", file=sys.stderr)
    print(f"-> {prefix}_timeseries.csv", file=sys.stderr)


if __name__ == "__main__":
    main()
