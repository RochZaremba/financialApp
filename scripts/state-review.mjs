import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
const dir = `artifacts/ui-review/${process.argv[2] || "states"}`;
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL: "http://localhost:3000",
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
  serviceWorkers: "block",
});
const page = await context.newPage();
const results = [];
async function capture(name, width) {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: `${dir}/${name}-${width}.png`,
    fullPage: true,
  });
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  results.push({
    name,
    width,
    overflow,
    violations: axe.violations.map((v) => v.id),
  });
  console.log(name, width, "overflow", overflow, "axe", axe.violations.length);
}
await page.goto("http://localhost:3000");
await page.getByRole("heading", { name: "Witaj z powrotem." }).waitFor();
await capture("login", 390);
await capture("login", 1440);
await page
  .getByRole("button", { name: "Pierwszy raz tutaj? Utwórz konto" })
  .click();
await capture("register", 390);
await capture("register", 1440);
await page.getByLabel("Jak masz na imię?").fill("Ala");
await page
  .getByLabel("Adres e-mail", { exact: true })
  .fill(`states-${crypto.randomUUID()}@example.com`);
await page
  .getByLabel("Hasło", { exact: true })
  .fill("private-state-review-password");
await page.getByRole("button", { name: "Utwórz konto", exact: true }).click();
await page.getByLabel("Nazwa gospodarstwa").waitFor();
await capture("onboarding", 390);
await capture("onboarding", 1440);
await page.getByLabel("Nazwa gospodarstwa").fill("Przegląd stanów QA");
await page.getByRole("button", { name: "Utwórz nasz dom" }).click();
await page.getByRole("heading", { name: "Cześć, Ala." }).waitFor();
await page.locator(".app-shell").waitFor();
const me = await page.request.get("/api/auth/me").then((r) => r.json());
const home = me.households[0].id;
for (const width of [390, 1440])
  for (const route of [
    "/",
    "/budzet",
    "/transakcje",
    "/cele",
    "/analiza",
    "/inbox",
    "/cykliczne",
    "/konta",
    "/dodaj?type=saving",
  ]) {
    await page.goto("http://localhost:3000" + route);
    await page.locator("main h1").waitFor();
    await capture(
      "empty-" +
        (route === "/" ? "home" : route.slice(1).replaceAll(/[/?=]/g, "-")),
      width,
    );
  }
await page.goto("http://localhost:3000/dodaj?type=expense");
await page.getByLabel("Kwota (zł)", { exact: true }).fill("2,345");
await page.getByLabel("Nazwa lub krótki opis").fill("Niepoprawna kwota");
await page.getByRole("button", { name: "Zapisz transakcję" }).click();
await page.locator("main [role=alert]").waitFor();
await capture("invalid-money", 390);
await context.setOffline(true);
await page.getByText("Sprawdź połączenie. Zapis może się nie udać.").waitFor();
await capture("offline-banner", 390);
await context.setOffline(false);
await page.goto("http://localhost:3000/dodaj");
await page
  .locator("input[type=file]")
  .last()
  .setInputFiles("apps/web/public/icon-192.png");
await page.getByRole("heading", { name: "Uzupełnij paragon." }).waitFor();
await capture("unread-receipt", 390);
await capture("unread-receipt", 1440);
await page.getByRole("button", { name: "Dodaj pozycję", exact: true }).click();
await page
  .getByLabel("Pozycja 1", { exact: true })
  .fill("Czytelna pozycja bez ilości");
if ((await page.getByLabel("Ilość", { exact: true }).inputValue()) !== "")
  throw new Error("Missing receipt quantity must remain empty");
await page.evaluate(() => scrollTo(0, 0));
await capture("optional-receipt-quantity", 390);
await page.evaluate(() => scrollTo(0, 0));
await capture("optional-receipt-quantity", 1440);
await page.route("**/api/households/*/overview?*", (route) =>
  route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({
      detail: "Nie możemy teraz wczytać budżetu. Spróbuj ponownie.",
    }),
  }),
);
await page.goto("http://localhost:3000");
await page
  .getByRole("heading", { name: "Nie udało się wczytać danych" })
  .waitFor();
await capture("api-error", 390);
await capture("api-error", 1440);
await page.unroute("**/api/households/*/overview?*");
await page.request.delete(`/api/households/${home}`, {
  data: { name: "Przegląd stanów QA" },
});
await fs.writeFile(`${dir}/results.json`, JSON.stringify(results, null, 2));
await browser.close();
if (results.some((r) => r.overflow || r.violations.length))
  process.exitCode = 1;
