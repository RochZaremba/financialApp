import { expect, test, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
// eslint-disable-next-line no-empty-pattern -- Playwright fixture syntax.
test.beforeAll(async ({}) => {
  await new Promise((resolve) => setTimeout(resolve, 60_000));
});
async function setup(page: Page, info: TestInfo, suffix: string) {
  const unique = `${Date.now()}-${info.project.name}-${suffix}`;
  expect(
    (
      await page.request.post("/api/auth/register", {
        data: {
          email: `surplus-${unique}@example.com`,
          name: "Nadwyżka QA",
          password: "private-surplus-password",
        },
      })
    ).status(),
  ).toBe(201);
  const home = await page.request
    .post("/api/households", {
      data: { name: `Nadwyżka ${unique}` },
      headers: { "Idempotency-Key": `home-${unique}` },
    })
    .then((r) => r.json());
  const route = `/api/households/${home.id}`;
  const data = await page.request
    .get(`${route}/overview?month=2026-10`)
    .then((r) => r.json());
  expect(
    (
      await page.request.put(`${route}/budget/2026-09`, {
        data: {
          planned_income: 100001,
          allocations: [
            {
              kind: "category",
              reference_id: data.categories[0].id,
              amount: 100001,
            },
          ],
        },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await page.request.post(`${route}/transactions`, {
        data: {
          kind: "income",
          date: "2026-09-01",
          amount: 100001,
          description: "Wpływ",
          account_id: data.accounts[0].id,
        },
        headers: { "Idempotency-Key": `income-${unique}` },
      })
    ).status(),
  ).toBe(201);
  return { route, data, name: `Nadwyżka ${unique}` };
}
async function review(page: Page, info: TestInfo, label: string) {
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
    await page.getByLabel("Co zrobić z nadwyżką?").focus();
    await page.screenshot({
      path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "surplus"}/${label}-${info.project.name}-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize(
    info.project.use.viewport || { width: 1440, height: 900 },
  );
}
test("carry envelope balances into next month without creating income", async ({
  page,
}, info) => {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
  const { route, name } = await setup(page, info, "carry");
  await page.goto("/budzet");
  await page.getByRole("button", { name: "Poprzedni miesiąc" }).click();
  await page.getByText("Rozlicz nadwyżkę miesiąca", { exact: true }).click();
  await page.getByRole("button", { name: "Pokaż podział nadwyżki" }).click();
  await expect(page.locator(".surplus-preview")).toContainText("1 000,01");
  expect(
    (await page.request.get(`${route}/budget/2026-10`).then((r) => r.json()))
      .period,
  ).toBeNull();
  await review(page, info, "carry-preview");
  await page
    .getByRole("button", { name: "Zamknij miesiąc i zapisz rozliczenie" })
    .click();
  await expect(page.locator(".settlement-summary")).toContainText(
    "Miesiąc rozliczony",
  );
  await expect(page.getByRole("button", { name: "Edytuj plan" })).toHaveCount(
    0,
  );
  await page.goto("/");
  await expect(page.locator("main")).toContainText("Do kolejnego miesiąca:");
  await page.goto("/budzet");
  await page.getByRole("button", { name: "Następny miesiąc" }).click();
  await expect(page.locator("main")).toContainText("z poprzedniego miesiąca");
  const budget = await page.request
    .get(`${route}/budget/2026-10`)
    .then((r) => r.json());
  expect(budget.carry_in).toBe(100001);
  expect(budget.income).toBe(0);
  expect(budget.planned_income).toBe(0);
  expect(
    (await page.request.get(`${route}/transactions`).then((r) => r.json()))
      .items,
  ).toHaveLength(1);
  await page.reload();
  await expect(page.locator("main")).toContainText("z poprzedniego miesiąca");
  await page.request.delete(route, { data: { name } });
});
test("distribute surplus using exact ratios and confirm performed transfers", async ({
  page,
}, info) => {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
  const { route, name } = await setup(page, info, "split");
  const accounts = [];
  for (const label of ["Poduszka", "Wakacje"]) {
    accounts.push(
      await page.request
        .post(`${route}/accounts`, {
          data: { name: label, kind: "savings" },
          headers: { "Idempotency-Key": `account-${Date.now()}-${label}` },
        })
        .then((r) => r.json()),
    );
  }
  const goal = await page.request
    .post(`${route}/goals`, {
      data: { name: "Wakacje", target: 1000000 },
      headers: { "Idempotency-Key": `goal-${Date.now()}` },
    })
    .then((r) => r.json());
  await page.goto("/budzet");
  await page.getByRole("button", { name: "Poprzedni miesiąc" }).click();
  await page.getByText("Rozlicz nadwyżkę miesiąca", { exact: true }).click();
  await page.getByLabel("Co zrobić z nadwyżką?").selectOption("distribute");
  await page.getByLabel("Konto oszczędnościowe 1").selectOption(accounts[0].id);
  await page.getByLabel("Udział nadwyżki 1 (%)").fill("70");
  await page.getByRole("button", { name: "Dodaj udział nadwyżki" }).click();
  await page.getByLabel("Konto oszczędnościowe 2").selectOption(accounts[1].id);
  await page.getByLabel("Cel nadwyżki 2").selectOption(goal.id);
  await page.getByLabel("Udział nadwyżki 2 (%)").fill("30");
  await page.getByRole("button", { name: "Pokaż podział nadwyżki" }).click();
  await expect(page.locator(".surplus-preview")).toContainText("700,01");
  await expect(page.locator(".surplus-preview")).toContainText("300,00");
  await expect(
    page.getByRole("button", { name: "Zamknij miesiąc i zapisz rozliczenie" }),
  ).toBeDisabled();
  await review(page, info, "distribution-preview");
  await page.getByLabel("Przelewy zostały wykonane").check();
  await page
    .getByRole("button", { name: "Zamknij miesiąc i zapisz rozliczenie" })
    .click();
  await expect(page.locator(".settlement-summary")).toContainText("Odłożono");
  const data = await page.request
    .get(`${route}/overview?month=2026-10`)
    .then((r) => r.json());
  expect(data.goals[0].current).toBe(30000);
  expect(data.budget.income).toBe(0);
  expect(data.budget.spent).toBe(0);
  const policy = await page.request
    .get(`${route}/surplus-policy`)
    .then((r) => r.json());
  expect(
    policy.targets.map((row: { basis_points: number }) => row.basis_points),
  ).toEqual([7000, 3000]);
  expect(
    (await page.request.get(`${route}/transactions`).then((r) => r.json()))
      .items,
  ).toHaveLength(3);
  await page.request.delete(route, { data: { name } });
});
