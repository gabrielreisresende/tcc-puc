import { Counter, Rate, Trend } from 'k6/metrics';

/** Duração das requisições por linguagem/rota (complementa http_req_duration). */
export const lambdaDuration = new Trend('lambda_duration', true);

/** Taxa de sucesso agregada (checks + status 200). */
export const lambdaSuccess = new Rate('lambda_success');

/** Contador total de requisições disparadas. */
export const lambdaRequests = new Counter('lambda_requests');
