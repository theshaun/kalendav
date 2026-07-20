/**
 * Run a single suite from qagate.spec.js.
 *   node tests/visual/run.js smoke     | axe | lighthouse | baseline | journeys | all
 */
const { spawnSync } = require('child_process');
const target = process.argv[2] || 'all';

const SUITE_GREP = {
  smoke:      'smoke:',
  axe:        'axe:',
  lighthouse: 'Lighthouse',
  baseline:   'baseline:',
  journeys:   'journey:',
  all:        '',
}[target];

if (SUITE_GREP === undefined) {
  console.error(`unknown target: ${target}`);
  process.exit(2);
}

const args = [
  'playwright', 'test',
  'tests/visual/qagate.spec.js',
  '--reporter=line',
  '--workers=1',
  SUITE_GREP ? `--grep=${SUITE_GREP}` : '',
].filter(Boolean);

const r = spawnSync('npx', args, { stdio: 'inherit', shell: process.platform === 'win32' });
process.exit(r.status || 0);
