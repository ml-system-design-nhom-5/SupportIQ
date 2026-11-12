import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: {baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8080', channel: 'msedge', headless: true, trace: 'off'},
  projects: [
    {name: 'desktop', use: {viewport: {width:1440,height:900}}},
    {name: 'tablet', use: {viewport: {width:768,height:1024}}},
    {name: 'mobile', use: {viewport: {width:390,height:844}}},
    {name: 'small-phone', use: {viewport: {width:360,height:800}}},
  ],
})
