import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
const base = process.env.BASE_URL || "http://localhost:3000";
const browser = await chromium.launch();
const context = await browser.newContext({
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
  serviceWorkers: "block",
});
const page = await context.newPage();
const dir = "artifacts/ui-review/currency";
await fs.mkdir(dir, { recursive: true });
let state = "current";
let latestTotal = 0;
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
// Real account persistence; deterministic rate metadata for stable UI checks.
// Provider parsing, rounding, caching and failures have API integration tests.
await page.route("**/api/households/*/overview?*", async (route) => {
  const response = await route.fetch();
  if (!response.ok()) return route.fulfill({ response });
  const data = await response.json();
  for (const a of data.accounts) {
    a.balance_pln =
      a.currency === "PLN"
        ? a.balance
        : state === "unavailable"
          ? null
          : Number(
              (BigInt(a.balance) * 425n + (a.balance < 0 ? -50n : 50n)) / 100n,
            );
    a.exchange_rate =
      a.currency === "PLN" ? "1" : state === "unavailable" ? null : "4.25";
  }
  data.account_valuation = {
    total_pln: data.accounts.some((a) => a.balance_pln === null)
      ? null
      : data.accounts.reduce((sum, a) => sum + a.balance_pln, 0),
    rate_date: state === "unavailable" ? null : "2026-10-07",
    status: state,
  };
  latestTotal = data.account_valuation.total_pln;
  await route.fulfill({ response, json: data });
});
await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
await page.goto(base);
await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
await page.getByRole("heading", { name: "Cześć, Roch." }).waitFor();
for (let loop = 1; loop <= 2; loop++) {
  for (const [width, height] of [
    [390, 844],
    [430, 932],
    [768, 1024],
    [1440, 900],
  ]) {
    state = "current";
    await page.setViewportSize({ width, height });
    await page.goto(`${base}/konta`);
    await page
      .getByRole("button", { name: "Dodaj konto", exact: true })
      .click();
    const name = `Euro ${loop} ${width}`;
    await page.getByLabel("Nazwa konta").fill(name);
    await page.getByLabel("Waluta", { exact: true }).selectOption("EUR");
    await page.getByLabel("Saldo na start (EUR)").fill("100,00");
    await page.screenshot({
      path: `${dir}/loop${loop}-form-${width}.png`,
      fullPage: true,
    });
    await page
      .locator("form")
      .getByRole("button", { name: "Dodaj konto", exact: true })
      .click();
    const card = page
      .locator(".account-card")
      .filter({ has: page.getByRole("heading", { name, exact: true }) });
    await card.getByText("100,00 EUR", { exact: true }).waitFor();
    assert.match(await card.innerText(), /425,00 zł/);
    const rateBox = await card.locator("p").boundingBox();
    const cardBox = await card.boundingBox();
    assert.ok(
      rateBox.width > cardBox.width / 2,
      "Rate description must use the readable content column",
    );
    assert.ok(
      rateBox.height < 85,
      "Rate description must not wrap into a tall narrow strip",
    );
    await page.reload();
    await card.getByText("100,00 EUR", { exact: true }).waitFor();
    assert.match(
      await page.locator(".accounts-total").innerText(),
      /2026-10-07/,
    );
    const formattedTotal = `${new Intl.NumberFormat("pl-PL", { useGrouping: "always" }).format(Math.trunc(latestTotal / 100))},${String(latestTotal % 100).padStart(2, "0")} zł`;
    assert.equal(
      await page.locator(".accounts-total > strong").innerText(),
      formattedTotal,
    );
    assert.equal(
      await card.getByRole("link", { name: "Zrób przelew" }).count(),
      0,
    );
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    const axe = await new AxeBuilder({ page })
      .include("main")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    assert.deepEqual(
      axe.violations.map((v) => v.id),
      [],
    );
    await page.screenshot({
      path: `${dir}/loop${loop}-accounts-${width}.png`,
      fullPage: true,
    });
    for (const status of ["cached", "unavailable"]) {
      state = status;
      await page.reload();
      await page
        .getByText(
          status === "cached"
            ? "Nie udało się odświeżyć kursów"
            : "Brak aktualnej wyceny",
          { exact: false },
        )
        .waitFor();
      await page.screenshot({
        path: `${dir}/loop${loop}-${status}-${width}.png`,
        fullPage: true,
      });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
    }
    state = "current";
    await page.goto(`${base}/dodaj?type=income`);
    await page.getByRole("heading", { name: "Wspólny wpływ" }).waitFor();
    assert.equal(
      await page
        .locator('select[name="account"] option')
        .filter({ hasText: name })
        .count(),
      0,
    );
    for (const kind of ["expense", "transfer"]) {
      await page.goto(`${base}/dodaj?type=${kind}`);
      await page.locator('select[name="account"]').waitFor();
      assert.equal(
        await page.locator("select option").filter({ hasText: name }).count(),
        0,
      );
    }
    await page.goto(`${base}/cykliczne`);
    await page.getByRole("button", { name: "Nowy stały wydatek" }).click();
    await page.getByLabel("Konto", { exact: true }).waitFor();
    assert.equal(
      await page
        .locator('select[name="account"] option')
        .filter({ hasText: name })
        .count(),
      0,
    );
  }
  console.log(
    `Currency loop ${loop}: four viewports, persisted EUR balance, PLN value/date, outage states, accessibility and PLN account choices passed.`,
  );
}
assert.deepEqual(errors, []);
await browser.close();
