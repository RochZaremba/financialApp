import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
// eslint-disable-next-line no-empty-pattern -- Playwright fixture syntax.
test.beforeAll(async ({}) => {
  await new Promise((resolve) => setTimeout(resolve, 60_000));
});
test("schedule annual and weekly payments, review reminders and confirm each occurrence once", async ({
  page,
}, info) => {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00+02:00"));
  const unique = `${Date.now()}-${info.project.name}`;
  expect(
    (
      await page.request.post("/api/auth/register", {
        data: {
          name: "Cykle QA",
          email: `cycles-${unique}@example.com`,
          password: "private-cycles-password",
        },
      })
    ).status(),
  ).toBe(201);
  const home = await page.request
    .post("/api/households", {
      data: { name: `Cykle ${unique}` },
      headers: { "Idempotency-Key": `home-${unique}` },
    })
    .then((r) => r.json());
  const route = `/api/households/${home.id}`;
  await page.goto("/cykliczne");
  await page.getByRole("button", { name: "Nowy stały wydatek" }).click();
  await page.getByLabel("Nazwa płatności").fill("Ubezpieczenie");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("123,45");
  await page.getByLabel("Jak często?").selectOption("yearly");
  await page.getByLabel("Pierwsza płatność / od kiedy").fill("2026-10-10");
  await page.getByLabel("Przypomnij wcześniej (dni)").fill("7");
  await page.getByRole("button", { name: "Zapisz płatność" }).click();
  await expect(page.locator(".reminder-panel")).toContainText("Ubezpieczenie");
  expect(
    (await page.request.get(`${route}/transactions`).then((r) => r.json()))
      .items.length,
  ).toBe(0);
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
      path: `../../artifacts/ui-review/${process.env.REVIEW_PASS || "recurring"}/reminders-${info.project.name}-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize(
    info.project.use.viewport || { width: 1440, height: 900 },
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Przypomnij w kalendarzu" }).click();
  expect((await download).suggestedFilename()).toBe("razem-platnosci.ics");
  await page
    .locator(".reminder-panel")
    .getByRole("button", { name: "Potwierdź zapłatę" })
    .click();
  await expect(page.locator(".reminder-panel")).toHaveCount(0);
  await expect(page.locator(".recurring-list")).toContainText("Opłacone");
  const recurring = (
    await page.request
      .get(`${route}/overview?month=2026-10`)
      .then((r) => r.json())
  ).recurring[0];
  expect(
    (
      await page.request.post(
        `${route}/recurring/${recurring.id}/pay/2026-10-10`,
      )
    ).status(),
  ).toBe(200);
  expect(
    (await page.request.get(`${route}/transactions`).then((r) => r.json()))
      .items.length,
  ).toBe(1);
  await page.getByRole("button", { name: "Nowy stały wydatek" }).click();
  await page.getByLabel("Nazwa płatności").fill("Zajęcia");
  await page.getByLabel("Kwota (zł)", { exact: true }).fill("10,01");
  await page.getByLabel("Jak często?").selectOption("weekly");
  await page.getByLabel("Pierwsza płatność / od kiedy").fill("2026-10-16");
  await page.getByRole("button", { name: "Zapisz płatność" }).click();
  await expect(page.locator(".recurring-list")).toContainText("Co tydzień");
  const overview = await page.request
    .get(`${route}/overview?month=2026-10`)
    .then((r) => r.json());
  expect(
    overview.recurring.filter((r: { name: string }) => r.name === "Zajęcia"),
  ).toHaveLength(3);
  await page.reload();
  await expect(page.locator(".recurring-list")).toContainText("Ubezpieczenie");
  await page.request.delete(route, { data: { name: `Cykle ${unique}` } });
});
