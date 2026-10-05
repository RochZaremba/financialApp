import { chromium, expect } from "@playwright/test";
import http from "node:http";
import fs from "node:fs/promises";
const dir = "artifacts/ui-review/live-ai";
await fs.mkdir(dir, { recursive: true });
const proxy = http.createServer((req, res) => {
  const api = req.url.startsWith("/api/");
  const upstream = http.request(
    {
      host: "127.0.0.1",
      port: api ? 8001 : 3001,
      path: api ? req.url.slice(4) : req.url,
      method: req.method,
      headers: {
        ...req.headers,
        host: api ? "127.0.0.1:8001" : "127.0.0.1:3001",
      },
    },
    (response) => {
      res.writeHead(response.statusCode, response.headers);
      response.pipe(res);
    },
  );
  upstream.on("error", () => {
    res.writeHead(502);
    res.end("Starting QA servers");
  });
  req.pipe(upstream);
});
await new Promise((r) => proxy.listen(3010, "127.0.0.1", r));
const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL: "http://127.0.0.1:3010",
  viewport: { width: 390, height: 844 },
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
});
const page = await context.newPage();
await page.clock.setFixedTime(new Date("2026-10-05T12:00:00+02:00"));
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
let home;
const name = `Live AI QA ${crypto.randomUUID()}`;
const send = (url, method, data, key = crypto.randomUUID()) =>
  page.evaluate(
    async ({ url, method, data, key }) => {
      const r = await fetch("/api" + url, {
        method,
        headers: { "Content-Type": "application/json", "Idempotency-Key": key },
        body: JSON.stringify(data),
      });
      return { status: r.status, data: await r.json() };
    },
    { url, method, data, key },
  );
const read = (url) =>
  page.evaluate(async (url) => {
    const r = await fetch("/api" + url);
    return { status: r.status, data: await r.json() };
  }, url);
try {
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch("http://127.0.0.1:3010/api/health")).ok) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  await page.goto("/");
  expect(
    (
      await send("/auth/register", "POST", {
        name: "AI QA",
        email: `live-${crypto.randomUUID()}@example.com`,
        password: "private-live-test-password",
      })
    ).status,
  ).toBe(201);
  const created = await send("/households", "POST", { name });
  expect(created.status).toBe(201);
  home = created.data.id;
  const root = `/households/${home}`;
  const data = (await read(root + "/overview?month=2026-10")).data;
  const allocations = data.categories.map((c) => ({
    kind: "category",
    reference_id: c.id,
    amount:
      c.name === "Jedzenie"
        ? 6000
        : c.name === "Dom i zakupy"
          ? 12000
          : c.name === "Przyjemności"
            ? 2000
            : 0,
  }));
  expect(
    (
      await send(root + "/budget/2026-10", "PUT", {
        planned_income: 20000,
        allocations,
      })
    ).status,
  ).toBe(200);
  expect(
    (
      await send(root + "/transactions", "POST", {
        kind: "income",
        amount: 20000,
        date: "2026-10-05",
        description: "Wpływ do testu AI",
        account_id: data.accounts[0].id,
        allocations: [],
      })
    ).status,
  ).toBe(201);
  await page.goto("/dodaj");
  await page
    .locator("input[type=file]")
    .last()
    .setInputFiles("fixtures/lidl.png");
  await expect(
    page.getByRole("heading", { name: "Odczytujemy Wasz paragon…" }),
  ).toBeVisible();
  await page.screenshot({
    path: dir + "/processing-mobile.png",
    fullPage: true,
  });
  await page.getByLabel("Sklep", { exact: true }).waitFor({ timeout: 100000 });
  const receiptId = new URL(page.url()).pathname.split("/").at(-1);
  const receipt = (await read(root + "/receipts/" + receiptId)).data;
  const summary = {
    provider: receipt.provider,
    status: receipt.status,
    merchant: receipt.merchant,
    date: receipt.date,
    total: receipt.total,
    itemCount: receipt.items.length,
    itemSum: receipt.items.reduce((sum, i) => sum + (i.amount || 0), 0),
    errors,
  };
  await fs.writeFile(
    dir + "/extraction-result.json",
    JSON.stringify(summary, null, 2),
  );
  console.log(JSON.stringify(summary));
  expect(receipt.status).toBe("ready");
  expect(receipt.total).toBe(13975);
  expect(receipt.items.length).toBe(6);
  expect(summary.itemSum).toBe(receipt.total);
  await page.screenshot({ path: dir + "/review-mobile.png", fullPage: true });
  for (let i = 0; i < receipt.items.length; i++) {
    const row = page.locator(".receipt-item").nth(i);
    if (await row.getAttribute("class").then((c) => c.includes("uncertain"))) {
      const selected = await row
        .getByLabel("Kategoria", { exact: true })
        .inputValue();
      if (selected)
        await row
          .getByRole("button", { name: "Kategoria jest poprawna", exact: true })
          .click();
      else
        await row
          .getByRole("button", { name: "Dom i zakupy", exact: true })
          .click();
    }
  }
  await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
  await expect(
    page.getByRole("heading", { name: "Cześć, AI QA." }),
  ).toBeVisible();
  const budget = (await read(root + "/budget/2026-10")).data;
  expect(budget.expenses).toBe(13975);
  expect(budget.remaining).toBe(6025);
  const txs = (await read(root + "/transactions")).data.items;
  const tx = txs.find((t) => t.kind === "expense");
  expect(tx.allocations.reduce((sum, a) => sum + a.amount, 0)).toBe(13975);
  expect(tx.allocations.length).toBeGreaterThan(1);
  await page.screenshot({
    path: dir + "/confirmed-budget-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/transakcje");
  await page.locator("main h1").waitFor();
  await page.screenshot({ path: dir + "/history-desktop.png", fullPage: true });
  expect(errors).toEqual([]);
  await fs.writeFile(
    dir + "/final-result.json",
    JSON.stringify(
      {
        provider: receipt.provider,
        extractionReady: true,
        expense: 13975,
        remaining: 6025,
        categorySplits: tx.allocations.length,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    "Live AI upload → extraction → review → balanced split transaction → budget passed.",
  );
} finally {
  if (home)
    await send(`/households/${home}`, "DELETE", { name }).catch(() => {});
  await browser.close();
  await new Promise((r) => proxy.close(r));
}
