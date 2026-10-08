import { expect, test, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const password = "extensions-private-password";
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
});
// A fresh limiter window separates these QA households from the original suite.
// eslint-disable-next-line no-empty-pattern -- Playwright requires destructuring.
test.beforeAll(async ({}, testInfo) => {
  if (testInfo.project.name !== "desktop")
    await new Promise((resolve) => setTimeout(resolve, 60_000));
});
async function household(page: Page, testInfo: TestInfo) {
  const unique = `${Date.now()}-${testInfo.project.name}`;
  expect(
    (
      await page.request.post("/api/auth/register", {
        data: {
          name: "Plan QA",
          email: `plan-${unique}@example.com`,
          password,
        },
      })
    ).status(),
  ).toBe(201);
  const response = await page.request.post("/api/households", {
    data: { name: `Plan ${unique}` },
    headers: { "Idempotency-Key": `home-${unique}` },
  });
  expect(response.status()).toBe(201);
  const home = (await response.json()).id;
  const route = `/api/households/${home}`;
  const data = await page.request
    .get(`${route}/overview?month=2026-10`)
    .then((r) => r.json());
  return { home, route, data, name: `Plan ${unique}` };
}
async function review(page: Page, label: string, testInfo: TestInfo) {
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
    await page.screenshot({
      path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "extensions"}/${label}-${testInfo.project.name}-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize(
    testInfo.project.use.viewport || { width: 1440, height: 900 },
  );
}

test("copy a monthly plan into a reviewed draft without duplicating transactions", async ({
  page,
}, testInfo) => {
  const { route, data, name } = await household(page, testInfo);
  const source = {
    income_sources: [
      { name: "Pensja", member_id: data.members[0].id, amount: 123456 },
    ],
    allocations: [
      { kind: "category", reference_id: data.categories[0].id, amount: 103456 },
      { kind: "pocket", reference_id: data.members[0].id, amount: 20000 },
    ],
  };
  expect(
    (
      await page.request.put(`${route}/budget/2026-09`, { data: source })
    ).status(),
  ).toBe(200);
  await page.goto("/budzet");
  await expect(
    page.getByLabel("Kwota źródła 1 (zł)", { exact: true }),
  ).toHaveValue("0,00");
  await page.getByText("Skopiuj plan innego miesiąca", { exact: true }).click();
  await page.getByRole("button", { name: "Pokaż plan do skopiowania" }).click();
  await expect(page.locator(".copy-preview")).toContainText("1 234,56");
  await expect(
    page.getByLabel("Kwota źródła 1 (zł)", { exact: true }),
  ).toHaveValue("0,00");
  expect(
    (await page.request.get(`${route}/budget/2026-10`).then((r) => r.json()))
      .period,
  ).toBeNull();
  await expect(page.locator(".sticky-actions")).toHaveCount(0);
  await review(page, "copy-preview", testInfo);
  await page
    .getByRole("button", { name: "Zastosuj do szkicu", exact: true })
    .click();
  await expect(
    page.getByLabel("Kwota źródła 1 (zł)", { exact: true }),
  ).toHaveValue("1234,56");
  await expect(
    page.getByLabel(`${data.categories[0].name} — plan (zł)`, { exact: true }),
  ).toHaveValue("1034,56");
  await page.getByRole("button", { name: "Zapisz plan", exact: true }).click();
  await expect(page.locator(".income-overview")).toContainText("Pensja");
  await page.reload();
  const target = await page.request
    .get(`${route}/budget/2026-10`)
    .then((r) => r.json());
  expect(target.planned_income).toBe(123456);
  expect(target.unassigned).toBe(0);
  expect(target.income).toBe(0);
  expect(
    (await page.request.get(`${route}/transactions`).then((r) => r.json()))
      .items,
  ).toEqual([]);
  expect(
    (await page.request.get(`${route}/budget/2026-09`).then((r) => r.json()))
      .planned_income,
  ).toBe(123456);
  await page.getByRole("button", { name: "Edytuj plan", exact: true }).click();
  await page.getByText("Skopiuj plan innego miesiąca", { exact: true }).click();
  await page.getByLabel("Miesiąc do skopiowania").fill("2026-08");
  await page.getByRole("button", { name: "Pokaż plan do skopiowania" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "nie ma jeszcze planu",
  );
  await page.request.delete(route, { data: { name } });
});

test("review a complete budget proposal and apply it only to the draft", async ({
  page,
}, info) => {
  const { route, data, name } = await household(page, info);
  await page.goto("/budzet");
  await page.getByLabel("Kwota źródła 1 (zł)", { exact: true }).fill("1000,01");
  await page.getByLabel(`${data.members[0].name} — plan (zł)`).fill("200");
  await page.getByText("Pomóż mi rozdzielić budżet", { exact: true }).click();
  await page
    .getByRole("button", { name: "Na podstawie historii", exact: true })
    .click();
  await expect(page.locator(".budget-proposal")).toContainText("800,01");
  await expect(page.locator(".proposal-row")).toHaveCount(
    data.categories.length,
  );
  expect(
    (await page.request.get(`${route}/budget/2026-10`).then((r) => r.json()))
      .period,
  ).toBeNull();
  await review(page, "budget-proposal", info);
  await page
    .getByRole("button", { name: "Zastosuj propozycję do szkicu" })
    .click();
  await expect(
    page.getByLabel(`${data.members[0].name} — plan (zł)`),
  ).toHaveValue("200");
  await page.getByRole("button", { name: "Zapisz plan", exact: true }).click();
  await expect(page.getByRole("button", { name: "Edytuj plan" })).toBeVisible();
  const saved = await page.request
    .get(`${route}/budget/2026-10`)
    .then((r) => r.json());
  expect(saved.unassigned).toBe(0);
  expect(saved.planned_income).toBe(100001);
  expect(
    (await page.request.get(`${route}/transactions`).then((r) => r.json()))
      .items.length,
  ).toBe(0);
  await page.request.delete(route, { data: { name } });
});
