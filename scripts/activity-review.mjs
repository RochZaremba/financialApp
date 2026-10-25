import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const directory = `artifacts/ui-review/activity-${pass}`;
await fs.mkdir(directory, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
});
const errors = [];
try {
  const options = {
    baseURL: "http://localhost:3000",
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    serviceWorkers: "block",
  };
  const first = await browser.newContext(options);
  const second = await browser.newContext(options);
  const password = process.env.ADMIN_REVIEW_USER_PASSWORD;
  for (const [context, name] of [
    [first, "Roch"],
    [second, "Kaja"],
  ]) {
    assert.equal(
      (
        await context.request.post("/api/auth/register", {
          data: {
            name,
            email: `activity-${name.toLowerCase()}-${pass}@example.com`,
            password,
          },
        })
      ).status(),
      201,
    );
  }
  const homeResponse = await first.request.post("/api/households", {
    data: { name: `Dom aktywności ${pass}` },
    headers: { "Idempotency-Key": `activity-home-${pass}` },
  });
  assert.equal(homeResponse.status(), 201);
  const household = (await homeResponse.json()).id;
  const base = `/api/households/${household}`;
  const invite = await first.request
    .post(`${base}/invitations`)
    .then((r) => r.json());
  assert.equal(
    (
      await second.request.post("/api/households/join", {
        data: { token: invite.token },
      })
    ).status(),
    200,
  );
  const date = new Date().toLocaleDateString("sv-SE", {
    timeZone: "Europe/Warsaw",
  });
  const month = date.slice(0, 7);
  const overview = await first.request
    .get(`${base}/overview?month=${month}`)
    .then((r) => r.json());
  const account = overview.accounts[0].id;
  const category = overview.categories[0].id;
  const page = await first.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("link", { name: "Aktywność", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Aktywność domowników." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Tutaj jeszcze spokojnie." }),
  ).toBeVisible();
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
        `${state}: overflow`,
      );
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      assert.deepEqual(result.violations, [], `${state} ${viewport.width}`);
      await page.screenshot({
        path: `${directory}/${state}-${viewport.width}.png`,
        fullPage: true,
      });
    }
  }
  await review("empty");
  async function transaction(context, kind, amount, description) {
    const response = await context.request.post(`${base}/transactions`, {
      headers: { "Idempotency-Key": `activity-${kind}-${pass}` },
      data: {
        kind,
        amount,
        description,
        date,
        account_id: account,
        allocations:
          kind === "expense" ? [{ category_id: category, amount }] : [],
      },
    });
    assert.equal(response.status(), 201);
    return response.json();
  }
  await transaction(first, "expense", 12345, `Ręczny wydatek ${pass}`);
  await transaction(second, "income", 40001, `Wpływ Kai ${pass}`);
  const uploaded = await first.request.post(`${base}/receipts`, {
    headers: { "Idempotency-Key": `activity-photo-${pass}` },
    multipart: {
      file: {
        name: "lidl.png",
        mimeType: "image/png",
        buffer: await fs.readFile("fixtures/lidl.png"),
      },
    },
  });
  assert.equal(uploaded.status(), 201);
  const receipt = await uploaded.json();
  assert.equal(receipt.created_by_name, "Roch");
  const confirmed = await second.request.post(
    `${base}/receipts/${receipt.id}/finalize`,
    {
      data: {
        merchant: `Paragon Kai ${pass}`,
        date,
        total: 1001,
        account_id: account,
        items: [
          {
            name: "Wspólny zakup",
            amount: 1001,
            category_id: category,
            confidence: 100,
            reviewed: true,
          },
        ],
      },
    },
  );
  assert.equal(confirmed.status(), 200);
  assert.equal((await confirmed.json()).created_by_name, "Kaja");
  const totals = await first.request
    .get(`${base}/activity?month=${month}`)
    .then((r) => r.json());
  assert.deepEqual(totals.totals, {
    receipts: 1,
    expenses: 2,
    expense_amount: 13346,
    incomes: 1,
    income_amount: 40001,
  });
  await page.goto("/aktywnosc");
  const roch = page
    .locator(".activity-person")
    .filter({ has: page.getByRole("heading", { name: "Roch", exact: true }) });
  const kaja = page
    .locator(".activity-person")
    .filter({ has: page.getByRole("heading", { name: "Kaja", exact: true }) });
  await expect(roch).toContainText("123,45");
  await expect(kaja).toContainText("400,01");
  await expect(kaja).toContainText("10,01");
  await page.getByRole("button", { name: "Cały okres" }).click();
  await expect(
    page.getByRole("button", { name: "Cały okres" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(kaja).toContainText("400,01");
  await review("populated");
  await page.route("**/api/households/*/activity*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Nie udało się wczytać aktywności." }),
    }),
  );
  await page.reload();
  await expect(page.locator(".notice[role=alert]")).toContainText(
    "Nie udało się wczytać aktywności.",
  );
  await review("error");
  await page.unroute("**/api/households/*/activity*");
  await page.getByRole("button", { name: "Spróbuj ponownie" }).click();
  await expect(roch).toContainText("123,45");
  await page.goto("/transakcje");
  const expense = page
    .locator("details.transaction")
    .filter({ hasText: `Ręczny wydatek ${pass}` });
  await expect(expense).toContainText("Dodano przez: Roch");
  const income = page
    .locator("details.transaction")
    .filter({ hasText: `Wpływ Kai ${pass}` });
  await expect(income).toContainText("Dodano przez: Kaja");
  await expense.locator("summary").click();
  await expect(expense).toContainText("Autor wpisu");
  await review("transaction-authors");
  await page.goto(`/paragony/${receipt.id}`);
  await expect(page.locator(".record-author")).toContainText(
    "Dodano przez: Roch",
  );
  await review("receipt-author");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "Więcej", exact: true }).click();
  await page.getByRole("link", { name: /Aktywność domowników/ }).click();
  await expect(
    page.getByRole("heading", { name: "Aktywność domowników." }),
  ).toBeVisible();
  assert.deepEqual(errors, []);
  console.log(
    `Activity pass ${pass}: two real members, exact counts/amounts, uploader versus confirmer, authors, desktop/mobile navigation, empty/error/retry, monthly/all-time and 20 viewport/accessibility checks passed`,
  );
} finally {
  await browser.close();
}
