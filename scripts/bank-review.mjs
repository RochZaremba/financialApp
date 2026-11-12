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
  await expect(page.getByText(/Dopasowano płatność bankową:/)).toBeVisible();
  await expect(
    page.getByLabel("Czy to płatność już pobrana z banku?", { exact: true }),
  ).toHaveCount(0);
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
  // A genuine credit with one matching merchant/purchase is a refund, not income.
  const advancedRefund = await context.request.post(
    "/api/__qa/advance?phase_value=2",
  );
  assert.equal(advancedRefund.status(), 200);
  const refundStatus = await context.request
    .get(base + "/bank")
    .then((r) => r.json());
  const returned = refundStatus.entries.find((e) => e.amount === 13975);
  assert.equal(returned.transaction.kind, "refund");
  assert.equal(returned.transaction.refund_of_id, debit.transaction.id);
  assert.equal(returned.match_method, "refund");
  await page.reload();
  await page
    .getByRole("button", { name: "Pokaż historię", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: /^Zwrot/ })).toBeVisible();
  await review("automatic-refund");

  // Create a monthly buffer and check exact automatic cover, then a partial refund.
  const food = data.categories[0].id,
    householdCategory = data.categories[1].id;
  const bufferResponse = await context.request.post(base + "/categories", {
    data: { name: "Bufor", group: "Potrzeby" },
    headers: { "Idempotency-Key": `buffer-${pass}` },
  });
  assert.equal(bufferResponse.status(), 201);
  const buffer = await bufferResponse.json();
  const plan = await context.request.put(
    base + "/budget/" + today.slice(0, 7),
    {
      data: {
        planned_income: 100000,
        buffer_category_id: buffer.id,
        allocations: [
          { kind: "category", reference_id: food, amount: 10000 },
          { kind: "category", reference_id: householdCategory, amount: 20000 },
          { kind: "category", reference_id: buffer.id, amount: 0 },
        ],
      },
      headers: { "Idempotency-Key": `buffer-plan-${pass}` },
    },
  );
  assert.equal(plan.status(), 200);
  const five = refundStatus.entries.find((e) => e.amount === -500);
  assert.equal(
    (
      await context.request.put(
        base + "/transactions/" + five.transaction.id + "/allocations",
        { data: [{ category_id: householdCategory, amount: 500 }] },
      )
    ).status(),
    200,
  );
  async function expense(name, amount, category, key) {
    const result = await context.request.post(base + "/transactions", {
      data: {
        kind: "expense",
        amount,
        account_id: data.accounts[0].id,
        date: today,
        description: name,
        allocations: [{ category_id: category, amount }],
      },
      headers: { "Idempotency-Key": key },
    });
    assert.equal(result.status(), 201);
    return result.json();
  }
  const refundPurchase = await expense(
    "Zakup do częściowego zwrotu QA",
    15000,
    food,
    `partial-purchase-${pass}`,
  );
  await expense(
    "Druga przekroczona koperta QA",
    23000,
    householdCategory,
    `overrun-${pass}`,
  );
  await page.goto("/budzet");
  const reserve = page.locator(".budget-buffer");
  await expect(reserve.getByRole("heading", { name: /Bufor/ })).toBeVisible();
  await reserve.locator("summary").click();
  await expect(reserve.locator(".buffer-recipients li")).toHaveCount(2);
  const beforeBuffer = await context.request
    .get(base + "/overview?month=" + today.slice(0, 7))
    .then((r) => r.json());
  assert.equal(beforeBuffer.budget.buffer.covered, 8500);
  assert.equal(beforeBuffer.budget.buffer.remaining, 61500);
  await review("buffer-covered");

  await page.goto("/transakcje?item=" + refundPurchase.id);
  const purchaseRow = page
    .locator(".transaction")
    .filter({
      has: page.getByText("Zakup do częściowego zwrotu QA", { exact: true }),
    });
  await expect(purchaseRow).toBeVisible();
  await purchaseRow.getByText("Zarejestruj zwrot", { exact: true }).click();
  await purchaseRow
    .getByLabel("Kwota zwrotu (zł)", { exact: true })
    .fill("40,00");
  await review("manual-partial-refund");
  await purchaseRow
    .getByRole("button", { name: "Zapisz zwrot", exact: true })
    .click();
  await expect(purchaseRow.getByText(/Oddano już/)).toContainText("40,00");
  await page.goto("/budzet");
  await page.locator(".budget-buffer summary").click();
  const afterBuffer = await context.request
    .get(base + "/overview?month=" + today.slice(0, 7))
    .then((r) => r.json());
  assert.equal(afterBuffer.budget.buffer.covered, 4500);
  assert.equal(afterBuffer.budget.buffer.remaining, 65500);
  assert.equal(afterBuffer.budget.income, 2500);
  assert.equal(afterBuffer.budget.expenses, 34500);
  await review("buffer-after-refund");

  // A conscious balance-only correction leaves budget income and expenses intact.
  await page.goto("/bank");
  const bankAccount = page.locator(".bank-account").first();
  await bankAccount
    .getByRole("button", {
      name: "Wyrównaj saldo aplikacji do banku",
      exact: true,
    })
    .click();
  await expect(
    bankAccount.getByRole("heading", { name: "Potwierdź korektę salda" }),
  ).toBeVisible();
  await review("balance-alignment-preview");
  await bankAccount
    .getByRole("button", { name: "Potwierdź wyrównanie", exact: true })
    .click();
  await expect(
    bankAccount.getByText("Historia korekt salda (1)", { exact: true }),
  ).toBeVisible();
  await bankAccount.locator(".bank-align details summary").click();
  const aligned = await context.request
    .get(base + "/overview?month=" + today.slice(0, 7))
    .then((r) => r.json());
  assert.equal(
    aligned.accounts.find((a) => a.id === data.accounts[0].id).balance,
    100000,
  );
  assert.equal(aligned.budget.income, afterBuffer.budget.income);
  assert.equal(aligned.budget.expenses, afterBuffer.budget.expenses);
  await review("balance-aligned");
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
