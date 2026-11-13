import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.e2e.ts',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: process.env.APP_URL || 'http://127.0.0.1:7007',
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      channel: 'chrome',
      args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    },
  },
})
