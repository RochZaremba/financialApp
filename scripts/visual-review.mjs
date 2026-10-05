import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
const base = process.env.BASE_URL || "http://localhost:3000";
const pass = process.argv[2] || "review";
const dir = `artifacts/ui-review/${pass}`;
await fs.mkdir(dir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  locale: "pl-PL",
  timezoneId: "Europe/Warsaw",
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.setViewportSize({ width: 1440, height: 900 });
await page.goto(base);
await page.getByRole("heading", { name: "Witaj z powrotem." }).waitFor();
await page.screenshot({ path: `${dir}/login-desktop.png`, fullPage: true });
await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
await page.getByRole("heading", { name: "Cześć, Roch." }).waitFor();
const overview = await page.evaluate(async () => {
  const me = await fetch("/api/auth/me").then((r) => r.json());
  const home = me.households[0].id;
  return fetch(`/api/households/${home}/overview?month=2026-10`).then((r) =>
    r.json(),
  );
});
const receipt = overview.tasks.find((t) => t.receipt_id)?.receipt_id;
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
  ...(receipt ? [`/paragony/${receipt}`] : []),
];
const results = [];
for (const viewport of [
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]) {
  await page.setViewportSize(viewport);
  for (const route of routes) {
    await page.goto(base + route);
    await page.locator("main h1").waitFor();
    await page.evaluate(() => document.fonts.ready);
    const filename =
      route === "/"
        ? "home"
        : route.startsWith("/paragony/")
          ? "receipt"
          : route.slice(1).replaceAll(/[/?=]/g, "-");
    await page.screenshot({
      path: `${dir}/${filename}-${viewport.width}.png`,
      fullPage: true,
    });
    const overflow = await page.evaluate(() => ({
      width: innerWidth,
      scroll: document.documentElement.scrollWidth,
      offenders: [...document.querySelectorAll("main *")]
        .filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
        .map((e) => ({
          tag: e.tagName,
          class: e.className,
          text: e.textContent?.slice(0, 60),
        }))
        .slice(0, 10),
    }));
    const brokenAmounts = await page
      .locator(".trend-value")
      .evaluateAll((nodes) =>
        nodes
          .filter((node) => {
            const range = document.createRange();
            range.selectNodeContents(node);
            const rects = [...range.getClientRects()];
            const row = node.closest(".trend-column").getBoundingClientRect();
            return (
              rects.length !== 1 ||
              rects.some(
                (r) => r.left < row.left - 1 || r.right > row.right + 1,
              )
            );
          })
          .map((node) => node.textContent),
      );
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    results.push({
      route,
      viewport,
      overflow,
      brokenAmounts,
      violations: axe.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
    });
    console.log(
      viewport.width,
      route,
      "overflow:",
      overflow.scroll > overflow.width,
      "axe:",
      axe.violations.map((v) => v.id).join(","),
    );
  }
}
await fs.writeFile(
  `${dir}/results.json`,
  JSON.stringify({ errors, results }, null, 2),
);
await browser.close();
if (
  errors.length ||
  results.some(
    (r) =>
      r.overflow.scroll > r.overflow.width ||
      r.violations.length ||
      r.brokenAmounts.length,
  )
)
  process.exitCode = 1;
