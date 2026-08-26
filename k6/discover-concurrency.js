/**
 * Descoberta empírica do teto de concorrência (Concurrent Executions) da
 * conta/função AWS Lambda — sem precisar de acesso ao console de Service
 * Quotas nem pedir aumento de cota.
 *
 * Sobe VUs em degraus curtos (1, 2, 4, 8, 16, 32, 64 por padrão) contra UM
 * único target e registra, degrau a degrau, quantas requisições vieram com
 * status 200 vs 429 (Too Many Requests = throttling de concorrência
 * excedida). Analise o resultado com `analysis/analyze_discovery.py` para
 * achar o maior nível de VUs que ainda roda limpo — esse número (com uma
 * margem de segurança) é o que você deve usar em SPIKE_PEAK_VUS.
 *
 * Uso (rode um target por vez):
 *   k6 run -e URL_GO_CPU="https://7ws63hhrchpx5ciaageqby2o4m0ppzye.lambda-url.us-east-1.on.aws/\
 *     -e DISCOVERY_VU_STEPS=1,2,4,8,16,32,64 -e DISCOVERY_STEP_DURATION=15s \
 *     --out json=results/discovery-go-cpu.json \
 *     discover-concurrency.js
 *
 *   k6 run -e URL_QUARKUS_CPU=... -e TARGETS=quarkus-cpu \
 *     -e DISCOVERY_VU_STEPS=1,2,4,8,16,32,64 -e DISCOVERY_STEP_DURATION=15s \
 *     --out json=results/discovery-quarkus-cpu.json \
 *     discover-concurrency.js
 *
 * O teto costuma ser da CONTA (não da função individual), então rodar para
 * as duas linguagens serve principalmente para confirmar que batem no mesmo
 * número.
 */
import { getDiscoveryStages } from './config/env.js';
import { buildEndpointScenarios, runTarget } from './lib/scenarios.js';

export { runTarget };

export const options = {
  scenarios: buildEndpointScenarios(getDiscoveryStages()),
  tags: {
    test_profile: 'discovery',
  },
};

export function setup() {
  const stages = getDiscoveryStages();
  console.log(`[discovery] stages: ${JSON.stringify(stages)}`);
}
