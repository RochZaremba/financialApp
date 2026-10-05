import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120000,
  reporter: [
    ["list"],
    [
      "html",
      { open: "never", outputFolder: "../../artifacts/playwright-report" },
    ],
  ],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    {
      name: "mobile",
      use: {
        ...devices["iPhone 13"],
        defaultBrowserType: "chromium",
        viewport: { width: 390, height: 844 },
      },
    },
    ...(process.env.WEBKIT === "1"
      ? [
          {
            name: "safari-mobile",
            use: { ...devices["iPhone 13"], browserName: "webkit" as const },
          },
        ]
      : []),
  ],
  outputDir: "../../artifacts/e2e-results",
});
