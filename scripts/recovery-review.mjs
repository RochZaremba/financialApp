import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const directory = `artifacts/ui-review/recovery-${pass}`;
await fs.mkdir(directory, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
});
const errors = [];
try {
  const context = await browser.newContext({
    baseURL: "http://localhost:3000",
    locale: "pl-PL",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  const email = `recovery-review-${pass}@example.com`;
  const old = process.env.ADMIN_REVIEW_USER_PASSWORD;
  const password = `${old}-new`;
  const key = process.env[`RECOVERY_REVIEW_KEY_${pass}`];
  assert.ok(key);
  assert.equal(
    (
      await context.request.post("/api/auth/register", {
        data: { email, password: old },
      })
    ).status(),
    201,
  );
  const viewports = [
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 },
  ];
  async function review(state) {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expect(page.locator("h1")).toBeVisible();
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
        state,
      );
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      assert.deepEqual(axe.violations, [], `${state} ${viewport.width}`);
      await page.screenshot({
        path: `${directory}/${state}-${viewport.width}.png`,
        fullPage: true,
      });
    }
  }
  await page.goto("/odzyskaj");
  await expect(
    page.getByRole("heading", { name: "Odzyskaj dostęp" }),
  ).toBeVisible();
  await review("empty");
  await page.getByLabel("Adres e-mail", { exact: true }).fill(email);
  // Incorrect synthetic code, not a real user's bearer token.
  await page
    .getByLabel("Klucz odzyskiwania", { exact: true })
    .fill("invalid-test-key".repeat(5));
  await page.getByLabel("Nowe hasło", { exact: true }).fill(password);
  await page
    .getByLabel("Powtórz nowe hasło", { exact: true })
    .fill(password + "different");
  await page.getByRole("button", { name: "Ustaw nowe hasło" }).click();
  await expect(page.locator(".notice[role=alert]")).toContainText(
    "Hasła muszą być takie same",
  );
  await page.getByLabel("Powtórz nowe hasło", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Ustaw nowe hasło" }).click();
  await expect(page.locator(".notice[role=alert]")).toContainText(
    "Klucz odzyskiwania jest nieprawidłowy",
  );
  await review("invalid");
  await page.getByLabel("Klucz odzyskiwania", { exact: true }).fill(key);
  await page.getByRole("button", { name: "Ustaw nowe hasło" }).click();
  await expect(
    page.getByRole("heading", { name: "Hasło zmienione" }),
  ).toBeVisible();
  await review("success");
  await page.getByRole("link", { name: "Przejdź do logowania" }).click();
  await expect(page.getByLabel("Hasło", { exact: true })).toBeVisible();
  assert.equal((await context.request.get("/api/auth/me")).status(), 401);
  assert.equal(
    (
      await context.request.post("/api/auth/login", {
        data: { email, password: old },
      })
    ).status(),
    401,
  );
  assert.equal(
    (
      await context.request.post("/api/auth/login", {
        data: { email, password },
      })
    ).status(),
    200,
  );
  assert.equal(
    (
      await context.request.post("/api/auth/recover", {
        data: { email, key, password, password_confirmation: password },
      })
    ).status(),
    400,
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^Cześć,/ })).toBeVisible();
  assert.deepEqual(errors, []);
  console.log(
    `Recovery pass ${pass}: real signed reset, password confirmation, generic error, session revocation, new login, replay denial and 12 viewport/accessibility checks passed`,
  );
} finally {
  await browser.close();
}
