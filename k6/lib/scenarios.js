import { getActiveEndpoints, getEndpointByKey, parseDurationToSeconds } from '../config/env.js';
import { invokeEndpoint } from './endpoints.js';

/**
 * Cria um scenario K6 por endpoint ativo, compartilhando o mesmo perfil de carga.
 * Cada scenario injeta TARGET_KEY via env para identificar qual Lambda chamar.
 *
 * `STAGGER_TARGETS=true` (variável de ambiente) faz os scenarios rodarem em
 * SEQUÊNCIA em vez de em paralelo (cada um só começa quando o anterior
 * termina todos os seus stages). Use isso quando o teto de "Concurrent
 * Executions" da conta AWS for baixo demais para suportar duas Lambdas
 * (ex.: go-cpu e quarkus-cpu) recebendo pico de VUs ao mesmo tempo — ver
 * discover-concurrency.js e k6/analysis/README.md. O trade-off é que as
 * duas linguagens deixam de ser testadas exatamente na mesma janela de
 * tempo (ambiente pode variar um pouco entre uma execução e outra), mas
 * evita que o throttling de uma Lambda contamine os números da outra.
 */
export function buildEndpointScenarios(stages) {
  const endpoints = getActiveEndpoints();
  const scenarios = {};
  const stagger = (__ENV.STAGGER_TARGETS || 'false').toLowerCase() === 'true';
  const totalStageSeconds = stages.reduce(
    (sum, stage) => sum + parseDurationToSeconds(stage.duration),
    0,
  );

  endpoints.forEach((endpoint, index) => {
    const startOffsetSeconds = stagger ? Math.round(index * totalStageSeconds) : 0;

    scenarios[endpoint.key] = {
      executor: 'ramping-vus',
      startVUs: 0,
      startTime: `${startOffsetSeconds}s`,
      gracefulRampDown: __ENV.GRACEFUL_RAMP_DOWN || '30s',
      stages,
      exec: 'runTarget',
      env: {
        TARGET_KEY: endpoint.key,
      },
      tags: {
        language: endpoint.language,
        route: endpoint.route,
        target: endpoint.key,
      },
    };
  });

  return scenarios;
}

export function runTarget() {
  const endpoint = getEndpointByKey(__ENV.TARGET_KEY);
  invokeEndpoint(endpoint);
}

export function getThresholds() {
  return {
    http_req_failed: [`rate<${__ENV.THRESHOLD_HTTP_FAIL_RATE || '0.05'}`],
    lambda_success: [`rate>${__ENV.THRESHOLD_SUCCESS_RATE || '0.95'}`],
    'http_req_duration{language:go}': [`p(95)<${__ENV.THRESHOLD_P95_GO_MS || '30000'}`],
    'http_req_duration{language:quarkus}': [`p(95)<${__ENV.THRESHOLD_P95_QUARKUS_MS || '30000'}`],
  };
}
