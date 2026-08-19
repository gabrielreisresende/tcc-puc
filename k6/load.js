/**
 * Teste de Carga (Load) — foco em Warm Start.
 *
 * Ramp-up moderado, platô longo com alta concorrência e ramp-down gradual.
 */
import { getLoadStages } from './config/env.js';
import { buildEndpointScenarios, getThresholds, runTarget } from './lib/scenarios.js';

export { runTarget };

export const options = {
  scenarios: buildEndpointScenarios(getLoadStages()),
  thresholds: getThresholds(),
  tags: {
    test_profile: 'load',
  },
};

export function setup() {
  const stages = getLoadStages();
  console.log(`[load] stages: ${JSON.stringify(stages)}`);
}
