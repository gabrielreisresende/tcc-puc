/**
 * Teste de Pico (Spike) — foco em Cold Start.
 *
 * Períodos prolongados de inatividade (0 VUs) intercalados com injeções
 * abruptas e curtas de carga alta.
 */
import { getSpikeStages } from './config/env.js';
import { buildEndpointScenarios, getThresholds, runTarget } from './lib/scenarios.js';

export { runTarget };

export const options = {
  scenarios: buildEndpointScenarios(getSpikeStages()),
  thresholds: getThresholds(),
  tags: {
    test_profile: 'spike',
  },
};

export function setup() {
  const stages = getSpikeStages();
  console.log(`[spike] stages: ${JSON.stringify(stages)}`);
}
