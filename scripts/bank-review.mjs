import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { generateKeyPairSync, randomUUID, randomBytes } from "node:crypto";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const dir = `artifacts/ui-review/bank-${pass}`;
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
});
const errors = [];
try {
  const context = await browser.newContext({
    baseURL: "http://localhost:3000",
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    serviceWorkers: "block",
  });
  await context.request.post("/api/__qa/reset");
  const password = process.env.ADMIN_REVIEW_USER_PASSWORD;
  assert.equal(
    (
      await context.request.post("/api/auth/register", {
        data: {
          name: "Roch QA",
          email: `bank-owner-${pass}@example.com`,
          password,
        },
      })
    ).status(),
    201,
  );
  assert.equal((await context.request.post("/api/__qa/admin")).status(), 200);
  const home = await context.request
    .post("/api/households", {
      data: { name: `Bank R&K QA ${pass}` },
      headers: { "Idempotency-Key": `bank-home-${pass}` },
    })
    .then((r) => r.json());
  const base = `/api/households/${home.id}`;
  const data = await context.request
    .get(base + "/overview?month=2026-10")
    .then((r) => r.json());
  const invitation = await context.request
    .post(base + "/invitations")
    .then((r) => r.json());
  const second = await browser.newContext({ baseURL: "http://localhost:3000" });
  await second.request.post("/api/auth/register", {
    data: {
      name: "Kaja QA",
      email: `bank-second-${pass}@example.com`,
      password,
    },
  });
  assert.equal(
    (
      await second.request.post("/api/households/join", {
        data: { token: invitation.token },
      })
    ).status(),
    200,
  );
  const page = await context.newPage();
  page.on("dialog", (dialog) => dialog.accept());
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/bank");
  await expect(
    page.getByRole("heading", { name: "Prywatne połączenie bankowe." }),
  ).toBeVisible();
  let checks = 0;
  async function review(state) {
    for (const [width, height] of [
      [390, 844],
      [430, 932],
      [768, 1024],
      [1440, 900],
    ]) {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => window.scrollTo(0, 0));
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
        `${state} overflow`,
      );
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      assert.deepEqual(
        result.violations.map((v) => ({
          id: v.id,
          targets: v.nodes.map((n) => n.target),
        })),
        [],
        `${state} ${width}`,
      );
      await page.screenshot({
        path: `${dir}/${state}-${width}.png`,
        fullPage: true,
      });
      checks++;
    }
  }
  await review("activation");
  const appId = randomUUID();
  const { privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" },
  });
  await page
    .getByLabel("Plik prywatnego klucza Enable Banking", { exact: true })
    .setInputFiles({
      name: `${appId}.pem.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(privateKey),
    });
  await expect(
    page.getByLabel("Identyfikator aplikacji Enable Banking", { exact: true }),
  ).toHaveValue(appId);
  await page
    .getByLabel("Potwierdź pełną nazwę tego domu", { exact: true })
    .fill(home.name);
  await page
    .getByLabel("Hasło administratora będącego właścicielem domu", {
      exact: true,
    })
    .fill(password);
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Aktywuj tylko dla tego domu", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Bank i zgodność salda." }),
  ).toBeVisible();
  await page.route("https://bank.qa.invalid/**", async (route) => {
    const state = new URL(route.request().url()).searchParams.get("state");
    await route.fulfill({
      status: 302,
      headers: {
        location: `http://localhost:3000/?code=qa-code&state=${encodeURIComponent(state)}`,
      },
    });
  });
  await page.getByRole("button", { name: "Połącz mBank", exact: true }).click();
  await expect(page.locator(".bank-account")).toHaveCount(2);
  await review("connected-unmapped");
  const bank = await context.request.get(base + "/bank").then((r) => r.json());
  for (let i = 0; i < bank.accounts.length; i++) {
    const account = bank.accounts[i];
    const card = page.locator(".bank-account").filter({
      has: page.getByRole("heading", {
        name: `Rachunek kończący się na ${account.last4} · PLN`,
      }),
    });
    await card
      .getByLabel("Konto aplikacji dla rachunku", { exact: true })
      .selectOption(data.accounts[i].id);
    await card
      .getByRole("button", { name: "Przypisz rachunek", exact: true })
      .click();
    await expect(card.getByText(/Konto aplikacji:/)).toBeVisible();
  }
  async function failure(mode) {
    assert.equal(
      (
        await context.request.post(`/api/__qa/sync-failure?mode=${mode}`)
      ).status(),
      200,
    );
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Połączenie mBank" }),
    ).toBeVisible();
  }
  await failure("unexpected");
  await page
    .getByRole("button", { name: "Synchronizuj teraz", exact: true })
    .click();
  await expect(
    page.locator(".bank-sync-failure").getByRole("alert"),
  ).toContainText("Synchronizacja nie powiodła się.");
  await expect(
    page.getByRole("button", { name: "Synchronizuj teraz", exact: true }),
  ).toBeDisabled();
  await page
    .getByText("Szczegóły błędu synchronizacji", { exact: true })
    .click();
  await expect(page.locator(".bank-diagnostic")).toContainText(
    "Pobieranie operacji",
  );
  await expect(page.locator(".bank-diagnostic")).toContainText(
    "AttributeError",
  );
  assert.ok(
    !(await page.locator("body").innerText()).includes(
      "PRIVATE_PROVIDER_RESPONSE_MUST_NOT_LEAK",
    ),
  );
  const waiting = await context.request
    .post(base + "/bank/sync")
    .then((r) => r.json());
  assert.equal(waiting.waiting, 1);
  assert.equal(waiting.failed, 0);
  assert.ok(waiting.message.includes("Nie rozpoczęto"));
  await review("sync-unexpected-error");
  await failure("http");
  await page
    .getByRole("button", { name: "Synchronizuj teraz", exact: true })
    .click();
  await expect(
    page.locator(".bank-sync-failure").getByRole("alert"),
  ).toContainText("Synchronizacja nie powiodła się.");
  await page
    .getByText("Szczegóły błędu synchronizacji", { exact: true })
    .click();
  await expect(page.locator(".bank-diagnostic")).toContainText("503");
  await expect(page.locator(".bank-diagnostic")).toContainText("ASPSP_ERROR");
  await review("sync-http-error");
  await failure("legacy");
  await page
    .getByText("Szczegóły błędu synchronizacji", { exact: true })
    .click();
  await expect(page.locator(".bank-diagnostic")).toContainText(
    "Ta starsza próba nie ma zapisanych szczegółów.",
  );
  await expect(
    page.getByRole("button", { name: "Synchronizuj teraz", exact: true }),
  ).toBeDisabled();
  await review("sync-legacy-error");
  await failure("none");
  await page
    .getByRole("button", { name: "Synchronizuj teraz", exact: true })
    .click();
  await expect(page.locator(".bank-entry")).toHaveCount(2);
  await expect(page.locator(".bank-sync-failure")).toHaveCount(0);
  await expect(page.locator(".bank-status").getByRole("status")).toContainText(
    "Synchronizacja zakończona.",
  );
  await expect(
    page.getByRole("button", { name: "Synchronizuj teraz", exact: true }),
  ).toBeDisabled();
  await review("unreviewed");
  const initial = await context.request
    .get(base + "/bank")
    .then((r) => r.json());
  assert.ok(initial.entries.every((e) => !e.transaction));
  const firstExpense = page
    .locator(".bank-entry")
    .filter({ has: page.getByRole("heading", { name: /^Wydatek/ }) });
  await firstExpense
    .getByText("Opisz lub dopasuj operację", { exact: true })
    .click();
  await firstExpense
    .getByLabel("Opis operacji bankowej", { exact: true })
    .fill("Zakupy QA");
  await firstExpense
    .getByRole("button", { name: "Potwierdź operację", exact: true })
    .click();
  await expect(page.locator(".bank-entry")).toHaveCount(1);
  const state = await context.request.get(base + "/bank").then((r) => r.json());
  const debit = state.entries.find((e) => e.amount < 0);
  assert.ok(debit.transaction);
  assert.equal(debit.transaction.amount, 13975);
  assert.equal(state.entries.find((e) => e.amount > 0).transaction, null);
  assert.equal(
    (await second.request.get(base + "/bank").then((r) => r.json())).enabled,
    true,
  );
  assert.equal(
    (await second.request.post(base + "/bank/connect")).status(),
    403,
  );
  const upload = await context.request
    .post(base + "/receipts", {
      multipart: {
        file: {
          name: "lidl.png",
          mimeType: "image/png",
          buffer: await fs.readFile("fixtures/lidl.png"),
        },
      },
      headers: { "Idempotency-Key": `bank-receipt-${pass}` },
    })
    .then((r) => r.json());
  const receipt = await context.request
    .get(base + "/receipts/" + upload.id)
    .then((r) => r.json());
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Warsaw",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  assert.equal(
    (
      await context.request.put(base + "/receipts/" + receipt.id, {
        data: {
          merchant: "Lidl QA",
          date: today,
          total: 13975,
          items: receipt.items.map((i) => ({
            name: i.name,
            quantity: i.quantity,
            amount: i.amount,
            category_id: i.category_id || data.categories[0].id,
            confidence: 100,
            reviewed: true,
          })),
        },
      })
    ).status(),
    200,
  );
  await page.goto("/paragony/" + receipt.id);
  await expect(
    page.getByLabel("Czy to płatność już pobrana z banku?", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Czy to płatność już pobrana z banku?", { exact: true })
    .selectOption(debit.transaction.id);
  await review("receipt-match");
  await page
    .getByRole("button", { name: "Zatwierdź paragon", exact: true })
    .click();
  await expect(page).toHaveURL("http://localhost:3000/");
  let history = await context.request
    .get(base + "/transactions?month=" + today.slice(0, 7))
    .then((r) => r.json());
  assert.equal(history.items.length, 1);
  assert.equal(history.items[0].id, debit.transaction.id);
  await page.goto("/bank");
  await expect(page.locator(".bank-entry")).toHaveCount(1);
  const income = page.locator(".bank-entry").first();
  await income.getByText("Opisz lub dopasuj operację", { exact: true }).click();
  await income
    .getByLabel("Opis operacji bankowej", { exact: true })
    .fill("Wynagrodzenie QA");
  await income
    .getByRole("button", { name: "Potwierdź operację", exact: true })
    .click();
  await expect(
    page.getByText("Nie ma nowych operacji do uzupełnienia.", { exact: true }),
  ).toBeVisible();
  await review("reviewed");
  const keys = {
    auth: randomBytes(16).toString("base64url"),
    p256dh: randomBytes(65).toString("base64url"),
  };
  assert.equal(
    (
      await context.request.post(base + "/bank/subscriptions", {
        data: {
          endpoint: "https://fcm.googleapis.com/fcm/send/qa-device",
          keys,
        },
      })
    ).status(),
    200,
  );
  const advanced = await context.request
    .post("/api/__qa/advance")
    .then((r) => r.json());
  assert.ok(advanced.delivered > 0);
  await page.reload();
  await expect(page.locator(".bank-entry")).toHaveCount(3);
  const updated = await context.request
    .get(base + "/bank")
    .then((r) => r.json());
  const transfers = updated.entries.filter((e) => Math.abs(e.amount) === 2000);
  assert.equal(transfers.length, 2);
  assert.ok(transfers.every((e) => !e.transaction));
  await review("new-and-own-transfer");
  const own = await context.request
    .post("/api/households", {
      data: { name: "Other QA home" },
      headers: { "Idempotency-Key": `other-bank-${pass}` },
    })
    .then((r) => r.json());
  assert.deepEqual(
    await context.request
      .get(`/api/households/${own.id}/bank`)
      .then((r) => r.json()),
    { enabled: false },
  );
  assert.equal(
    (
      await context.request.post(`/api/households/${own.id}/bank/connect`)
    ).status(),
    404,
  );
  assert.deepEqual(errors, []);
  await fs.writeFile(
    `${dir}/results.json`,
    JSON.stringify(
      {
        checks,
        errors,
        syntheticProvider: true,
        twoMembers: true,
        noDuplicate: true,
        otherHouseholdDenied: true,
        pushOutbox: true,
      },
      null,
      2,
    ),
  );
  console.log(
    `Bank loop ${pass}: ${checks} viewport/axe checks, exact-scope activation, OAuth callback, two accounts, two members, receipt matching and outbox passed`,
  );
} finally {
  await browser.close();
}
