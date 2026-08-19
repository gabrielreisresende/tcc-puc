import { getActiveEndpoints, getEndpointByKey } from '../config/env.js';
import { invokeEndpoint } from './endpoints.js';

/**
 * Cria um scenario K6 por endpoint ativo, compartilhando o mesmo perfil de carga.
 * Cada scenario injeta TARGET_KEY via env para identificar qual Lambda chamar.
 */
export function buildEndpointScenarios(stages) {
  const endpoints = getActiveEndpoints();
  const scenarios = {};

  for (const endpoint of endpoints) {
    scenarios[endpoint.key] = {
      executor: 'ramping-vus',
      startTime: '0s',
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
  }

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
