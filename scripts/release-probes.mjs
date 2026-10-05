import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
const dir = `artifacts/ui-review/${process.argv[2] || "release-probes"}`;
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL: "http://localhost:3000",
  viewport: { width: 390, height: 844 },
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
});
const page = await context.newPage();
await page.goto("http://localhost:3000");
const name = `Release QA ${crypto.randomUUID()}`;
const send = async (path, method, data, key = crypto.randomUUID()) => {
  const r = await page.request.fetch("/api" + path, {
    method,
    data,
    headers: { "Idempotency-Key": key },
  });
  return { status: r.status(), data: await r.json() };
};
const findings = [];
let home;
try {
  const registration = await send("/auth/register", "POST", {
    email: `qa-${crypto.randomUUID()}@example.com`,
    password: "  release-test-password  ",
    name: "QA",
  });
  if (registration.status !== 201)
    throw Error("register " + registration.status);
  home = (await send("/households", "POST", { name })).data.id;
  const root = `/households/${home}`;
  await send(root + "/budget/2026-10", "PUT", {
    planned_income: 0,
    allocations: [],
  });
  await page.goto("http://localhost:3000/");
  await page.locator(".balance-card").waitFor();
  findings.push({
    case: "zero-income plan",
    claimsReady: await page
      .getByText("Plan gotowy", { exact: true })
      .isVisible(),
  });
  await page.screenshot({ path: dir + "/zero-plan.png", fullPage: true });
  await page.goto("http://localhost:3000/konta");
  await page.getByRole("button", { name: "Dodaj konto", exact: true }).click();
  await page.getByLabel("Nazwa konta", { exact: true }).fill("Saldo ujemne");
  await page.getByLabel("Saldo na start (zł)", { exact: true }).fill("-0,01");
  await page
    .locator("form")
    .getByRole("button", { name: "Dodaj konto", exact: true })
    .click();
  await page.waitForTimeout(300);
  findings.push({
    case: "negative account balance",
    error: await page.locator("main [role=alert]").allTextContents(),
  });
  await page.screenshot({
    path: dir + "/negative-balance.png",
    fullPage: true,
  });
  await page.goto("http://localhost:3000/dodaj");
  await page
    .locator("input[type=file]")
    .last()
    .setInputFiles("apps/web/public/icon-192.png");
  await page.getByLabel("Sklep", { exact: true }).waitFor();
  await page.getByLabel("Sklep", { exact: true }).fill("Tylko nazwa odczytana");
  findings.push({
    case: "partial OCR draft",
    inventedDate: await page
      .getByLabel("Data zakupu", { exact: true })
      .inputValue(),
    saveDisabled: await page
      .getByRole("button", { name: "Zapisz szkic", exact: true })
      .isDisabled(),
  });
  await page.screenshot({ path: dir + "/partial-draft.png", fullPage: true });
  const upload = async (key) => {
    const r = await page.request.post("/api" + root + "/receipts", {
      headers: { "Idempotency-Key": key },
      multipart: {
        file: {
          name: "lidl.png",
          mimeType: "image/png",
          buffer: await fs.readFile("fixtures/lidl.png"),
        },
      },
    });
    return r.json();
  };
  const key = crypto.randomUUID();
  const a = await upload(key),
    b = await upload(key);
  findings.push({ case: "retry receipt upload", sameReceipt: a.id === b.id });
  const draft = await send(root + `/receipts/${a.id}`, "PUT", {
    merchant: "Partial",
    date: null,
    total: null,
    items: [],
  });
  findings.push({ case: "API partial draft", status: draft.status });
  const data = (
    await page.request.get("/api" + root + "/overview?month=2026-10")
  ).json();
  const overview = await data;
  const category = overview.categories[0].id;
  const discount = await send(root + `/receipts/${a.id}`, "PUT", {
    merchant: "Rabat",
    date: "2026-10-01",
    total: 900,
    items: [
      { name: "Zakup", quantity: "1", amount: 1000, category_id: category },
      { name: "Rabat", quantity: "1", amount: -100, category_id: category },
    ],
  });
  findings.push({ case: "receipt discount", status: discount.status });
  const g1 = (
      await send(root + "/goals", "POST", { name: "Cel A", target: 100000 })
    ).data,
    g2 = (
      await send(root + "/goals", "POST", { name: "Cel B", target: 100000 })
    ).data;
  await send(root + "/budget/2026-10", "PUT", {
    planned_income: 35000,
    allocations: [
      { kind: "goal", reference_id: g1.id, amount: 10000 },
      { kind: "goal", reference_id: g2.id, amount: 25000 },
    ],
  });
  await page.goto("http://localhost:3000/dodaj?type=saving");
  await page.getByLabel("Na jaki cel?", { exact: true }).waitFor();
  const before = await page
    .getByLabel("Kwota (zł)", { exact: true })
    .inputValue();
  await page.getByLabel("Na jaki cel?", { exact: true }).selectOption(g2.id);
  findings.push({
    case: "changed payout target",
    before,
    after: await page.getByLabel("Kwota (zł)", { exact: true }).inputValue(),
    expected: "250,00",
  });
  await page.screenshot({ path: dir + "/changed-target.png", fullPage: true });
  await send(root + "/budget/2026-10", "PUT", {
    planned_income: 10000,
    allocations: [
      { kind: "goal", reference_id: g1.id, amount: 10000 },
      { kind: "goal", reference_id: g2.id, amount: 25000 },
    ],
  });
  await page.goto("http://localhost:3000/");
  await page.locator(".balance-card").waitFor();
  findings.push({
    case: "oversubscribed plan",
    warning: await page
      .getByText("Plan przekracza dochód", { exact: true })
      .isVisible(),
  });
  await page.screenshot({
    path: dir + "/oversubscribed-plan.png",
    fullPage: true,
  });
  const login = await send("/auth/login", "POST", {
    email: registration.data.email,
    password: "release-test-password",
  });
  findings.push({
    case: "password whitespace preserved",
    trimmedPasswordAccepted: login.status === 200,
  });
} finally {
  if (home) await send(`/households/${home}`, "DELETE", { name });
  await fs.writeFile(dir + "/results.json", JSON.stringify(findings, null, 2));
  console.log(JSON.stringify(findings));
  await browser.close();
}

if (process.argv.includes("--verify")) {
  const expected = {
    "oversubscribed plan": (f) => f.warning === true,
    "zero-income plan": (f) => f.claimsReady === false,
    "negative account balance": (f) => f.error.length === 0,
    "partial OCR draft": (f) =>
      f.inventedDate === "" && f.saveDisabled === false,
    "retry receipt upload": (f) => f.sameReceipt === true,
    "API partial draft": (f) => f.status === 200,
    "receipt discount": (f) => f.status === 200,
    "changed payout target": (f) => f.after === f.expected,
    "password whitespace preserved": (f) => f.trimmedPasswordAccepted === false,
  };
  if (findings.length !== 9 || findings.some((f) => !expected[f.case]?.(f)))
    process.exitCode = 1;
}
