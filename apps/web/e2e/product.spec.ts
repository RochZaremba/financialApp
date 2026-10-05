import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
const fixture = path.resolve("../../fixtures/lidl.png");
const password = "test-password-for-private-household";
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-05T12:00:00+02:00"));
});

test.describe("receipt AI capability", () => {
  test.use({ serviceWorkers: "block" });
  test("Gemini availability and missing-key upload notice", async ({
    page,
  }) => {
    let available = true;
    // Only public capability metadata is simulated; provider/network contracts
    // and receipt persistence are exercised separately by API integration tests.
    await page.route("**/api/auth/me", async (route) => {
      const response = await route.fetch();
      if (response.ok()) {
        await route.fulfill({
          response,
          json: {
            ...(await response.json()),
            receipt_provider: "gemini",
            receipt_ai_available: available,
          },
        });
      } else await route.fulfill({ response });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
    await expect(
      page.getByRole("heading", { name: "Cześć, Roch." }),
    ).toBeVisible();
    await go(page, "/dodaj");
    await expect(
      page.getByText("Automatyczny odczyt zdjęć wymaga", { exact: false }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Użyj przykładowego paragonu Lidl" }),
    ).toHaveCount(0);
    available = false;
    await page.reload();
    await expect(
      page.getByText("Automatyczny odczyt zdjęć wymaga", { exact: false }),
    ).toBeVisible();
  });
});

async function go(page: Page, url: string) {
  // Hard document replacement during post-save refetches cancels those
  // requests. Let the old document settle before testing another entry URL;
  // native WebKit cancellation diagnostics must not obscure page exceptions.
  if (page.url() !== "about:blank") await page.waitForLoadState("networkidle");
  await page.goto(url);
  await expect(page.locator("main h1")).toBeVisible();
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

test("complete household budget, receipts, goals and second-member flow", async ({
  page,
  browser,
}) => {
  const unique = Date.now() + "-" + Math.random().toString(16).slice(2);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Pierwszy raz tutaj? Utwórz konto" })
    .click();
  await page.getByLabel("Jak masz na imię?").fill("Roch");
  await page
    .getByLabel("Adres e-mail", { exact: true })
    .fill(`roch-${unique}@example.com`);
  await page.getByLabel("Hasło", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Utwórz konto", exact: true }).click();
  await page.getByLabel("Nazwa gospodarstwa").fill("Nasz dom " + unique);
  await page.getByRole("button", { name: "Utwórz nasz dom" }).click();
  // Onboarding and Home share the greeting. Require the household shell so
  // this assertion cannot pass while household creation is still in flight.
  await expect(page.locator(".app-shell")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  const me = await page.request.get("/api/auth/me").then((r) => r.json());
  const home = me.households[0].id;
  await page
    .getByRole("link", { name: "Zaplanuj miesiąc", exact: true })
    .click();
  await page.getByLabel("Kwota źródła 1 (zł)").fill("10000");
  await page.getByLabel("Mieszkanie — plan (zł)").fill("2000");
  await page.getByLabel("Jedzenie — plan (zł)").fill("2000");
  await page.getByLabel("Rachunki — plan (zł)").fill("1000");
  await page.getByLabel("Transport — plan (zł)").fill("1000");
  await page.getByLabel("Przyjemności — plan (zł)").fill("2000");
  await page.getByLabel("Dom i zakupy — plan (zł)").fill("1400");
  await page.getByLabel("Roch — plan (zł)").fill("600");
  await expect(
    page.getByText("Wszystko przydzielone. Dobry plan!"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.getByText("Wszystko ma swoje miejsce")).toBeVisible();
  await go(page, "/dodaj?type=income");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("10000");
  await page.getByLabel("Skąd te pieniądze?").fill("Wspólne wynagrodzenie");
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  await go(page, "/dodaj?type=pocket");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("600");
  await page.getByLabel("Nazwa lub krótki opis").fill("Kieszonkowe Rocha");
  await page
    .getByRole("button", { name: "Wypłać kieszonkowe", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  await expect(page.getByText("Wypłacone", { exact: true })).toBeVisible();
  await go(page, "/dodaj?type=expense");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("49,90");
  await page.getByLabel("Nazwa lub krótki opis").fill("Biedronka — zakupy");
  await page
    .getByLabel("Kategoria", { exact: true })
    .selectOption({ label: "Jedzenie" });
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  await expect(page.locator(".balance-number")).toContainText("9\u00a0350,10");
  // Capture a real browser file input; OCR fixture recognizes only this exact image.
  await go(page, "/dodaj");
  await page.locator("input[type=file]").last().setInputFiles(fixture);
  await expect(
    page.getByRole("heading", { name: "Jeszcze jedna chwila." }),
  ).toBeVisible();
  await expect(page.locator(".receipt-item.uncertain")).toHaveCount(1);
  await page
    .locator(".receipt-item.uncertain")
    .getByRole("button", { name: "Dom i zakupy", exact: true })
    .click();
  await expect(page.locator(".receipt-item.uncertain")).toHaveCount(0);
  await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  const budget = await page.request
    .get(`/api/households/${home}/budget/2026-10`)
    .then((r) => r.json());
  expect(budget.expenses).toBe(18965);
  expect(budget.pocket).toBe(60000);
  expect(budget.remaining).toBe(921035);
  // The same image is flagged as a possible duplicate and remains discoverable in Inbox.
  await go(page, "/dodaj");
  await page.locator("input[type=file]").last().setInputFiles(fixture);
  await expect(
    page.getByRole("heading", { name: "Sprawdź możliwy duplikat." }),
  ).toBeVisible();
  await expect(page.locator(".receipt-item.uncertain")).toHaveCount(0);
  await go(page, "/inbox");
  await page.getByRole("link").filter({ hasText: "Zatwierdź paragon" }).click();
  await page
    .getByRole("button", { name: "Usuń ten szkic", exact: true })
    .click();
  await page.getByRole("button", { name: "Usuń szkic", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Wszystko na bieżąco." }),
  ).toBeVisible();
  await go(page, "/transakcje");
  await page.getByLabel("Szukaj transakcji").fill("Lidl");
  const row = page.locator("details").filter({ hasText: "Lidl" });
  await row.locator("summary").click();
  await expect(row.locator(".transaction-details")).toContainText("Jedzenie");
  await expect(row.locator(".transaction-details")).toContainText(
    "Dom i zakupy",
  );
  await expect(row.locator(".transaction-details")).toContainText(
    "Przyjemności",
  );
  await go(page, "/inbox");
  await expect(
    page.getByRole("heading", { name: "Wszystko na bieżąco." }),
  ).toBeVisible();
  // A past-month unallocated expense must be resolvable directly from Inbox.
  await go(page, "/dodaj?type=expense");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("10");
  await page.getByLabel("Data", { exact: true }).fill("2026-09-30");
  await page.getByLabel("Nazwa lub krótki opis").fill("Wydatek do przypisania");
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  await go(page, "/inbox");
  await page.getByText("Wydatek do przypisania", { exact: true }).click();
  await page
    .getByLabel("Kategoria wydatku")
    .selectOption({ label: "Jedzenie" });
  await page.getByRole("button", { name: "Przypisz kategorię" }).click();
  await go(page, "/inbox");
  await expect(
    page.getByRole("heading", { name: "Wszystko na bieżąco." }),
  ).toBeVisible();
  await go(page, "/cele");
  await page.getByRole("button", { name: "Nowy cel" }).click();
  await page.getByLabel("Nazwa celu").fill("Nasze wakacje");
  await page.getByLabel("Chcemy zebrać (zł)").fill("8000");
  await page.getByLabel("Już odłożone na start (zł)").fill("500");
  await page.getByLabel("Miesięczny plan (zł)").fill("600");
  await page.getByRole("button", { name: "Zapisz cel" }).click();
  await expect(
    page.getByRole("heading", { name: "Nasze wakacje", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Odłóż na cel", exact: true }).click();
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("600");
  await page.getByLabel("Nazwa lub krótki opis").fill("Na nasze wakacje");
  await page.getByRole("button", { name: "Odłóż na cel", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Cześć, Roch." }),
  ).toBeVisible();
  await go(page, "/cele");
  await expect(page.locator(".goal-amount")).toContainText("1\u00a0100 zł");
  await page.getByRole("button", { name: "Edytuj cel: Nasze wakacje" }).click();
  await page.getByLabel("Nazwa celu").fill("Wakacje razem");
  await page.getByRole("button", { name: "Zapisz cel" }).click();
  await expect(
    page.getByRole("heading", { name: "Wakacje razem" }),
  ).toBeVisible();
  await go(page, "/cykliczne");
  await page.getByRole("button", { name: "Nowy stały wydatek" }).click();
  await page.getByLabel("Nazwa płatności").fill("Internet domowy");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("69");
  await page.getByLabel("Dzień miesiąca").fill("31");
  await page.getByRole("button", { name: "Zapisz płatność" }).click();
  await page.getByRole("button", { name: "Opłacone", exact: true }).click();
  await expect(page.locator(".recurring-actions .pill")).toContainText(
    "Opłacone",
  );
  await go(page, "/ustawienia");
  await page
    .getByRole("button", { name: "Zaproś do wspólnego budżetu" })
    .click();
  const invite = await page
    .getByLabel("Link zaproszenia (ważny 7 dni)")
    .inputValue();
  const secondContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
  });
  const second = await secondContext.newPage();
  await second.goto(invite);
  await second.getByLabel("Jak masz na imię?").fill("Kaja");
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
    second.getByRole("heading", { name: "Cześć, Kaja." }),
  ).toBeVisible();
  await noOverflow(second);
  const anotherResponse = await second.request.post("/api/households", {
    data: { name: "Osobny dom" },
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  expect(anotherResponse.status()).toBe(201);
  const another = await anotherResponse.json();
  expect(
    (
      await page.request.get(
        `/api/households/${another.id}/overview?month=2026-10`,
      )
    ).status(),
  ).toBe(403);
  expect(
    (await second.request.post(`/api/households/${home}/invitations`)).status(),
  ).toBe(403);
  await second.request.delete(`/api/households/${another.id}`, {
    data: { name: "Osobny dom" },
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  await secondContext.close();
  await page.reload();
  await expect(page.getByText("Kaja", { exact: true }).first()).toBeVisible();
  // After joining, update the budget to give both members their own terminal allocations.
  await go(page, "/budzet");
  await page.getByRole("button", { name: "Edytuj plan" }).click();
  await page.getByLabel("Kaja — plan (zł)").fill("600");
  await page.getByLabel("Przyjemności — plan (zł)").fill("1400");
  await expect(
    page.getByText("Wszystko przydzielone. Dobry plan!"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await go(page, "/analiza");
  await noOverflow(page);
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(axe.violations).toEqual([]);
  expect(errors).toEqual([]);
  // Clean up only this isolated E2E household, keeping demo data untouched.
  await page.request.delete(`/api/households/${home}`, {
    data: { name: "Nasz dom " + unique },
  });
});

test.describe("connection and session states", () => {
  // Isolate HTTP fault injection from service-worker-owned fetches in WebKit.
  test.use({ serviceWorkers: "block" });
  test("unreliable offline hint keeps reachable API usable and failed reads retryable", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
    await expect(
      page.getByRole("heading", { name: "Cześć, Roch." }),
    ).toBeVisible();
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "onLine", {
        get: () => false,
        configurable: true,
      });
      window.addEventListener("load", () =>
        window.dispatchEvent(new Event("offline")),
      );
    });
    await go(page, "/cele");
    await expect(
      page.getByRole("heading", { name: "Wasze cele." }),
    ).toBeVisible();
    await expect(
      page.getByText("Sprawdź połączenie. Zapis może się nie udać."),
    ).toBeVisible();
    await page.route("**/api/households/*/overview?*", (route) =>
      route.abort("failed"),
    );
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Nie udało się wczytać danych" }),
    ).toBeVisible({ timeout: 15000 });
    await page.unroute("**/api/households/*/overview?*");
    await page.getByRole("button", { name: "Spróbuj ponownie" }).click();
    await expect(
      page.getByRole("heading", { name: "Wasze cele." }),
    ).toBeVisible();
  });
  test("offline, API failure, session expiry and PWA state", async ({
    page,
    context,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
    await expect(
      page.getByRole("heading", { name: "Cześć, Roch." }),
    ).toBeVisible();
    await go(page, "/ustawienia");
    await context.setOffline(true);
    await expect(
      page.getByText("Sprawdź połączenie. Zapis może się nie udać."),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Wyloguj się", exact: true })
      .click();
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "Brak połączenia. Sprawdź internet i spróbuj ponownie.",
    );
    await context.setOffline(false);
    await page.route("**/api/households/*/overview?*", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Przerwa testowa. Spróbuj ponownie." }),
      }),
    );
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Nie udało się wczytać danych" }),
    ).toBeVisible({ timeout: 20000 });
    await page.unroute("**/api/households/*/overview?*");
    await page.getByRole("button", { name: "Spróbuj ponownie" }).click();
    await expect(
      page.getByRole("heading", { name: "Wasz dom i ustawienia." }),
    ).toBeVisible();
    const manifest = await page.request
      .get("/manifest.webmanifest")
      .then((r) => r.json());
    expect(manifest.display).toBe("standalone");
    expect(manifest.icons.length).toBe(2);
    expect((await page.request.get("/sw.js")).status()).toBe(200);
    await context.clearCookies();
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Witaj z powrotem." }),
    ).toBeVisible();
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(axe.violations).toEqual([]);
  });
});

test("manual splits, honest photo draft and persisted correction", async ({
  page,
  browserName,
}) => {
  const unique = crypto.randomUUID();
  const registered = await page.request.post("/api/auth/register", {
    data: { name: "QA", email: `edge-${unique}@example.com`, password },
  });
  expect(registered.status()).toBe(201);
  const homeResponse = await page.request.post("/api/households", {
    data: { name: "Edge " + unique },
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  expect(homeResponse.status()).toBe(201);
  const home = (await homeResponse.json()).id;
  await go(page, "/dodaj?type=expense");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("30");
  await page.getByLabel("Nazwa lub krótki opis").fill("Podzielone zakupy");
  await page.getByRole("button", { name: "Podziel między kategorie" }).click();
  await page
    .getByLabel("Kategoria 1", { exact: true })
    .selectOption({ label: "Jedzenie" });
  await page.getByLabel("Kwota 1 (zł)", { exact: true }).fill("10");
  await page
    .getByRole("button", { name: "Dodaj kategorię", exact: true })
    .click();
  await page
    .getByLabel("Kategoria 2", { exact: true })
    .selectOption({ label: "Dom i zakupy" });
  await page.getByLabel("Kwota 2 (zł)", { exact: true }).fill("19");
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Suma kategorii musi być równa kwocie wydatku.",
  );
  await page.getByLabel("Kwota 2 (zł)", { exact: true }).fill("20");
  await page.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(page.getByRole("heading", { name: "Cześć, QA." })).toBeVisible();
  const history = await page.request
    .get(`/api/households/${home}/transactions`)
    .then((r) => r.json());
  expect(
    history.items[0].allocations
      .map((a: { amount: number }) => a.amount)
      .sort(),
  ).toEqual([1000, 2000]);
  await go(page, "/dodaj");
  // A different real image must never receive invented fixture OCR data.
  await page
    .locator("input[type=file]")
    .last()
    .setInputFiles(path.resolve("public/icon-192.png"));
  await expect(
    page.getByText("Uzupełnij koszyk", { exact: true }),
  ).toBeVisible();
  const draftUrl = page.url();
  await page
    .getByLabel("Sklep", { exact: true })
    .fill("Ręcznie poprawiony sklep");
  await page.getByLabel("Data zakupu", { exact: true }).fill("2026-10-05");
  await page.getByLabel("Suma paragonu (zł)", { exact: true }).fill("12,34");
  await page
    .getByRole("button", { name: "Dodaj pozycję", exact: true })
    .click();
  await page.getByLabel("Pozycja 1", { exact: true }).fill("Jabłka");
  await expect(page.getByLabel("Ilość", { exact: true })).toHaveValue("");
  await page.getByLabel("Kwota pozycji (zł)", { exact: true }).fill("12,34");
  await page
    .locator(".receipt-item")
    .getByRole("button", { name: "Jedzenie", exact: true })
    .click();
  await expect(page.locator(".receipt-item-summary")).toContainText("Jedzenie");
  await expect(page.locator(".receipt-item.uncertain")).toHaveCount(0);
  await page.getByRole("button", { name: "Zapisz szkic", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Szkic paragonu zapisany",
  );
  await page.reload();
  await expect(page.getByLabel("Sklep", { exact: true })).toHaveValue(
    "Ręcznie poprawiony sklep",
  );
  await expect(page.locator(".receipt-item-summary")).toContainText("Jedzenie");
  await page.getByRole("button", { name: "Zobacz zdjęcie" }).click();
  await expect(
    page.getByRole("img", { name: "Zdjęcie przesłanego paragonu" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Pobierz zdjęcie" }),
  ).toHaveAttribute("download", "paragon.png");
  await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
  await expect(page.getByRole("heading", { name: "Cześć, QA." })).toBeVisible();
  await go(page, new URL(draftUrl).pathname);
  await expect(
    page.getByRole("heading", { name: "Paragon zapisany." }),
  ).toBeVisible();
  await expect(page.getByLabel("Sklep", { exact: true })).toBeDisabled();
  await go(page, "/inbox");
  await expect(
    page.getByRole("heading", { name: "Wszystko na bieżąco." }),
  ).toBeVisible();

  const otherResponse = await page.request.post("/api/households", {
    data: { name: "Drugi QA dom" },
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  expect(otherResponse.status()).toBe(201);
  const other = (await otherResponse.json()).id;
  await go(page, "/budzet");
  // Prime both cached households; a dirty form cannot cross the boundary.
  await page.getByLabel("Gospodarstwo", { exact: true }).selectOption(other);
  await expect(page.getByLabel("Kwota źródła 1 (zł)")).toHaveValue("0,00");
  await page.getByLabel("Gospodarstwo", { exact: true }).selectOption(home);
  await page.getByLabel("Kwota źródła 1 (zł)").fill("1000");
  await page.getByLabel("Jedzenie — plan (zł)").fill("300");
  await page.getByLabel("Gospodarstwo", { exact: true }).selectOption(other);
  await expect(page.getByLabel("Kwota źródła 1 (zł)")).toHaveValue("0,00");
  await expect(page.getByLabel("Jedzenie — plan (zł)")).toHaveValue("0,00");
  await page.getByLabel("Gospodarstwo", { exact: true }).selectOption(home);
  await go(page, "/dodaj?type=expense");
  await page.getByLabel("Miesiąc budżetu").fill("2026-09");
  await expect(page.getByLabel("Data", { exact: true })).toHaveValue(
    "2026-09-01",
  );
  await page.getByLabel("Miesiąc budżetu").fill("2026-10");
  await expect(page.getByLabel("Data", { exact: true })).toHaveValue(
    "2026-10-05",
  );
  await page.request.delete(`/api/households/${other}`, {
    data: { name: "Drugi QA dom" },
  });
  await go(page, "/inbox");
  // The real installed worker serves only a public offline page, never financial responses.
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
  const cached = await page.evaluate(async () => {
    const urls: string[] = [];
    for (const name of await caches.keys())
      for (const request of await (await caches.open(name)).keys())
        urls.push(new URL(request.url).pathname);
    return urls;
  });
  expect(cached.sort()).toEqual([
    "/icon-192.png",
    "/icon-512.png",
    "/offline.html",
  ]);
  if (browserName !== "webkit") {
    await page.context().setOffline(true);
    await page.goto("/offline-network-check");
    await expect(
      page.getByRole("heading", { name: "Wrócimy za chwilę." }),
    ).toBeVisible();
    await page.context().setOffline(false);
  } else {
    test.info().annotations.push({
      type: "issue",
      description:
        "Playwright #42775: WebKit offline emulation blocks SW responses; actual origin outage is verified by scripts/webkit-offline.mjs.",
    });
  }
  await page.request.delete(`/api/households/${home}`, {
    data: { name: "Edge " + unique },
  });
});

test.describe("independent release regressions", () => {
  test.use({ serviceWorkers: "block" });
  test("partial OCR, discounts, exact balances, payout targets and lost upload response", async ({
    page,
    browser,
  }) => {
    const unique = crypto.randomUUID();
    const homeName = `Release ${unique}`;
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const created = await page.request.post("/api/auth/register", {
      data: {
        name: "Release QA",
        email: `release-${unique}@example.com`,
        password,
      },
    });
    expect(created.status()).toBe(201);
    const response = await page.request.post("/api/households", {
      data: { name: homeName },
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    const home = (await response.json()).id;
    const root = `/api/households/${home}`;
    const second = await browser.newContext({
      baseURL: "http://localhost:3000",
    });
    try {
      await page.request.put(root + "/budget/2026-10", {
        data: { planned_income: 0, allocations: [] },
      });
      await go(page, "/");
      await expect(page.getByText("Plan gotowy", { exact: true })).toHaveCount(
        0,
      );
      await expect(
        page.getByText("Uzupełnij dochód", { exact: true }),
      ).toBeVisible();
      await go(page, "/budzet");
      await expect(
        page.getByText("Wszystko ma swoje miejsce", { exact: true }),
      ).toHaveCount(0);
      await go(page, "/dodaj?type=expense");
      await page.getByLabel("Nazwa lub krótki opis").fill("Kwota zero");
      await page.getByRole("button", { name: "Zapisz transakcję" }).click();
      await expect(page.locator("main [role=alert]")).toContainText(
        "Kwota transakcji musi być większa od zera.",
      );
      await go(page, "/konta");
      await page
        .getByRole("button", { name: "Dodaj konto", exact: true })
        .click();
      await page
        .getByLabel("Nazwa konta", { exact: true })
        .fill("Ujemne saldo");
      await page
        .getByLabel("Saldo na start (zł)", { exact: true })
        .fill("-0,01");
      await page
        .locator("form")
        .getByRole("button", { name: "Dodaj konto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Ujemne saldo", exact: true }),
      ).toBeVisible();
      const negativeCard = page
        .locator(".account-card")
        .filter({ hasText: "Ujemne saldo" });
      await expect(negativeCard).toContainText("−0,01 zł");
      const invited = await page.request
        .post(root + "/invitations")
        .then((r) => r.json());
      await second.request.post("/api/auth/register", {
        data: {
          name: "Kaja",
          email: `release-kaja-${unique}@example.com`,
          password,
        },
      });
      expect(
        (
          await second.request.post("/api/households/join", {
            data: { token: invited.token },
          })
        ).status(),
      ).toBe(200);
      const data = await page.request
        .get(root + "/overview?month=2026-10")
        .then((r) => r.json());
      const members = data.members as { id: string }[];
      const goals = [];
      for (const [name, amount] of [
        ["Mały cel", 1],
        ["Drugi cel", 25000],
      ] as const) {
        const goal = await page.request
          .post(root + "/goals", {
            data: { name, target: 100000, opening_amount: amount },
            headers: { "Idempotency-Key": crypto.randomUUID() },
          })
          .then((r) => r.json());
        goals.push(goal);
      }
      await page.request.put(root + "/budget/2026-10", {
        data: {
          planned_income: 125000,
          allocations: [
            { kind: "pocket", reference_id: members[0].id, amount: 60000 },
            { kind: "pocket", reference_id: members[1].id, amount: 30000 },
            { kind: "goal", reference_id: goals[0].id, amount: 10000 },
            { kind: "goal", reference_id: goals[1].id, amount: 25000 },
          ],
        },
      });
      await go(page, "/dodaj?type=pocket");
      await expect(page.getByLabel("Kwota (zł)", { exact: true })).toHaveValue(
        "600,00",
      );
      await page
        .getByLabel("Dla kogo?", { exact: true })
        .selectOption(members[1].id);
      await expect(page.getByLabel("Kwota (zł)", { exact: true })).toHaveValue(
        "300,00",
      );
      await page.getByLabel("Nazwa lub krótki opis").fill("Kieszonkowe Kai");
      await page
        .getByRole("button", { name: "Wypłać kieszonkowe", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Cześć, Release QA." }),
      ).toBeVisible();
      await go(page, "/dodaj?type=saving");
      await expect(page.getByLabel("Kwota (zł)", { exact: true })).toHaveValue(
        "100,00",
      );
      await page
        .getByLabel("Na jaki cel?", { exact: true })
        .selectOption(goals[1].id);
      await expect(page.getByLabel("Kwota (zł)", { exact: true })).toHaveValue(
        "250,00",
      );
      await go(page, "/cele");
      await expect(
        page
          .locator(".goal-card")
          .filter({ hasText: "Mały cel" })
          .locator(".goal-amount"),
      ).toContainText("0,01 zł");
      await go(page, "/dodaj?type=transfer");
      const source = page.getByLabel("Z konta", { exact: true }),
        dest = page.getByLabel("Na konto", { exact: true });
      await source.selectOption(await dest.inputValue());
      expect(await source.inputValue()).not.toBe(await dest.inputValue());
      await page.getByLabel("Kwota (zł)", { exact: true }).fill("0,01");
      await page.getByLabel("Nazwa lub krótki opis").fill("Transfer grosza");
      await page.getByRole("button", { name: "Zapisz transakcję" }).click();
      await expect(
        page.getByRole("heading", { name: "Cześć, Release QA." }),
      ).toBeVisible();
      await go(page, "/dodaj");
      await page
        .locator("input[type=file]")
        .last()
        .setInputFiles(path.resolve("public/icon-192.png"));
      await expect(page.getByLabel("Data zakupu", { exact: true })).toHaveValue(
        "",
      );
      await page.getByLabel("Sklep", { exact: true }).fill("Poprawiony sklep");
      await page
        .getByRole("button", { name: "Dodaj pozycję", exact: true })
        .click();
      await page.getByLabel("Pozycja 1", { exact: true }).fill("Jabłka");
      await expect(page.getByLabel("Ilość", { exact: true })).toHaveValue("");
      await page
        .locator(".receipt-item")
        .getByRole("button", { name: "Jedzenie", exact: true })
        .click();
      await expect(
        page.getByLabel("Kwota pozycji (zł)", { exact: true }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Zapisz szkic", exact: true })
        .click();
      await expect(page.getByRole("status")).toContainText(
        "Szkic paragonu zapisany",
      );
      await page.reload();
      await expect(page.getByLabel("Pozycja 1", { exact: true })).toHaveValue(
        "Jabłka",
      );
      await expect(page.getByLabel("Data zakupu", { exact: true })).toHaveValue(
        "",
      );
      await expect(
        page.getByLabel("Kwota pozycji (zł)", { exact: true }),
      ).toHaveValue("");
      await expect(page.getByLabel("Ilość", { exact: true })).toHaveValue("");
      await page.getByLabel("Data zakupu", { exact: true }).fill("2026-10-05");
      await page
        .getByLabel("Suma paragonu (zł)", { exact: true })
        .fill("19,99");
      await page.getByLabel("Kwota pozycji (zł)", { exact: true }).fill("20");
      await expect(page.locator(".receipt-item-summary")).toContainText(
        "Jedzenie",
      );
      await page
        .getByRole("button", { name: "Dodaj pozycję", exact: true })
        .click();
      await page.getByLabel("Pozycja 2", { exact: true }).fill("Rabat");
      await page
        .locator(".receipt-item")
        .nth(1)
        .getByLabel("Kwota pozycji (zł)", { exact: true })
        .fill("-0,01");
      await page
        .locator(".receipt-item")
        .nth(1)
        .getByRole("button", { name: "Jedzenie", exact: true })
        .click();
      await page.getByLabel("Suma paragonu (zł)", { exact: true }).fill("20");
      await expect(
        page.getByRole("heading", { name: "Popraw kwoty paragonu." }),
      ).toBeVisible();
      await page
        .getByLabel("Suma paragonu (zł)", { exact: true })
        .fill("19,99");
      await page
        .getByRole("button", { name: "Edytuj pozycję 2", exact: true })
        .click();
      const discount = page.locator(".receipt-item").nth(1);
      await discount
        .getByLabel("Kategoria", { exact: true })
        .selectOption({ label: "Dom i zakupy" });
      await expect(page.locator("main [role=alert]")).toContainText(
        "Przypisz rabat do kategorii zakupów",
      );
      await discount
        .getByRole("button", { name: "Jedzenie", exact: true })
        .click();
      await expect(page.locator("main [role=alert]")).toHaveCount(0);
      await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
      await expect(
        page.getByRole("heading", { name: "Cześć, Release QA." }),
      ).toBeVisible();
      const budget = await page.request
        .get(root + "/budget/2026-10")
        .then((r) => r.json());
      expect(budget.expenses).toBe(1999);
      expect(budget.pocket).toBe(30000);
      expect(budget.remaining).toBe(93001);
      await go(page, "/dodaj");
      // Preserve native multipart bytes in every engine. Playwright's WebKit
      // route.fetch interception corrupts binary multipart bodies (#14624).
      // The real request commits; only delivery to the app fails once.
      await page.evaluate((root) => {
        const state = {
          lost: true,
          keys: [] as (string | null)[],
          ids: [] as string[],
        };
        const original = window.fetch.bind(window);
        const browserWindow = window as typeof window & {
          releaseUploadTrace: typeof state;
        };
        browserWindow.releaseUploadTrace = state;
        window.fetch = async (input, init) => {
          const response = await original(input, init);
          if (String(input) === root + "/receipts" && init?.method === "POST") {
            state.keys.push(new Headers(init.headers).get("Idempotency-Key"));
            state.ids.push((await response.clone().json()).id);
            if (state.lost) {
              state.lost = false;
              throw new TypeError(
                "Simulated lost upload response after real commit",
              );
            }
          }
          return response;
        };
      }, root);
      await page
        .getByRole("button", { name: "Użyj przykładowego paragonu Lidl" })
        .click();
      await expect(page.locator("main [role=alert]")).toBeVisible();
      await page
        .getByRole("button", { name: "Użyj przykładowego paragonu Lidl" })
        .click();
      await expect(
        page.getByRole("heading", { name: "Jeszcze jedna chwila." }),
      ).toBeVisible();
      const { keys, ids } = await page.evaluate(
        () =>
          (
            window as typeof window & {
              releaseUploadTrace: { keys: (string | null)[]; ids: string[] };
            }
          ).releaseUploadTrace,
      );
      expect(keys).toHaveLength(2);
      expect(keys[0]).toBeTruthy();
      expect(keys[1]).toBe(keys[0]);
      expect(ids[1]).toBe(ids[0]);
      const pending = await page.request
        .get(root + "/overview?month=2026-10")
        .then((r) => r.json());
      expect(pending.tasks).toHaveLength(1);
      // Different image bytes can still document the same receipt. Correcting
      // OCR must reveal the duplicate and require a separate-purchase decision.
      const food = data.categories.find(
        (category: { name: string }) => category.name === "Jedzenie",
      ).id;
      expect(
        (
          await page.request.put(root + "/receipts/" + ids[0], {
            data: {
              merchant: "POPRAWIONY SKLEP",
              date: "2026-10-05",
              total: 1999,
              items: [
                {
                  name: "Jabłka",
                  quantity: "1",
                  amount: 1999,
                  category_id: food,
                  confidence: 99,
                  reviewed: true,
                },
              ],
            },
          })
        ).status(),
      ).toBe(200);
      await page.reload();
      await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
      await expect(page.locator("main [role=alert]")).toContainText(
        "Ten paragon może już być zapisany",
      );
      await expect(
        page.getByRole("heading", { name: "Sprawdź możliwy duplikat." }),
      ).toBeVisible();
      expect(
        await page.request
          .get(root + "/budget/2026-10")
          .then((r) => r.json())
          .then((b) => b.expenses),
      ).toBe(1999);
      // Recomputed suspicion must replace the finalization fallback after
      // correcting OCR; no financial operation happens on draft save.
      await page.getByLabel("Sklep", { exact: true }).fill("Inny sklep");
      await page
        .getByRole("button", { name: "Zapisz szkic", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Wszystko wygląda dobrze." }),
      ).toBeVisible();
      await expect(
        page.getByRole("checkbox", {
          name: "Jeśli ten paragon już istnieje, potwierdzam, że to osobny zakup.",
        }),
      ).toHaveCount(0);
      expect(
        await page.request
          .get(root + "/budget/2026-10")
          .then((r) => r.json())
          .then((b) => b.expenses),
      ).toBe(1999);
      await page.getByLabel("Sklep", { exact: true }).fill("POPRAWIONY SKLEP");
      await page
        .getByRole("button", { name: "Zatwierdź paragon", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Sprawdź możliwy duplikat." }),
      ).toBeVisible();
      await page
        .getByRole("checkbox", {
          name: "Jeśli ten paragon już istnieje, potwierdzam, że to osobny zakup.",
        })
        .check();
      await page.getByRole("button", { name: "Zatwierdź paragon" }).click();
      await expect(
        page.getByRole("heading", { name: "Cześć, Release QA." }),
      ).toBeVisible();
      expect(
        await page.request
          .get(root + "/budget/2026-10")
          .then((r) => r.json())
          .then((b) => b.expenses),
      ).toBe(3998);
      await noOverflow(page);
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(axe.violations).toEqual([]);
      expect(errors).toEqual([]);
    } finally {
      await second.close();
      await page.request.delete(root, { data: { name: homeName } });
    }
  });
});

test("named income sources, contributors, corrections and independent months", async ({
  page,
  browser,
}, testInfo) => {
  const unique = crypto.randomUUID();
  expect(
    (
      await page.request.post("/api/auth/register", {
        data: { name: "Roch", email: `income-${unique}@example.com`, password },
      })
    ).status(),
  ).toBe(201);
  const homeResponse = await page.request.post("/api/households", {
    data: { name: `Źródła QA ${unique}` },
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  const home = (await homeResponse.json()).id;
  const invitation = await page.request
    .post(`/api/households/${home}/invitations`)
    .then((r) => r.json());
  const second = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  expect(
    (
      await second.request.post("/api/auth/register", {
        data: {
          name: "Kaja",
          email: `income-kaja-${unique}@example.com`,
          password,
        },
      })
    ).status(),
  ).toBe(201);
  expect(
    (
      await second.request.post("/api/households/join", {
        data: { token: invitation.token },
      })
    ).status(),
  ).toBe(200);
  await second.close();
  const overview = await page.request
    .get(`/api/households/${home}/overview?month=2026-10`)
    .then((r) => r.json());
  const roch = overview.members.find(
    (m: { name: string }) => m.name === "Roch",
  ).id;
  const kaja = overview.members.find(
    (m: { name: string }) => m.name === "Kaja",
  ).id;
  await go(page, "/budzet");
  await page
    .getByLabel("Nazwa źródła 1", { exact: true })
    .fill("Wynagrodzenie");
  await page.getByLabel("Kwota źródła 1 (zł)", { exact: true }).fill("6000,01");
  await expect(
    page.getByLabel("Kto dostarcza dochód 1", { exact: true }),
  ).toHaveValue(roch);
  await page.getByRole("button", { name: "Dodaj źródło dochodu" }).click();
  await page
    .getByLabel("Nazwa źródła 2", { exact: true })
    .fill("Wynagrodzenie");
  await page
    .getByLabel("Kto dostarcza dochód 2", { exact: true })
    .selectOption(kaja);
  await page.getByLabel("Kwota źródła 2 (zł)", { exact: true }).fill("3999,99");
  await expect(page.locator(".income-total")).toContainText("10 000,00");
  await page.getByLabel("Jedzenie — plan (zł)").fill("10000");
  await expect(page.locator(".plan-feedback")).toContainText(
    "Wszystko przydzielone",
  );
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await noOverflow(page);
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.evaluate(() => {
      (document.activeElement as HTMLElement)?.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "income"}/income-edit-${testInfo.project.name}-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.locator(".income-source-summary")).toHaveCount(2);
  await expect(page.locator(".income-overview")).toContainText("Kaja");
  await page.reload();
  await expect(page.locator(".income-overview")).toContainText("6 000,01");
  await expect(page.locator(".income-overview")).toContainText("3 999,99");
  await page.getByRole("button", { name: "Edytuj plan" }).click();
  await page
    .getByLabel("Kto dostarcza dochód 2", { exact: true })
    .selectOption(roch);
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Ta osoba ma już źródło",
  );
  await expect(page.locator("main").getByRole("alert")).toBeInViewport();
  await page.screenshot({
    path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "income"}/income-error-${testInfo.project.name}.png`,
  });
  await page.getByLabel("Nazwa źródła 2", { exact: true }).fill("Zlecenia");
  await page.getByLabel("Kwota źródła 2 (zł)", { exact: true }).fill("500,05");
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.locator(".income-overview")).toContainText("Zlecenia");
  await page.getByLabel("Miesiąc budżetu").fill("2026-11");
  await expect(page.getByLabel("Kwota źródła 1 (zł)")).toHaveValue("0,00");
  await page.getByLabel("Kwota źródła 1 (zł)").fill("7000");
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.locator(".income-overview")).toContainText("7 000,00");
  await page.getByLabel("Miesiąc budżetu").fill("2026-10");
  await expect(page.locator(".income-overview")).toContainText("500,05");
  await page.getByRole("button", { name: "Edytuj plan" }).click();
  await page
    .getByRole("button", { name: "Usuń źródło 2", exact: true })
    .click();
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.locator(".income-source-summary")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".income-source-summary")).toHaveCount(1);
  await page.getByRole("button", { name: "Edytuj plan" }).click();
  await page
    .getByRole("button", { name: "Usuń źródło 1", exact: true })
    .click();
  await expect(
    page.getByText("Nie ma jeszcze źródeł dochodu.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zapisz plan" }).click();
  await expect(page.locator(".income-overview")).toContainText(
    "Dodaj źródła, gdy znasz planowane dochody.",
  );
  const budget = await page.request
    .get(`/api/households/${home}/budget/2026-10`)
    .then((r) => r.json());
  expect(budget.planned_income).toBe(0);
  expect(budget.income).toBe(0);
  await page.request.delete(`/api/households/${home}`, {
    data: { name: `Źródła QA ${unique}` },
  });
});
