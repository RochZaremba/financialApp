import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
const base =
  process.env.PRODUCTION_REVIEW_URL || "https://budget.localhost:8443";
const dir = "artifacts/ui-review/production-release";
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch({
  args: ["--host-resolver-rules=MAP budget.localhost 127.0.0.1"],
});
const context = await browser.newContext({
  baseURL: base,
  ignoreHTTPSErrors: true,
  viewport: { width: 390, height: 844 },
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
});
const page = await context.newPage();
await page.clock.setFixedTime(new Date("2026-10-05T12:00:00+02:00"));
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const unique = crypto.randomUUID(),
  email = `production-${unique}@example.com`,
  password = "  exact-production-password  ",
  name = `Release ${unique}`;
let home, receiptUrl, secondContext;
const screens = [];
const read = (path) =>
  page.evaluate(async (p) => {
    const r = await fetch(p);
    return { status: r.status, data: await r.json() };
  }, path);
const send = (path, method, data) =>
  page.evaluate(
    async ({ path, method, data }) => {
      const r = await fetch(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      return { status: r.status, data: await r.json() };
    },
    { path, method, data },
  );
async function go(path) {
  if (page.url() !== "about:blank") await page.waitForLoadState("networkidle");
  await page.goto(path);
  await page.locator("main h1").waitFor();
}
async function homeReady() {
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch QA." }),
  ).toBeVisible();
  await expect(page.locator(".app-shell")).toBeVisible();
}
try {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Zobacz wersję demo" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Pierwszy raz tutaj? Utwórz konto" })
    .click();
  await page.getByLabel("Jak masz na imię?").fill("Roch QA");
  await page.getByLabel("Adres e-mail", { exact: true }).fill(email);
  await page.getByLabel("Hasło", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Utwórz konto", exact: true }).click();
  await page.getByLabel("Nazwa gospodarstwa").fill(name);
  await page.getByRole("button", { name: "Utwórz nasz dom" }).click();
  await homeReady();
  const cookie = (await context.cookies()).find(
    (c) => c.name === "dom_session",
  );
  expect(cookie?.secure).toBe(true);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  home = (await read("/api/auth/me")).data.households[0].id;
  const root = `/api/households/${home}`;
  await go("/budzet");
  await page.getByLabel("Planowany dochód (zł)").fill("100");
  await page.getByLabel("Jedzenie — plan (zł)").fill("60");
  await page.getByLabel("Roch QA — plan (zł)").fill("40");
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(
    page.getByText("Wszystko ma swoje miejsce", { exact: true }),
  ).toBeVisible();
  await go("/dodaj?type=income");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("100");
  await page.getByLabel("Skąd te pieniądze?").fill("Wspólny wpływ");
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await homeReady();
  await go("/dodaj?type=pocket");
  await expect(page.getByLabel("Kwota (zł)", { exact: true })).toHaveValue(
    "40,00",
  );
  await page.getByLabel("Nazwa lub krótki opis").fill("Kieszonkowe");
  await page
    .getByRole("button", { name: "Wypłać kieszonkowe", exact: true })
    .click();
  await homeReady();
  await go("/dodaj?type=expense");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("1,01");
  await page.getByLabel("Nazwa lub krótki opis").fill("Dokładnie co do grosza");
  await page
    .getByLabel("Kategoria", { exact: true })
    .selectOption({ label: "Jedzenie" });
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await homeReady();
  await go("/dodaj");
  await page
    .locator("input[type=file]")
    .last()
    .setInputFiles("fixtures/lidl.png");
  await expect(page.getByLabel("Data zakupu", { exact: true })).toHaveValue("");
  receiptUrl = page.url();
  await page.getByLabel("Sklep", { exact: true }).fill("Lidl");
  await page.getByRole("button", { name: "Zapisz szkic", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Szkic paragonu zapisany",
  );
  await page.reload();
  await expect(page.getByLabel("Sklep", { exact: true })).toHaveValue("Lidl");
  await page.getByLabel("Data zakupu", { exact: true }).fill("2026-10-05");
  await page.getByLabel("Suma paragonu (zł)", { exact: true }).fill("19,99");
  for (const [index, title, amount] of [
    [0, "Zakup", "20"],
    [1, "Rabat", "-0,01"],
  ]) {
    await page
      .getByRole("button", { name: "Dodaj pozycję", exact: true })
      .click();
    const row = page.locator(".receipt-item").nth(index);
    await row.getByLabel(`Pozycja ${index + 1}`, { exact: true }).fill(title);
    await row.getByLabel("Kwota pozycji (zł)", { exact: true }).fill(amount);
    await row.getByRole("button", { name: "Jedzenie", exact: true }).click();
  }
  await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
  await homeReady();
  await go("/dodaj");
  await page
    .locator("input[type=file]")
    .last()
    .setInputFiles("apps/web/public/icon-192.png");
  await page.getByLabel("Sklep", { exact: true }).fill("LIDL");
  await page.getByLabel("Data zakupu", { exact: true }).fill("2026-10-05");
  await page.getByLabel("Suma paragonu (zł)", { exact: true }).fill("19,99");
  await page
    .getByRole("button", { name: "Dodaj pozycję", exact: true })
    .click();
  await page
    .getByLabel("Pozycja 1", { exact: true })
    .fill("Drugi odczyt tego samego zakupu");
  await page.getByLabel("Kwota pozycji (zł)", { exact: true }).fill("19,99");
  await page
    .locator(".receipt-item")
    .getByRole("button", { name: "Jedzenie", exact: true })
    .click();
  await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
  await expect(page.locator("main [role=alert]")).toContainText(
    "Ten paragon może już być zapisany",
  );
  await expect(
    page.getByRole("checkbox", {
      name: "Jeśli ten paragon już istnieje, potwierdzam, że to osobny zakup.",
    }),
  ).toBeVisible();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: `${dir}/duplicate-${width}.png`,
      fullPage: true,
    });
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(axe.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    screens.push({
      route: "receipt-duplicate",
      width,
      overflow: false,
      violations: 0,
    });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect((await read(root + "/budget/2026-10")).data.expenses).toBe(2100);
  await page
    .getByLabel("Sklep", { exact: true })
    .fill("Inny sklep po korekcie OCR");
  await page.getByRole("button", { name: "Zapisz szkic", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Wszystko wygląda dobrze." }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", {
      name: "Jeśli ten paragon już istnieje, potwierdzam, że to osobny zakup.",
    }),
  ).toHaveCount(0);
  expect((await read(root + "/budget/2026-10")).data.expenses).toBe(2100);
  await page.getByLabel("Sklep", { exact: true }).fill("LIDL");
  await page
    .getByRole("button", { name: "Zatwierdź paragon", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sprawdź możliwy duplikat." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Usuń ten szkic", exact: true })
    .click();
  await page.getByRole("button", { name: "Usuń szkic", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Wszystko na bieżąco." }),
  ).toBeVisible();
  await go("/cele");
  await page.getByRole("button", { name: "Nowy cel" }).click();
  await page.getByLabel("Nazwa celu").fill("Wyjazd");
  await page.getByLabel("Chcemy zebrać (zł)").fill("50");
  await page.getByLabel("Miesięczny plan (zł)").fill("10");
  await page.getByRole("button", { name: "Zapisz cel" }).click();
  await expect(
    page.getByRole("heading", { name: "Wyjazd", exact: true }),
  ).toBeVisible();
  await go("/budzet");
  await page.getByRole("button", { name: "Edytuj plan" }).click();
  await page.getByLabel("Jedzenie — plan (zł)").fill("50");
  await page.getByLabel("Wyjazd — plan (zł)").fill("10");
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(
    page.getByText("Wszystko ma swoje miejsce", { exact: true }),
  ).toBeVisible();
  await go("/cele");
  await page.getByRole("link", { name: "Odłóż na cel", exact: true }).click();
  await expect(page.getByLabel("Kwota (zł)", { exact: true })).toHaveValue(
    "10,00",
  );
  await page.getByLabel("Nazwa lub krótki opis").fill("Odkładamy");
  await page.getByRole("button", { name: "Odłóż na cel", exact: true }).click();
  await homeReady();
  await go("/cykliczne");
  await page.getByRole("button", { name: "Nowy stały wydatek" }).click();
  await page.getByLabel("Nazwa płatności").fill("Stała płatność");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("2");
  await page
    .getByLabel("Kategoria", { exact: true })
    .selectOption({ label: "Jedzenie" });
  await page.getByRole("button", { name: "Zapisz płatność" }).click();
  await page.getByRole("button", { name: "Opłacone", exact: true }).click();
  await expect(page.locator(".recurring-actions .pill")).toContainText(
    "Opłacone",
  );
  const data = (await read(root + "/overview?month=2026-10")).data;
  expect(data.budget.expenses).toBe(2300);
  expect(data.budget.pocket).toBe(4000);
  expect(data.budget.savings).toBe(1000);
  expect(data.budget.remaining).toBe(2700);
  expect(data.accounts.reduce((sum, a) => sum + a.balance, 0)).toBe(3700);
  expect(data.tasks).toHaveLength(0);
  await go("/ustawienia");
  await page
    .getByRole("button", { name: "Zaproś do wspólnego budżetu" })
    .click();
  const invite = await page
    .getByLabel("Link zaproszenia (ważny 7 dni)")
    .inputValue();
  secondContext = await browser.newContext({
    baseURL: base,
    ignoreHTTPSErrors: true,
    viewport: { width: 390, height: 844 },
    locale: "pl-PL",
  });
  const second = await secondContext.newPage();
  await second.goto(invite);
  await second.getByLabel("Jak masz na imię?").fill("Kaja QA");
  await second
    .getByLabel("Adres e-mail", { exact: true })
    .fill(`kaja-${unique}@example.com`);
  await second.getByLabel("Hasło", { exact: true }).fill(password);
  await second
    .getByRole("button", { name: "Utwórz konto", exact: true })
    .click();
  await second.getByRole("button", { name: "Dołącz do domu" }).click();
  await expect(second.locator(".app-shell")).toBeVisible();
  await expect(
    second.getByRole("heading", { name: "Cześć, Kaja QA." }),
  ).toBeVisible();
  await second.goto(base + "/ustawienia");
  await expect(
    second.getByRole("button", { name: "Usuń gospodarstwo", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Kaja QA", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Pobierz dane" }).click();
  const download = await downloadPromise;
  await download.saveAs(dir + "/household-export.json");
  const exported = JSON.parse(
    await fs.readFile(dir + "/household-export.json", "utf8"),
  );
  expect(exported.money_unit).toBe("grosz");
  const routes = [
    "/",
    "/budzet",
    "/dodaj",
    "/dodaj?type=expense",
    "/transakcje",
    "/cele",
    "/analiza",
    "/inbox",
    "/konta",
    "/cykliczne",
    "/ustawienia",
    "/wiecej",
    new URL(receiptUrl).pathname,
  ];
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    for (const route of routes) {
      await go(route);
      await page.evaluate(() => document.fonts.ready);
      const filename =
        route === "/"
          ? "home"
          : route.startsWith("/paragony/")
            ? "receipt"
            : route.slice(1).replaceAll(/[/?=]/g, "-");
      await page.screenshot({
        path: `${dir}/${filename}-${width}.png`,
        fullPage: true,
      });
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      );
      expect(axe.violations).toEqual([]);
      expect(overflow).toBe(false);
      screens.push({
        route,
        width,
        overflow,
        violations: axe.violations.length,
      });
    }
  }
  await go("/ustawienia");
  await page.getByRole("button", { name: "Wyloguj się", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Witaj z powrotem." }),
  ).toBeVisible();
  expect((await read(root + "/export")).status).toBe(401);
  await page.getByLabel("Adres e-mail", { exact: true }).fill(email);
  await page.getByLabel("Hasło", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Zaloguj się", exact: true }).click();
  await homeReady();
  await go("/ustawienia");
  await page
    .getByRole("button", { name: "Usuń gospodarstwo", exact: true })
    .click();
  await page.getByLabel("Wpisz nazwę: " + name, { exact: true }).fill(name);
  await page.getByRole("button", { name: "Usuń bezpowrotnie" }).click();
  await expect(page.getByLabel("Nazwa gospodarstwa")).toBeVisible();
  expect((await read(root + "/export")).status).toBe(403);
  home = null;
  expect(errors).toEqual([]);
  await fs.writeFile(
    dir + "/results.json",
    JSON.stringify(
      {
        secureCookie: true,
        httpOnly: true,
        sameSite: "Strict",
        budgetRemaining: 2700,
        accountTotal: 3700,
        errors,
        screens,
      },
      null,
      2,
    ),
  );
  console.log(
    `Production HTTPS: real registration/login/invitation, finances, private receipt/discount/duplicates, export/delete and ${screens.length} visual checks passed.`,
  );
} finally {
  if (home)
    await send(`/api/households/${home}`, "DELETE", { name }).catch(() => {});
  await secondContext?.close();
  await browser.close();
}
