const path = require('path');
const config = {
  testDir: path.resolve(__dirname),
  timeout: 120000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: path.join(__dirname, '__results__', 'test-results.json') }]],
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        channel: undefined,
        launchOptions: { args: ['--no-sandbox', '--disable-dev-shm-usage'] },
      },
    },
  ],
};
module.exports = config;
