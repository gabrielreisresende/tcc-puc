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

/**
 * Converte uma duração no formato do k6 (ex: "5m", "30s", "1h2m3s") para
 * segundos. Usado para calcular offsets de `startTime` entre scenarios
 * (ver `STAGGER_TARGETS` em lib/scenarios.js) e por scripts de análise.
 */
export function parseDurationToSeconds(duration) {
  if (!duration) return 0;
  const re = /(\d+(?:\.\d+)?)(h|m|s)/g;
  let total = 0;
  let match;
  // eslint-disable-next-line no-cond-assign
  while ((match = re.exec(duration)) !== null) {
    const value = parseFloat(match[1]);
    const unit = match[2];
    if (unit === 'h') total += value * 3600;
    else if (unit === 'm') total += value * 60;
    else total += value;
  }
  return total;
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
 *
 * IMPORTANTE sobre o executor `ramping-vus` do k6: ele interpola o número de
 * VUs LINEARMENTE ao longo de toda a duração de cada stage, usando como
 * ponto de partida o valor final do stage anterior. Isso significa que um
 * stage "idle" (target: 0) logo após um stage "spike" (target: peakVus) NÃO
 * derruba as VUs para 0 de forma abrupta — ele as reduz gradualmente durante
 * toda a duração do idle (ex.: com SPIKE_IDLE_DURATION=5m, as VUs só chegam
 * de fato a 0 no fim desses 5 minutos). Na prática isso mantém um tráfego
 * residual constante para a Lambda, o que tende a manter o contêiner quente
 * e IMPEDE a ocorrência do cold start que o teste deveria forçar.
 *
 * Por isso, cada ciclo agora tem um stage extra e curto (`rampDownDuration`)
 * logo após o pico, para levar as VUs a 0 rapidamente; o stage de idle que
 * vem em seguida já começa (e permanece) em 0 pelo tempo configurado,
 * garantindo uma janela real de inatividade antes do próximo pico.
 * `startVUs: 0` (ver lib/scenarios.js) evita o mesmo problema no primeiro
 * stage do teste.
 *
 * SOBRE THROTTLING (HTTP 429): `SPIKE_PEAK_VUS` deve ficar ABAIXO do teto de
 * "Concurrent Executions" da sua conta/função na AWS. Se você não tem como
 * pedir aumento de cota, rode antes `discover-concurrency.js` (neste mesmo
 * diretório) para descobrir esse teto na prática e escolher um
 * SPIKE_PEAK_VUS seguro. Ver k6/analysis/README.md.
 */
export function getSpikeStages() {
  const idleDuration = __ENV.SPIKE_IDLE_DURATION || '5m';
  const spikeDuration = __ENV.SPIKE_SPIKE_DURATION || '30s';
  const rampDownDuration = __ENV.SPIKE_RAMPDOWN_DURATION || '2s';
  const peakVus = parseIntEnv('SPIKE_PEAK_VUS', 100);
  const cycles = parseIntEnv('SPIKE_CYCLES', 3);

  const stages = [];

  for (let i = 0; i < cycles; i += 1) {
    stages.push({ duration: idleDuration, target: 0 });
    stages.push({ duration: spikeDuration, target: peakVus });
    stages.push({ duration: rampDownDuration, target: 0 });
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

/**
 * Perfil Discovery — degraus curtos de VUs (1, 2, 4, 8, 16, ...) contra UM
 * único target, para achar empiricamente o maior nível de concorrência que
 * ainda roda sem erro 429 (throttling de "Concurrent Executions" da AWS
 * Lambda). Útil quando você não tem como pedir aumento de cota/reservar
 * concorrência e precisa descobrir na prática até onde pode ir.
 *
 * Rode com TARGETS=go-cpu (depois de novo com TARGETS=quarkus-cpu, para
 * confirmar que o teto é o mesmo — ele costuma ser da CONTA, não da função).
 * Analise o resultado com `python3 analysis/analyze_discovery.py`.
 */
export function getDiscoveryStages() {
  const steps = (__ENV.DISCOVERY_VU_STEPS || '1,2,4,8,16,32,64')
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !Number.isNaN(n));
  const stepDuration = __ENV.DISCOVERY_STEP_DURATION || '15s';

  const stages = steps.map((vus) => ({ duration: stepDuration, target: vus }));
  stages.push({ duration: '5s', target: 0 });

  return stages;
}
