import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const directory = `artifacts/ui-review/ocr-${pass}`;
await fs.mkdir(directory, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
});
const results = [],
  errors = [];
try {
  const context = await browser.newContext({
    baseURL: "http://localhost:3000",
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  let response = await context.request.post("/api/auth/register", {
    data: {
      email: `ocr-review-${pass}@example.com`,
      password: process.env.ADMIN_REVIEW_USER_PASSWORD,
      name: "Odczyt",
    },
  });
  assert.equal(response.status(), 201);
  response = await context.request.post("/api/households", {
    data: { name: `Dom OCR ${pass}` },
    headers: { "Idempotency-Key": `ocr-review-home-${pass}` },
  });
  assert.equal(response.status(), 201);
  const household = (await response.json()).id;
  response = await context.request.post(
    `/api/households/${household}/receipts`,
    {
      multipart: {
        file: {
          name: "lidl.png",
          mimeType: "image/png",
          buffer: await fs.readFile("fixtures/lidl.png"),
        },
      },
    },
  );
  assert.equal(response.status(), 201);
  const receipt = await response.json();
  const url = `/api/households/${household}/receipts/${receipt.id}`;
  await page.goto(`/paragony/${receipt.id}`);
  await page
    .getByLabel("Sklep", { exact: true })
    .fill("Ręczna niezapisana poprawka");

  const failure = {
    id: "mock-gemini-failure",
    created_at: new Date().toISOString(),
    provider: "gemini",
    model: "gemini-3.1-flash-lite",
    status: "failed",
    duration_ms: 75000,
    applied_at: null,
    receipt_updated_at: receipt.updated_at,
    result: null,
    diagnostics: {
      kind: "quota",
      code: "RESOURCE_EXHAUSTED",
      http_status: 429,
      message:
        "Przekroczono limit zapytań dostawcy. Sprawdź limity i rozliczenia.",
      retry_after_seconds: 30,
    },
  };
  await page.route(`**${url}/ocr`, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(failure),
        })
      : route.continue(),
  );
  await page
    .getByRole("button", { name: "Odczytaj ponownie", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ponów odczyt zdjęcia", exact: true })
    .click();
  await page
    .getByRole("alert")
    .filter({ hasText: "RESOURCE_EXHAUSTED" })
    .waitFor();
  assert.equal(
    await page.getByLabel("Sklep", { exact: true }).inputValue(),
    "Ręczna niezapisana poprawka",
  );

  async function capture(state) {
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 430, height: 932 },
      { width: 768, height: 1024 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({
        path: `${directory}/${state}-${viewport.width}.png`,
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
      results.push({
        state,
        width: viewport.width,
        overflow: false,
        axeViolations: 0,
      });
    }
  }
  await capture("gemini-error");
  await page.unroute(`**${url}/ocr`);
  await page
    .getByRole("button", { name: "Odczytaj ponownie", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ponów odczyt zdjęcia", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Wynik ponownego odczytu" })
    .waitFor();
  assert.equal(
    await page.getByLabel("Sklep", { exact: true }).inputValue(),
    "Ręczna niezapisana poprawka",
  );
  assert.equal(
    (await context.request.get(url).then((r) => r.json())).merchant,
    "Lidl",
  );
  await capture("ocr-proposal");
  await page.getByRole("button", { name: "Zastosuj odczyt do szkicu" }).click();
  await page.getByLabel("Sklep", { exact: true }).waitFor();
  await page.waitForFunction(
    () => document.querySelector('input[aria-label="Sklep"]')?.value === "Lidl",
  );
  const current = await context.request.get(url).then((r) => r.json());
  assert.equal(current.merchant, "Lidl");
  let transactions = await context.request
    .get(`/api/households/${household}/transactions?month=2026-10`)
    .then((r) => r.json());
  assert.equal(transactions.items.length, 0);
  const overview = await context.request
    .get(`/api/households/${household}/overview?month=2026-10`)
    .then((r) => r.json());
  const fields = page.getByLabel("Kategoria", { exact: true });
  while (await fields.count()) {
    const count = await fields.count();
    await fields.first().selectOption(overview.categories[0].id);
    await expect(fields).toHaveCount(count - 1);
  }
  await page
    .getByRole("button", { name: "Zatwierdź paragon", exact: true })
    .click();
  await page.waitForURL("http://localhost:3000/");
  transactions = await context.request
    .get(`/api/households/${household}/transactions?month=2026-10`)
    .then((r) => r.json());
  assert.equal(transactions.items.length, 1);
  const transaction = transactions.items[0].id;
  await page.goto(`/paragony/${receipt.id}`);
  await page.getByRole("heading", { name: "Paragon zapisany." }).waitFor();
  await page
    .getByRole("button", { name: "Odczytaj ponownie", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ponów odczyt zdjęcia", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Wynik ponownego odczytu" })
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Zastosuj odczyt do szkicu" })
      .count(),
    0,
  );
  await capture("confirmed-comparison");
  transactions = await context.request
    .get(`/api/households/${household}/transactions?month=2026-10`)
    .then((r) => r.json());
  assert.equal(transactions.items.length, 1);
  assert.equal(transactions.items[0].id, transaction);

  const admin = await browser.newContext({
    baseURL: "http://localhost:3000",
    locale: "pl-PL",
    serviceWorkers: "block",
  });
  response = await admin.request.post("/api/auth/login", {
    data: {
      email: process.env.ADMIN_REVIEW_EMAIL,
      password: process.env.ADMIN_REVIEW_PASSWORD,
    },
  });
  assert.equal(response.status(), 200);
  const adminPage = await admin.newPage();
  await adminPage.goto("/administrator");
  await adminPage.getByRole("heading", { name: "Diagnostyka OCR" }).waitFor();
  await adminPage
    .getByText("Nie ma jeszcze zarejestrowanych prób Gemini ani OpenAI.")
    .waitFor();
  assert.deepEqual(errors, []);
  await fs.writeFile(
    `${directory}/results.json`,
    JSON.stringify(
      {
        pass,
        results,
        errors,
        retry: "passed",
        confirmedTransaction: "unchanged",
      },
      null,
      2,
    ),
  );
  console.log(
    `OCR pass ${pass}: failure codes, preserved edits, stored-image retry, explicit apply, confirmation, immutable booked transaction, admin summary and 12 responsive/accessibility checks passed`,
  );
} finally {
  await browser.close();
}
