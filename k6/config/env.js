/**
 * Centraliza leitura e validação das variáveis de ambiente (__ENV) do K6.
 */

export const TARGET_KEYS = [
  'go-cpu',
  'go-parallel',
  'go-io',
  'quarkus-cpu',
  'quarkus-parallel',
  'quarkus-io',
];

const URL_ENV_MAP = {
  'go-cpu': 'URL_GO_CPU',
  'go-parallel': 'URL_GO_PARALLEL',
  'go-io': 'URL_GO_IO',
  'quarkus-cpu': 'URL_QUARKUS_CPU',
  'quarkus-parallel': 'URL_QUARKUS_PARALLEL',
  'quarkus-io': 'URL_QUARKUS_IO',
};

export function parseIntEnv(name, defaultValue) {
  const raw = __ENV[name];
  if (raw === undefined || raw === '') {
    return defaultValue;
  }

  const value = parseInt(raw, 10);
  if (Number.isNaN(value)) {
    throw new Error(`Variável ${name} deve ser um número inteiro. Valor recebido: "${raw}"`);
  }

  return value;
}

export function parseTargets(targetsEnv) {
  if (!targetsEnv || targetsEnv === 'all') {
    return [...TARGET_KEYS];
  }

  const targets = targetsEnv
    .split(',')
    .map((target) => target.trim())
    .filter(Boolean);

  for (const target of targets) {
    if (!TARGET_KEYS.includes(target)) {
      throw new Error(
        `Target inválido: "${target}". Valores aceitos: ${TARGET_KEYS.join(', ')}, all`,
      );
    }
  }

  return targets;
}

export function getEndpointMetadata(key) {
  const language = key.startsWith('go-') ? 'go' : 'quarkus';

  let route = 'io';
  if (key.endsWith('-cpu')) {
    route = 'cpu';
  } else if (key.endsWith('-parallel')) {
    route = 'parallel';
  }

  return { language, route };
}

export function getUrls() {
  const urls = {};

  for (const [key, envVar] of Object.entries(URL_ENV_MAP)) {
    urls[key] = __ENV[envVar] || '';
  }

  return urls;
}

export function getEndpointByKey(key) {
  const url = getUrls()[key];

  if (!url) {
    throw new Error(`URL não configurada para o target "${key}". Defina ${URL_ENV_MAP[key]}.`);
  }

  const { language, route } = getEndpointMetadata(key);

  return { key, url, language, route };
}

export function getActiveEndpoints() {
  const targets = parseTargets(__ENV.TARGETS);
  const urls = getUrls();
  const missing = [];

  const endpoints = targets
    .filter((key) => {
      if (!urls[key]) {
        missing.push(`${key} (${URL_ENV_MAP[key]})`);
        return false;
      }
      return true;
    })
    .map((key) => {
      const { language, route } = getEndpointMetadata(key);
      return { key, url: urls[key], language, route };
    });

  if (endpoints.length === 0) {
    const hint = missing.length > 0 ? ` URLs ausentes: ${missing.join(', ')}.` : '';
    throw new Error(`Nenhum endpoint ativo para teste.${hint}`);
  }

  return endpoints;
}

export function getPayloadConfig() {
  return {
    cpuNumber: parseIntEnv('PAYLOAD_CPU_NUMBER', 999999999989),
    parallelTasks: parseIntEnv('PAYLOAD_PARALLEL_TASKS', 5000),
  };
}

export function getHttpTimeout() {
  return __ENV.HTTP_TIMEOUT || '60s';
}

/**
 * Perfil Spike — períodos longos de inatividade intercalados com picos abruptos.
 * Objetivo: forçar cold starts repetidos.
 */
export function getSpikeStages() {
  const idleDuration = __ENV.SPIKE_IDLE_DURATION || '5m';
  const spikeDuration = __ENV.SPIKE_SPIKE_DURATION || '30s';
  const peakVus = parseIntEnv('SPIKE_PEAK_VUS', 100);
  const cycles = parseIntEnv('SPIKE_CYCLES', 3);

  const stages = [];

  for (let i = 0; i < cycles; i += 1) {
    stages.push({ duration: idleDuration, target: 0 });
    stages.push({ duration: spikeDuration, target: peakVus });
  }

  stages.push({ duration: idleDuration, target: 0 });

  return stages;
}

/**
 * Perfil Load — ramp-up moderado, platô longo e ramp-down.
 * Objetivo: manter contêineres aquecidos (warm start).
 */
export function getLoadStages() {
  const steadyVus = parseIntEnv('LOAD_STEADY_VUS', 50);

  return [
    { duration: __ENV.LOAD_RAMP_UP_DURATION || '2m', target: steadyVus },
    { duration: __ENV.LOAD_STEADY_DURATION || '10m', target: steadyVus },
    { duration: __ENV.LOAD_RAMP_DOWN_DURATION || '2m', target: 0 },
  ];
}
