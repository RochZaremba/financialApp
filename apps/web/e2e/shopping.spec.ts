import { expect, test, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Keep registration abuse protection enabled; separate this suite's households.
// eslint-disable-next-line no-empty-pattern -- Playwright fixture syntax.
test.beforeAll(async ({}) => {
  await new Promise((resolve) => setTimeout(resolve, 60_000));
});
async function home(page: Page, info: TestInfo) {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
  const unique = `${Date.now()}-${info.project.name}`;
  expect(
    (
      await page.request.post("/api/auth/register", {
        data: {
          name: "Zakupy QA",
          email: `shopping-${unique}@example.com`,
          password: "shopping-private-password",
        },
      })
    ).status(),
  ).toBe(201);
  const household = await page.request
    .post("/api/households", {
      data: { name: `Dom zakupy ${unique}` },
      headers: { "Idempotency-Key": `home-${unique}` },
    })
    .then((r) => r.json());
  const base = `/api/households/${household.id}`;
  const data = await page.request
    .get(`${base}/overview?month=2026-10`)
    .then((r) => r.json());
  return { base, household, data, unique };
}
async function capture(page: Page, info: TestInfo, state: string) {
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.evaluate(() => {
      if (
        document.activeElement instanceof HTMLElement &&
        document.activeElement.matches(".skip-link")
      )
        document.activeElement.blur();
    });
    await page.screenshot({
      path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "shopping"}/${state}-${info.project.name}-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize(
    info.project.use.viewport || { width: 1440, height: 900 },
  );
}

test("household shopping list, shared purchase, stock consumption and repeat history", async ({
  page,
  browser,
}, info) => {
  const { base, household, data, unique } = await home(page, info);
  await page.goto("/");
  if (info.project.name === "desktop")
    await page
      .locator(".sidebar")
      .getByRole("link", { name: "Zakupy i zapasy", exact: true })
      .click();
  else {
    await page.getByRole("link", { name: "Więcej", exact: true }).click();
    await page
      .locator("main")
      .getByRole("link", { name: /Zakupy i zapasy/ })
      .click();
  }
  await expect(
    page.getByRole("heading", { name: "Lista jest pusta" }),
  ).toBeVisible();
  await expect(page.getByLabel("Miesiąc budżetu")).toHaveCount(0);
  await capture(page, info, "shopping-empty");
  await page
    .getByRole("button", { name: "Dodaj produkt", exact: true })
    .click();
  await page.getByLabel("Nazwa produktu", { exact: true }).fill("Mleko");
  await page.getByLabel("Ilość", { exact: true }).fill("0,3");
  await page.getByLabel("Jednostka", { exact: true }).selectOption("l");
  await page.getByLabel("Gdzie przechowywać").selectOption("fridge");
  await page.getByLabel("Szacowany koszt całości (zł)").fill("4,56");
  await page
    .getByLabel("Kategoria zakupu")
    .selectOption(
      data.categories.find((c: { name: string }) => c.name === "Jedzenie").id,
    );
  await capture(page, info, "shopping-editor");
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("4,56");
  await page
    .getByRole("button", { name: "Edytuj produkt: Mleko", exact: true })
    .click();
  await page.getByLabel("Ilość", { exact: true }).fill("0,5");
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("0,5 l");
  const invite = await page.request
    .post(`${base}/invitations`)
    .then((r) => r.json());
  const partner = await browser.newContext({
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
  });
  try {
    expect(
      (
        await partner.request.post("http://localhost:3000/api/auth/register", {
          data: {
            name: "Drugi domownik",
            email: `partner-${unique}@example.com`,
            password: "shopping-private-password",
          },
        })
      ).status(),
    ).toBe(201);
    expect(
      (
        await partner.request.post(
          "http://localhost:3000/api/households/join",
          { data: { token: invite.token } },
        )
      ).status(),
    ).toBe(200);
    const second = await partner.newPage();
    await second.goto("http://localhost:3000/zakupy");
    await expect(second.locator(".shopping-row")).toContainText("Mleko");
    await second
      .getByRole("button", { name: "Kupione: Mleko", exact: true })
      .click();
    await second.getByLabel("Zapłacono za produkt (zł)").fill("5,79");
    await second.getByLabel("Sklep", { exact: true }).fill("Sklep domowy");
    await second
      .getByLabel("Termin ważności", { exact: true })
      .fill("2026-10-10");
    await second
      .getByRole("button", { name: "Potwierdź zakup", exact: true })
      .click();
    await expect(
      second.getByRole("heading", { name: "Lista jest pusta" }),
    ).toBeVisible();
  } finally {
    await partner.close();
  }
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Lista jest pusta" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zapasy", exact: true }).click();
  await expect(page.locator(".shopping-row")).toContainText("0,5 l");
  await page.getByRole("button", { name: "Zużyj: Mleko", exact: true }).click();
  await page.getByLabel("Zużyta ilość (l)").fill("0,1");
  await page
    .getByRole("button", { name: "Zapisz zużycie", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("0,4 l");
  await page
    .getByRole("button", { name: "Edytuj zapas: Mleko", exact: true })
    .click();
  await page.getByLabel("Minimalny zapas").fill("1");
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await capture(page, info, "shopping-stock");
  await page
    .getByRole("button", { name: "Lista zakupów", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Mleko · 0,6 l", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("0,6 l");
  await page
    .getByRole("button", { name: "Usuń z listy: Mleko", exact: true })
    .click();
  await page.getByRole("button", { name: "Usuń produkt", exact: true }).click();
  await page.getByRole("button", { name: "Historia", exact: true }).click();
  await expect(page.locator(".shopping-row")).toContainText("5,79");
  await page.getByLabel("Szukaj w historii zakupów").fill("Sklep domowy");
  await page.getByRole("button", { name: "Szukaj", exact: true }).click();
  await capture(page, info, "shopping-history");
  await page
    .getByRole("button", { name: "Kup ponownie: Mleko", exact: true })
    .click();
  await expect(page.getByLabel("Szacowany koszt całości (zł)")).toHaveValue(
    "5,79",
  );
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Lista zakupów", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("Mleko");
  expect(
    (
      await page.request
        .get(`${base}/transactions?month=2026-10`)
        .then((r) => r.json())
    ).items,
  ).toHaveLength(0);
  await page.request.delete(base, { data: { name: household.name } });
});

test("household shopping receipt import is reviewed, linked and never books a second expense", async ({
  page,
}, info) => {
  const { base, household, data, unique } = await home(page, info);
  const upload = await page.request
    .post(`${base}/receipts`, {
      multipart: {
        file: {
          name: "lidl.png",
          mimeType: "image/png",
          buffer: readFileSync(resolve("../../fixtures/lidl.png")),
        },
      },
    })
    .then((r) => r.json());
  const finalized = await page.request.post(
    `${base}/receipts/${upload.id}/finalize`,
    {
      data: {
        merchant: upload.merchant,
        date: upload.date,
        total: upload.total,
        account_id: data.accounts[0].id,
        items: upload.items.map(
          (item: {
            name: string;
            quantity: string;
            amount: number;
            category_id: string | null;
            confidence: number;
          }) => ({
            name: item.name,
            quantity: item.quantity,
            amount: item.amount,
            category_id: item.category_id || data.categories[0].id,
            confidence: item.confidence,
            reviewed: true,
          }),
        ),
      },
    },
  );
  expect(finalized.status()).toBe(200);
  const receipts = await page.request
    .get(`${base}/shopping/receipts`)
    .then((r) => r.json());
  const line = receipts[0].items[0];
  const pending = await page.request
    .post(`${base}/shopping/items`, {
      data: {
        name: line.name,
        quantity: 1000,
        unit: "szt",
        location: "fridge",
      },
      headers: { "Idempotency-Key": `item-${unique}` },
    })
    .then((r) => r.json());
  await page.goto(`/paragony/${upload.id}`);
  await page
    .getByRole("link", { name: /Dodaj produkty do domowych zapasów/ })
    .click();
  await expect(page.getByLabel("Paragon do uzupełnienia zapasów")).toHaveValue(
    upload.id,
  );
  await page
    .getByRole("button", {
      name: `Dodaj z paragonu: ${line.name}`,
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Ilość", { exact: true })).toHaveValue("");
  await page.getByLabel("Połącz z listą zakupów").selectOption(pending.id);
  await page.getByLabel("Ilość", { exact: true }).fill("1,25");
  await page.getByLabel("Jednostka", { exact: true }).selectOption("kg");
  await page.getByLabel("Gdzie przechowywać").selectOption("fridge");
  await page.getByLabel("Termin ważności", { exact: true }).fill("2026-10-09");
  await capture(page, info, "shopping-receipt-import");
  await page
    .getByRole("button", { name: "Dodaj do zapasów", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("1,25 kg");
  await expect(
    page.locator(".receipt-stock-row").filter({ hasText: line.name }),
  ).toContainText("Dodano do zapasów");
  await page.reload();
  await expect(page.locator(".shopping-row")).toHaveCount(1);
  const stock = await page.request
    .get(`${base}/shopping`)
    .then((r) => r.json());
  expect(stock.items).toHaveLength(0);
  expect(stock.stock).toHaveLength(1);
  expect(
    (
      await page.request
        .get(`${base}/transactions?month=2026-10`)
        .then((r) => r.json())
    ).items,
  ).toHaveLength(1);
  await page
    .getByRole("button", { name: `Usuń zapas: ${line.name}`, exact: true })
    .click();
  await page.getByRole("button", { name: "Usuń produkt", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Zajrzyj do lodówki i szafek" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Historia", exact: true }).click();
  await expect(page.locator(".shopping-row")).toContainText(line.name);
  await page.request.delete(base, { data: { name: household.name } });
});

test("household shopping navigation, loading failure retry and stale stock recovery", async ({
  page,
}, info) => {
  const { base, household, unique } = await home(page, info);
  await page.route("**/sw.js", (route) => route.abort());
  await page.addInitScript(() =>
    navigator.serviceWorker
      .getRegistrations()
      .then((regs) => Promise.all(regs.map((reg) => reg.unregister()))),
  );
  let failed = true;
  await page.route(`**${base}/shopping`, async (route) => {
    if (failed)
      await route.fulfill({
        status: 503,
        json: { detail: "Zakupy chwilowo niedostępne." },
      });
    else await route.continue();
  });
  await page.goto("/zakupy");
  await expect(
    page.getByRole("heading", { name: "Nie udało się wczytać zakupów" }),
  ).toBeVisible();
  await capture(page, info, "shopping-error");
  failed = false;
  await page
    .getByRole("button", { name: "Spróbuj ponownie", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Lista jest pusta" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zapasy", exact: true }).click();
  await page.getByRole("button", { name: "Dodaj zapas", exact: true }).click();
  await page.getByLabel("Nazwa produktu", { exact: true }).fill("Ryż");
  await page.getByLabel("Ilość", { exact: true }).fill("0,5");
  await page.getByLabel("Jednostka", { exact: true }).selectOption("kg");
  await page.getByLabel("Minimalny zapas").fill("1");
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await page.getByRole("button", { name: "Zużyj: Ryż", exact: true }).click();
  await page.getByLabel("Zużyta ilość (kg)").fill("1");
  await page
    .getByRole("button", { name: "Zapisz zużycie", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Nie możesz zużyć więcej",
  );
  await page.getByLabel("Zużyta ilość (kg)").fill("0,1");
  await page
    .getByRole("button", { name: "Zapisz zużycie", exact: true })
    .click();
  await expect(page.locator(".shopping-row")).toContainText("0,4 kg");
  await page
    .getByRole("button", { name: "Edytuj zapas: Ryż", exact: true })
    .click();
  const stock = await page.request
    .get(`${base}/shopping`)
    .then((r) => r.json())
    .then((r) => r.stock[0]);
  expect(
    (
      await page.request.post(`${base}/shopping/stock/${stock.id}/consume`, {
        data: { quantity: 100, expected_updated_at: stock.updated_at },
        headers: { "Idempotency-Key": `consume-${unique}` },
      })
    ).status(),
  ).toBe(200);
  await page.getByLabel("Ilość", { exact: true }).fill("0,8");
  await page
    .getByRole("button", { name: "Zapisz produkt", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Ktoś zmienił ten produkt",
  );
  await capture(page, info, "shopping-stale");
  await page
    .getByRole("button", { name: "Wczytaj aktualne dane", exact: true })
    .click();
  await expect(page.locator(".shopping-editor")).toHaveCount(0);
  await expect(page.locator(".shopping-row")).toContainText("0,3 kg");
  await page.reload();
  await expect(page.locator(".shopping-row")).toContainText("0,3 kg");
  await page.setViewportSize({ width: 1440, height: 650 });
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "Ustawienia domu", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Wasz dom i ustawienia." }),
  ).toBeVisible();
  for (const link of await page
    .locator(".sidebar-navigation .nav-item")
    .all()) {
    await link.focus();
    expect(
      await link.evaluate((el) => {
        const r = el.getBoundingClientRect();
        return r.top >= 0 && r.bottom <= innerHeight;
      }),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/zakupy");
  await capture(page, info, "shopping-navigation");
  await page.setViewportSize({ width: 720, height: 450 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("link", { name: "Więcej", exact: true }),
  ).toHaveAttribute("aria-current", "location");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dodaj");
  await page
    .getByRole("link", { name: "Produkt na listę zakupów", exact: true })
    .click();
  await expect(
    page.getByLabel("Nazwa produktu", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Anuluj", exact: true }).click();
  await page
    .locator(".sidebar")
    .getByRole("link", {
      name: "Domownicy i ustawienia: Zakupy QA",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "Wasz dom i ustawienia." }),
  ).toBeVisible();
  await page.request.delete(base, { data: { name: household.name } });
  await page.locator(".sidebar-logout").click();
  await expect(
    page.getByRole("heading", { name: "Witaj z powrotem." }),
  ).toBeVisible();
});
