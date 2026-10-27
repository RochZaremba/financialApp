import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const directory = `artifacts/ui-review/meters-${pass}`;
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
  const context = await browser.newContext(options);
  const second = await browser.newContext(options);
  const password = process.env.ADMIN_REVIEW_USER_PASSWORD;
  assert.equal(
    (
      await context.request.post("/api/auth/register", {
        data: {
          name: "Odczyty",
          email: `meters-${pass}@example.com`,
          password,
        },
      })
    ).status(),
    201,
  );
  const home = await context.request
    .post("/api/households", {
      data: { name: `Dom odczytów ${pass}` },
      headers: { "Idempotency-Key": `meters-household-${pass}` },
    })
    .then((r) => r.json());
  const base = `/api/households/${home.id}/meters`;
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("link", { name: "Liczniki", exact: true }).click();
  await page.getByLabel("Nazwa licznika", { exact: true }).fill(`Prąd ${pass}`);
  await page
    .getByRole("button", { name: "Zapisz licznik", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Dodaj kolejny odczyt" }),
  ).toBeVisible();
  const meters = await context.request.get(base).then((r) => r.json());
  assert.equal(meters.length, 1);
  const meter = meters[0];
  const path = `${base}/${meter.id}`;
  const detail = () => context.request.get(path).then((r) => r.json());
  const today = (await detail()).today;
  function day(offset) {
    const d = new Date(today + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + offset);
    return d.toISOString().slice(0, 10);
  }
  const viewports = [
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 },
  ];
  async function review(state) {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => window.scrollTo(0, 0));
      await expect(page.locator("h1")).toBeVisible();
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
        `${state}: overflow`,
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
  // Keep the original date-only flow deterministic; exact clocks/context have a separate review.
  async function saveWithoutClock() {
    await page.getByLabel("Godzina pomiaru", { exact: true }).fill("");
    await page
      .getByRole("button", { name: "Zapisz odczyt", exact: true })
      .click();
  }
  await review("empty");
  await page.getByLabel("Data odczytu", { exact: true }).fill(day(-60));
  await page.getByLabel("Stan licznika (kWh)", { exact: true }).fill("12000");
  await saveWithoutClock();
  await expect(page.locator(".meter-history article")).toHaveCount(1);
  assert.equal((await detail()).readings[0].consumption, null);
  await page.getByLabel("Data odczytu", { exact: true }).fill(day(-30));
  await page.getByLabel("Stan licznika (kWh)", { exact: true }).fill("12200");
  await page
    .getByLabel("Zdjęcie licznika", { exact: true })
    .setInputFiles("fixtures/meter.png");
  await page
    .getByRole("button", { name: "Zapisz zdjęcie", exact: true })
    .click();
  await expect(page.locator(".meter-proposal")).toContainText(/12\s345,678/);
  await expect(
    page.getByLabel("Stan licznika (kWh)", { exact: true }),
  ).toHaveValue("12200");
  assert.equal((await detail()).readings.length, 1);
  await review("proposal");
  await page
    .getByRole("button", { name: "Użyj tego odczytu", exact: true })
    .click();
  await expect(
    page.getByLabel("Stan licznika (kWh)", { exact: true }),
  ).toHaveValue("12345,678");
  await saveWithoutClock();
  await expect(page.locator(".meter-history article")).toHaveCount(2);
  assert.equal((await detail()).readings[1].consumption, 345678);
  await page.getByLabel("Data odczytu", { exact: true }).fill(today);
  await page
    .getByLabel("Stan licznika (kWh)", { exact: true })
    .fill("12345,678");
  await saveWithoutClock();
  await expect(page.locator(".meter-history article")).toHaveCount(3);
  assert.equal((await detail()).readings[2].consumption, 0);
  await page
    .getByRole("button", { name: "Średnio dziennie", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Średnio dziennie", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.locator(".meter-bars button").first().click();
  await expect(page.locator(".meter-chart-detail")).toContainText("11,523");
  await page.locator(".meter-bars button").last().click();
  await expect(page.locator(".meter-chart-detail")).toContainText(
    "0 kWh/dzień",
  );
  await page.getByLabel("Odstęp odczytów w dniach", { exact: true }).fill("7");
  await page.getByRole("button", { name: "Zapisz plan", exact: true }).click();
  await expect(
    page.getByLabel("Odstęp odczytów w dniach", { exact: true }),
  ).toHaveValue("7");
  await page
    .getByRole("button", { name: "Między odczytami", exact: true })
    .click();
  await review("usage");
  await page.getByLabel("Data odczytu", { exact: true }).fill(day(-15));
  await page
    .getByLabel("Stan licznika (kWh)", { exact: true })
    .fill("12345,678");
  await page
    .getByLabel("Zdjęcie licznika", { exact: true })
    .setInputFiles("fixtures/lidl.png");
  await page
    .getByRole("button", { name: "Zapisz zdjęcie", exact: true })
    .click();
  await expect(page.locator(".meter-proposal")).toContainText("AI_UNAVAILABLE");
  await expect(
    page.getByLabel("Stan licznika (kWh)", { exact: true }),
  ).toHaveValue("12345,678");
  await review("manual-fallback");
  await saveWithoutClock();
  await expect(page.locator(".meter-history article")).toHaveCount(4);
  await page
    .getByRole("button", { name: `Popraw odczyt ${day(-60)}`, exact: true })
    .click();
  await page.getByLabel("Stan licznika (kWh)", { exact: true }).fill("12001");
  await saveWithoutClock();
  await expect(
    page.getByRole("heading", { name: "Dodaj kolejny odczyt" }),
  ).toBeVisible();
  assert.equal((await detail()).readings[1].consumption, 344678);
  await page.getByLabel("Data odczytu", { exact: true }).fill(day(-1));
  await page.getByLabel("Stan licznika (kWh)", { exact: true }).fill("1");
  await saveWithoutClock();
  await expect(page.locator(".notice[role=alert]")).toContainText(
    "Stan nie pasuje",
  );
  await page
    .getByLabel("Stan licznika (kWh)", { exact: true })
    .fill("12345,678");
  await saveWithoutClock();
  await expect(page.locator(".meter-history article")).toHaveCount(5);
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: `Usuń odczyt ${day(-1)}`, exact: true })
    .click();
  await expect(page.locator(".meter-history article")).toHaveCount(4);
  const final = await detail();
  assert.equal(
    (
      await context.request
        .get(`/api/households/${home.id}/transactions`)
        .then((r) => r.json())
    ).items.length,
    0,
  );
  await second.request.post("/api/auth/register", {
    data: {
      name: "Druga osoba",
      email: `meters-other-${pass}@example.com`,
      password,
    },
  });
  assert.equal((await second.request.get(path)).status(), 403);
  const invitation = await context.request
    .post(`/api/households/${home.id}/invitations`)
    .then((r) => r.json());
  await second.request.post("/api/households/join", {
    data: { token: invitation.token },
  });
  assert.equal((await second.request.get(path)).status(), 200);
  assert.equal(
    (await second.request.get(`${path}/photos/${final.photos[0].id}`)).status(),
    200,
  );
  await page
    .getByRole("button", { name: "Dodaj licznik", exact: true })
    .click();
  await page.getByLabel("Nazwa licznika", { exact: true }).fill(`Woda ${pass}`);
  await page.getByLabel("Jednostka", { exact: true }).selectOption("m3");
  await page
    .getByRole("button", { name: "Zapisz licznik", exact: true })
    .click();
  await expect(
    page.getByLabel("Stan licznika (m³)", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Wybierz licznik", { exact: true })
    .selectOption(meter.id);
  await expect(page.locator(".meter-history article")).toHaveCount(4);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "Więcej", exact: true }).click();
  await page.getByRole("link", { name: /Liczniki i zużycie/ }).click();
  await expect(
    page.getByRole("heading", { name: "Wasze liczniki." }),
  ).toBeVisible();
  assert.deepEqual(errors, []);
  console.log(
    `Meters pass ${pass}: private photo proposal without overwrite, explicit confirmation, irregular and zero consumption, interactive charts, manual fallback, correction/deletion, reminders, two-member access, multiple units, no financial entries and 16 viewport/accessibility checks passed`,
  );
} finally {
  await browser.close();
}
