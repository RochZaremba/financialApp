import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const directory = `artifacts/ui-review/admin-${pass}`;
await fs.mkdir(directory, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
});
const baseURL = "http://localhost:3000";
const errors = [];
const results = [];
try {
  const admin = await browser.newContext({
    baseURL,
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    serviceWorkers: "block",
  });
  const ordinary = await browser.newContext({
    baseURL,
    locale: "pl-PL",
    serviceWorkers: "block",
  });
  const page = await admin.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  const userEmail = `recovery-${pass}@example.com`;
  let response = await ordinary.request.post("/api/auth/register", {
    data: {
      email: userEmail,
      password: process.env.ADMIN_REVIEW_USER_PASSWORD,
      name: "Osoba",
    },
  });
  assert.equal(response.status(), 201);
  await page.goto("/administrator");
  await page
    .getByLabel("Adres e-mail", { exact: true })
    .fill(process.env.ADMIN_REVIEW_EMAIL);
  await page
    .getByLabel("Hasło", { exact: true })
    .fill(process.env.ADMIN_REVIEW_PASSWORD);
  await page.getByRole("button", { name: "Zaloguj się", exact: true }).click();
  await page.getByRole("heading", { name: "Panel administratora" }).waitFor();
  await page.getByLabel("E-mail użytkownika").fill(userEmail);
  await page
    .getByLabel("Nowe hasło użytkownika", { exact: true })
    .fill("new-private-password");
  await page.getByLabel("Powtórz nowe hasło").fill("different-password");
  await page
    .getByLabel("Twoje hasło administratora")
    .fill(process.env.ADMIN_REVIEW_PASSWORD);
  await page.getByRole("button", { name: "Zmień hasło użytkownika" }).click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Nowe hasła muszą być takie same" })
    .waitFor();
  await page.getByLabel("Powtórz nowe hasło").fill("new-private-password");
  await page
    .getByLabel("Twoje hasło administratora")
    .fill("incorrect-password");
  await page.getByRole("button", { name: "Zmień hasło użytkownika" }).click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Nieprawidłowe hasło administratora" })
    .waitFor();
  assert.equal(
    await page.getByLabel("Twoje hasło administratora").inputValue(),
    "",
  );
  assert.equal((await ordinary.request.get("/api/auth/me")).status(), 200);
  await page
    .getByLabel("Twoje hasło administratora")
    .fill(process.env.ADMIN_REVIEW_PASSWORD);
  await page.getByRole("button", { name: "Zmień hasło użytkownika" }).click();
  await page
    .getByRole("status")
    .filter({ hasText: "Hasło zostało zmienione" })
    .waitFor();
  assert.equal(
    await page
      .getByLabel("Nowe hasło użytkownika", { exact: true })
      .inputValue(),
    "",
  );
  assert.equal((await ordinary.request.get("/api/auth/me")).status(), 401);
  response = await ordinary.request.post("/api/auth/login", {
    data: {
      email: userEmail,
      password: process.env.ADMIN_REVIEW_USER_PASSWORD,
    },
  });
  assert.equal(response.status(), 401);
  response = await ordinary.request.post("/api/auth/login", {
    data: { email: userEmail, password: "new-private-password" },
  });
  assert.equal(response.status(), 200);
  response = await ordinary.request.post("/api/admin/password-reset", {
    data: {
      email: userEmail,
      password: "another-private-password",
      admin_password: "new-private-password",
    },
  });
  assert.equal(response.status(), 403);
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: `${directory}/administrator-${viewport.width}.png`,
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    assert.deepEqual(
      axe.violations.map((v) => v.id),
      [],
    );
    results.push({ width: viewport.width, overflow: false, axeViolations: 0 });
  }
  await page.getByRole("link", { name: "Utwórz dom", exact: true }).click();
  await page.getByLabel("Nazwa gospodarstwa").waitFor();
  await page.goto("/administrator");
  const householdName = `Dom administratora ${pass}`;
  response = await admin.request.post("/api/households", {
    data: { name: householdName },
    headers: { "Idempotency-Key": `admin-navigation-${pass}` },
  });
  assert.equal(response.status(), 201);
  const householdId = (await response.json()).id;
  await page.goto("/");
  await page.getByRole("heading", { name: "Cześć, Administrator." }).waitFor();
  await page.getByRole("link", { name: "Administrator", exact: true }).click();
  await page.getByRole("heading", { name: "Panel administratora" }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/wiecej");
  await page
    .getByRole("link", { name: "Administrator Przywracanie dostępu do kont" })
    .click();
  await page.getByRole("heading", { name: "Panel administratora" }).waitFor();
  response = await admin.request.delete(`/api/households/${householdId}`, {
    data: { name: householdName },
  });
  assert.equal(response.status(), 200);
  await page.getByRole("button", { name: "Wyloguj", exact: true }).click();
  await page.getByRole("heading", { name: "Witaj z powrotem." }).waitFor();
  await page.getByText("Nie pamiętasz hasła?", { exact: false }).waitFor();
  const ordinaryPage = await ordinary.newPage();
  await ordinaryPage.goto("/administrator");
  await ordinaryPage
    .getByRole("alert")
    .filter({ hasText: "Ta strona jest dostępna tylko dla administratora" })
    .waitFor();
  assert.equal(await ordinaryPage.locator("form").count(), 0);
  assert.deepEqual(errors, []);
  await fs.writeFile(
    `${directory}/results.json`,
    JSON.stringify({ pass, results, errors, recovery: "passed" }, null, 2),
  );
  console.log(
    `Admin recovery pass ${pass}: login, validation, reauthentication, reset, session revocation, access denial, desktop/mobile navigation and 4 viewports passed`,
  );
} finally {
  await browser.close();
}
