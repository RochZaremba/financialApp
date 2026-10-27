import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const dir = `artifacts/ui-review/meter-context-${pass}`;
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
  const result = await context.request.post("/api/auth/register", {
    data: {
      name: "Odczyty QA",
      email: `meter-context-${pass}@example.com`,
      password: process.env.ADMIN_REVIEW_USER_PASSWORD,
    },
  });
  assert.equal(result.status(), 201);
  const home = await context.request
    .post("/api/households", {
      data: { name: "Dom pomiarów" },
      headers: { "Idempotency-Key": `context-home-${pass}` },
    })
    .then((r) => r.json());
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/liczniki");
  await page.getByLabel("Nazwa licznika", { exact: true }).fill("Prąd");
  await page
    .getByRole("button", { name: "Zapisz licznik", exact: true })
    .click();
  await expect(page.getByLabel("Godzina pomiaru", { exact: true })).toHaveValue(
    /^\d\d:\d\d$/,
  );
  const base = `/api/households/${home.id}/meters`;
  const meter = (await context.request.get(base).then((r) => r.json()))[0];
  const detail = () =>
    context.request.get(`${base}/${meter.id}`).then((r) => r.json());
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
      );
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      assert.deepEqual(
        axe.violations.map((v) => ({
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
  await review("empty");
  await page.getByLabel("Data odczytu", { exact: true }).fill("2026-01-01");
  await page.getByLabel("Godzina pomiaru", { exact: true }).fill("20:15");
  await page.getByLabel("Stan licznika (kWh)", { exact: true }).fill("100");
  await page
    .getByRole("button", { name: "Zapisz odczyt", exact: true })
    .click();
  await expect(page.locator(".meter-history article")).toHaveCount(1);
  await page.getByLabel("Data odczytu", { exact: true }).fill("2026-01-02");
  await page.getByLabel("Godzina pomiaru", { exact: true }).fill("14:15");
  await page.getByLabel("Stan licznika (kWh)", { exact: true }).fill("101");
  await page
    .getByRole("button", { name: "Gotowanie: tak", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Piekarnik: nie", exact: true })
    .click();
  await page.getByRole("button", { name: "Pralka: tak", exact: true }).click();
  await page.getByRole("button", { name: "Pralka: tak", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Pralka: tak", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page
    .getByLabel("Krótka notatka (opcjonalnie)", { exact: true })
    .fill("Goście, gotowaliśmy obiad. Bez pieczenia.");
  await review("context-form");
  await page
    .getByRole("button", { name: "Zapisz odczyt", exact: true })
    .click();
  await expect(page.locator(".meter-history article")).toHaveCount(2);
  let row = (await detail()).readings.at(-1);
  assert.equal(row.elapsed_seconds, 64800);
  assert.equal(row.average, 1333);
  assert.deepEqual(row.activities, { cooking: true, oven: false });
  await expect(
    page.getByLabel("Krótka notatka (opcjonalnie)", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Gotowanie: tak", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page
    .getByRole("button", { name: "Średnio dziennie", exact: true })
    .click();
  await expect(page.locator(".meter-chart-detail")).toContainText(
    "1,333 kWh/dzień",
  );
  await expect(page.locator(".meter-chart-detail")).toContainText("18 godz.");
  await expect(page.locator(".meter-chart-detail")).toContainText(
    "Gotowanie: tak · Piekarnik: nie",
  );
  await review("history-chart");
  await page
    .getByRole("button", { name: "Popraw odczyt 2026-01-02", exact: true })
    .click();
  await expect(page.getByLabel("Godzina pomiaru", { exact: true })).toHaveValue(
    "14:15",
  );
  await expect(
    page.getByRole("button", { name: "Piekarnik: nie", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Godzina pomiaru", { exact: true }).fill("15:15");
  await page
    .getByLabel("Krótka notatka (opcjonalnie)", { exact: true })
    .fill("Poprawiona godzina. Gotowanie obiadu.");
  await page
    .getByRole("button", { name: "Piekarnik: tak", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Zapisz odczyt", exact: true })
    .click();
  await expect(page.locator(".meter-history article").first()).toContainText(
    "15:15",
  );
  row = (await detail()).readings.at(-1);
  assert.equal(row.elapsed_seconds, 68400);
  assert.equal(row.average, 1263);
  assert.equal(row.activities.oven, true);
  await review("corrected");
  await page.reload();
  await expect(page.locator(".meter-history article").first()).toContainText(
    "Poprawiona godzina",
  );
  // A legacy-style API/MCP client still creates a reading without a claimed measurement clock.
  assert.equal(
    (
      await context.request.post(`${base}/${meter.id}/readings`, {
        data: { date: "2026-01-03", value: 102000 },
        headers: { "Idempotency-Key": `legacy-context-${pass}` },
      })
    ).status(),
    201,
  );
  await page.reload();
  await expect(page.locator(".meter-history article").first()).toContainText(
    "godzina nieznana",
  );
  await expect(page.locator(".meter-chart-detail")).toContainText("wg dat");
  await review("legacy-unknown");
  assert.deepEqual(errors, []);
  await fs.writeFile(
    `${dir}/results.json`,
    JSON.stringify(
      { checks, errors, exactAverage: true, contextPreserved: true },
      null,
      2,
    ),
  );
  console.log(
    `Meter context loop ${pass}: ${checks} viewport/axe checks passed`,
  );
} finally {
  await browser.close();
}
