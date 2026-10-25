import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { chromium, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pass = process.argv[2] || "1";
const directory = `artifacts/ui-review/mcp-${pass}`;
await fs.mkdir(directory, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
});
const errors = [];
try {
  const context = await browser.newContext({
    baseURL: "http://localhost:3000",
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    serviceWorkers: "block",
  });
  const password = process.env.ADMIN_REVIEW_USER_PASSWORD;
  assert.equal(
    (
      await context.request.post("/api/auth/register", {
        data: { name: "MCP", email: `mcp-${pass}@example.com`, password },
      })
    ).status(),
    201,
  );
  const home = await context.request
    .post("/api/households", {
      data: { name: `Dom MCP ${pass}` },
      headers: { "Idempotency-Key": `mcp-home-${pass}` },
    })
    .then((r) => r.json());
  const page = await context.newPage();
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/ustawienia");
  const panel = page.locator(".connections-panel");
  await expect(
    panel.getByText("Nie masz jeszcze połączeń z AI w tym domu."),
  ).toBeVisible();
  const checks = [];
  async function inspect(state) {
    for (const [width, height] of [
      [390, 844],
      [430, 932],
      [768, 1024],
      [1440, 900],
    ]) {
      await page.setViewportSize({ width, height });
      await panel.scrollIntoViewIfNeeded();
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
        `overflow ${state} ${width}`,
      );
      const results = await new AxeBuilder({ page })
        .include(".connections-panel")
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      assert.deepEqual(
        results.violations.map((v) => ({
          id: v.id,
          targets: v.nodes.map((n) => n.target),
        })),
        [],
        `axe ${state} ${width}`,
      );
      await panel.screenshot({
        path: `${directory}/${state}-${width}.png`,
        mask: [panel.getByLabel("Nowy klucz połączenia AI")],
      });
      checks.push({ state, width, overflow: false, axe: 0 });
    }
  }
  await inspect("empty");
  await panel
    .getByRole("button", { name: "Dodaj połączenie AI", exact: true })
    .click();
  await expect(panel.getByLabel("Dostęp AI")).toHaveValue("read");
  await inspect("form");
  await panel.getByLabel("Nazwa połączenia", { exact: true }).fill("Mój Codex");
  await panel.getByLabel("Dostęp AI").selectOption("write");
  await panel.getByLabel("Potwierdź swoim hasłem").fill("wrong-password");
  await panel
    .getByRole("button", { name: "Utwórz klucz AI", exact: true })
    .click();
  await expect(panel.getByText("Nieprawidłowe hasło konta.")).toBeVisible();
  await inspect("password-error");
  await panel.getByLabel("Potwierdź swoim hasłem").fill(password);
  await panel
    .getByRole("button", { name: "Utwórz klucz AI", exact: true })
    .click();
  const secret = panel.getByLabel("Nowy klucz połączenia AI");
  await expect(secret).toBeVisible();
  const token = await secret.inputValue();
  assert.match(token, /^razem_mcp_/);
  await panel
    .getByRole("button", { name: "Kopiuj klucz", exact: true })
    .click();
  assert.equal(
    await page
      .evaluate(() => navigator.clipboard.readText())
      .then((value) => value === token),
    true,
  );
  await inspect("created-masked");
  const sdk = spawnSync(".venv/bin/python", ["scripts/mcp-client-review.py"], {
    env: { ...process.env, MCP_REVIEW_TOKEN: token },
    encoding: "utf8",
    timeout: 60000,
  });
  // Only synthetic QA credentials exist here; redact them before diagnostics.
  if (sdk.status !== 0)
    console.error(sdk.stderr.replaceAll(token, "[REDACTED]"));
  assert.equal(sdk.status, 0, "Official MCP SDK roundtrip failed");
  console.log(sdk.stdout.trim());
  await panel.getByRole("button", { name: "Zapisane, ukryj klucz" }).click();
  await expect(secret).toHaveCount(0);
  await page.reload();
  await expect(
    panel.getByRole("button", { name: "Odłącz Mój Codex", exact: true }),
  ).toBeVisible();
  assert.equal(await panel.getByLabel("Nowy klucz połączenia AI").count(), 0);
  await panel
    .getByRole("button", { name: "Odłącz Mój Codex", exact: true })
    .click();
  await inspect("disconnect-confirmation");
  await panel
    .getByRole("button", { name: "Odłącz połączenie", exact: true })
    .click();
  await expect(panel.getByText(/Odczyt i zapis · Odłączone/)).toBeVisible();
  const denied = await context.request.post("/api/mcp", {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json, text/event-stream",
    },
    data: { jsonrpc: "2.0", id: 1, method: "tools/list" },
  });
  assert.equal(denied.status(), 401);
  await inspect("disconnected");
  assert.deepEqual(errors, []);
  await fs.writeFile(
    `${directory}/results.json`,
    JSON.stringify(
      { checks, errors, sdk: "passed", revocation: "passed" },
      null,
      2,
    ),
  );
  console.log(
    `MCP loop ${pass}: ${checks.length} viewport/accessibility checks passed`,
  );
} finally {
  await browser.close();
}
