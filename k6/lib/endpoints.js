import { check } from 'k6';
import http from 'k6/http';

import { getHttpTimeout, getPayloadConfig } from '../config/env.js';
import { lambdaDuration, lambdaRequests, lambdaSuccess } from './metrics.js';

function buildRequestBody(route) {
  const payload = getPayloadConfig();

  switch (route) {
    case 'cpu':
      return JSON.stringify({ number: payload.cpuNumber });
    case 'concurrency':
      return JSON.stringify({ tasks: payload.concurrencyTasks });
    case 'io':
      return JSON.stringify({});
    default:
      throw new Error(`Rota desconhecida: ${route}`);
  }
}

export function invokeEndpoint(endpoint) {
  const tags = {
    language: endpoint.language,
    route: endpoint.route,
    target: endpoint.key,
  };

  const body = buildRequestBody(endpoint.route);
  const params = {
    tags,
    timeout: getHttpTimeout(),
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const response = http.post(endpoint.url, body, params);

  const success = check(
    response,
    {
      'status is 200': (res) => res.status === 200,
      'response has body': (res) => res.body && res.body.length > 0,
    },
    tags,
  );

  lambdaDuration.add(response.timings.duration, tags);
  lambdaSuccess.add(success, tags);
  lambdaRequests.add(1, tags);

  return response;
}
