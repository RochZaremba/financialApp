import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const base = process.env.BASE_URL || "http://localhost:3000";
const dir = `artifacts/ui-review/${process.argv[2] || "gemini"}`;
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
  serviceWorkers: "block",
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
let available = true;
// Capability metadata only: this does not simulate Gemini extraction.
await page.route("**/api/auth/me", async (route) => {
  const response = await route.fetch();
  if (response.ok()) {
    await route.fulfill({
      response,
      json: {
        ...(await response.json()),
        receipt_provider: "gemini",
        receipt_ai_available: available,
      },
    });
  } else await route.fulfill({ response });
});
const results = [];
try {
  await page.goto(base);
  await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
  await page.getByRole("heading", { name: "Cześć, Roch." }).waitFor();
  for (available of [true, false]) {
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 430, height: 932 },
      { width: 768, height: 1024 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto(base + "/dodaj");
      await page.locator("main h1").waitFor();
      await page.evaluate(() => document.fonts.ready);
      const notice = await page.locator(".manual-provider-note").count();
      assert.equal(notice, available ? 0 : 1);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      );
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      await page.screenshot({
        path: `${dir}/${available ? "ready" : "missing-key"}-${viewport.width}.png`,
        fullPage: true,
      });
      results.push({
        available,
        viewport,
        overflow,
        violations: axe.violations,
      });
      assert.equal(overflow, false);
      assert.equal(axe.violations.length, 0);
      console.log(
        available ? "Gemini ready" : "Gemini missing key",
        viewport.width,
        "clean",
      );
    }
  }
  assert.deepEqual(errors, []);
  await fs.writeFile(
    `${dir}/results.json`,
    JSON.stringify({ errors, results }, null, 2),
  );
} finally {
  await browser.close();
}
