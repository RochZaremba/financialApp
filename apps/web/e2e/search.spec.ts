import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
// eslint-disable-next-line no-empty-pattern -- Playwright fixture syntax.
test.beforeAll(async ({}) => {
  await new Promise((resolve) => setTimeout(resolve, 60_000));
});
test("search transactions by product, account, category, dates and exact amounts", async ({
  page,
}, info) => {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
  const unique = `${Date.now()}-${info.project.name}`;
  expect(
    (
      await page.request.post("/api/auth/register", {
        data: {
          name: "Szukaj QA",
          email: `search-${unique}@example.com`,
          password: "private-search-password",
        },
      })
    ).status(),
  ).toBe(201);
  const home = await page.request
    .post("/api/households", {
      data: { name: `Szukaj ${unique}` },
      headers: { "Idempotency-Key": `home-${unique}` },
    })
    .then((r) => r.json());
  const route = `/api/households/${home.id}`;
  const data = await page.request
    .get(`${route}/overview?month=2026-10`)
    .then((r) => r.json());
  for (const [index, amount] of [10001, 20002, 30003].entries()) {
    expect(
      (
        await page.request.post(`${route}/transactions`, {
          data: {
            kind: "expense",
            amount,
            date: index === 0 ? "2026-09-30" : "2026-10-02",
            description: `Zakupy ${index}`,
            account_id: data.accounts[index === 2 ? 1 : 0].id,
            allocations: [
              { category_id: data.categories[0].id, amount: amount - 1 },
              { category_id: data.categories[1].id, amount: 1 },
            ],
          },
          headers: { "Idempotency-Key": `tx-${unique}-${index}` },
        })
      ).status(),
    ).toBe(201);
  }
  await page.goto("/transakcje");
  await expect(page.locator(".transaction")).toHaveCount(2);
  await page.getByText("Dokładniejsze filtry", { exact: true }).click();
  await page.getByLabel("Okres wyszukiwania").selectOption("range");
  await page.getByLabel("Data od", { exact: true }).fill("2026-09-01");
  await page.getByLabel("Data do", { exact: true }).fill("2026-10-31");
  await page
    .getByLabel("Kategoria wyszukiwania")
    .selectOption(data.categories[1].id);
  await page.getByLabel("Konto wyszukiwania").selectOption(data.accounts[0].id);
  await page.getByLabel("Kwota transakcji od (zł)").fill("100,01");
  await page.getByLabel("Kwota transakcji do (zł)").fill("200,02");
  await page.getByLabel("Sortuj transakcje").selectOption("amount_desc");
  await page.getByRole("button", { name: "Szukaj", exact: true }).click();
  await expect(page.locator(".transaction")).toHaveCount(2);
  await expect(page.locator(".transaction").first()).toContainText("200,02");
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
    await page.getByLabel("Szukaj transakcji", { exact: true }).focus();
    await page.screenshot({
      path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "search"}/search-${info.project.name}-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize(
    info.project.use.viewport || { width: 1440, height: 900 },
  );
  await page.getByLabel("Kwota transakcji od (zł)").fill("300");
  await page.getByRole("button", { name: "Szukaj", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "nie może przekraczać",
  );
  await page
    .getByRole("button", { name: "Wyczyść filtry", exact: true })
    .click();
  await expect(page.locator(".transaction")).toHaveCount(2);
  await page.getByLabel("Szukaj transakcji", { exact: true }).fill("Zakupy 2");
  await expect(page.locator(".transaction")).toHaveCount(1);
  await expect(page.locator(".transaction")).toContainText("300,03");
  await page.request.delete(route, { data: { name: `Szukaj ${unique}` } });
});
