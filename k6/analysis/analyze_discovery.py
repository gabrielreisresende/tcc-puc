#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_discovery.py
======================

Le o arquivo JSON gerado por `discover-concurrency.js` (--out json=...) e
mostra, degrau a degrau (1, 2, 4, 8, 16, 32, 64 VUs por padrao), quantas
requisicoes tiveram sucesso (200) vs throttling (429). Serve para achar,
sem precisar pedir aumento de cota na AWS, o maior nivel de concorrencia
que a sua conta/funcao aguenta sem throttling -- numero que voce deve usar
(com margem) em SPIKE_PEAK_VUS no teste de spike principal.

Uso:
    python3 analyze_discovery.py results/discovery-go-cpu.json \
        --steps 1,2,4,8,16,32,64 --step-duration 15s
"""
import argparse
import json
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime

_DUR_RE = re.compile(r"(\d+(?:\.\d+)?)(h|m|s)")
_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?([+-]\d{2}:\d{2}|Z)?$"
)


def parse_duration(s):
    total = 0.0
    for value, unit in _DUR_RE.findall(s):
        value = float(value)
        total += value * (3600 if unit == "h" else 60 if unit == "m" else 1)
    return total


def parse_ts(s):
    m = _TS_RE.match(s)
    if not m:
        return None
    y, mo, d, h, mi, se, frac, _off = m.groups()
    micro = int((frac or "0").ljust(6, "0")[:6])
    return datetime(int(y), int(mo), int(d), int(h), int(mi), int(se), micro)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--steps", default="1,2,4,8,16,32,64",
                     help="mesma lista usada em DISCOVERY_VU_STEPS")
    ap.add_argument("--step-duration", default="15s",
                     help="mesmo valor usado em DISCOVERY_STEP_DURATION")
    ap.add_argument("--max-429-rate", type=float, default=1.0,
                     help="percentual maximo de 429 tolerado para considerar o degrau 'limpo' (default: 1.0)")
    args = ap.parse_args()

    steps = [int(s.strip()) for s in args.steps.split(",") if s.strip()]
    step_s = parse_duration(args.step_duration)
    boundaries = [(i * step_s, (i + 1) * step_s, vus) for i, vus in enumerate(steps)]

    t0 = None
    counts = defaultdict(Counter)  # vus -> Counter(status)

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"metric":"http_reqs"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "Point":
                continue
            data = obj.get("data", {})
            tags = data.get("tags", {})
            status = tags.get("status", "?")
            ts = parse_ts(data.get("time", ""))
            if ts is None:
                continue
            if t0 is None:
                t0 = ts
            elapsed = (ts - t0).total_seconds()
            for start, end, vus in boundaries:
                if start <= elapsed < end:
                    counts[vus][status] += 1
                    break

    print(f"{'VUs':>5} {'total':>7} {'200':>7} {'429':>7} {'outros':>7} {'%429':>7}")
    safe_max = None
    first_bad = None
    for vus in steps:
        c = counts[vus]
        total = sum(c.values())
        ok = c.get("200", 0)
        throttled = c.get("429", 0)
        other = total - ok - throttled
        pct = (throttled / total * 100) if total else 0.0
        flag = "  <-- throttling aqui" if pct > args.max_429_rate and first_bad is None else ""
        if pct > args.max_429_rate and first_bad is None:
            first_bad = vus
        print(f"{vus:>5} {total:>7} {ok:>7} {throttled:>7} {other:>7} {pct:>6.1f}%{flag}")
        if pct <= args.max_429_rate and total > 0:
            safe_max = vus

    print()
    if safe_max is None:
        print("Nenhum degrau ficou limpo (429 em todos os niveis testados, "
              "inclusive o mais baixo). Rode DISCOVERY_VU_STEPS com valores "
              "menores (ex: 1,1,1) para confirmar se ate 1 VU sofre throttling "
              "-- se sim, o problema pode ser outro (ex: reserved concurrency "
              "= 0 em alguma configuracao, ou throttling de outra origem).",
              file=sys.stderr)
    else:
        recommended = max(1, int(safe_max * 0.7))
        print(f"Maior nivel de VUs sem throttling (<= {args.max_429_rate}% de 429): {safe_max}")
        print(f"SPIKE_PEAK_VUS recomendado (com margem de seguranca ~30%): {recommended}")
        print("Lembre-se: se for testar go-cpu e quarkus-cpu ao mesmo tempo, "
              "some as duas concorrencias (ou use STAGGER_TARGETS=true no "
              "teste de spike principal para nao somar).")


if __name__ == "__main__":
    main()
