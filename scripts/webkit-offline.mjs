// Real network outage: avoids Playwright's documented WebKit setOffline/SW bug #42775.
import http from "node:http";
import fs from "node:fs/promises";
import { webkit } from "@playwright/test";
const proxy = http.createServer((request, response) => {
  const headers = { ...request.headers, host: "localhost:3000" };
  if (headers.origin) headers.origin = "http://localhost:3000";
  const upstream = http.request(
    "http://127.0.0.1:3000" + request.url,
    { method: request.method, headers },
    (result) => {
      response.writeHead(result.statusCode, result.headers);
      result.pipe(response);
    },
  );
  upstream.on("error", () => {
    if (!response.headersSent) response.writeHead(502);
    response.end();
  });
  request.pipe(upstream);
});
await new Promise((resolve) => proxy.listen(3210, "127.0.0.1", resolve));
const browser = await webkit.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
  });
  await page.goto("http://127.0.0.1:3210");
  await page.getByRole("button", { name: "Zobacz wersję demo" }).click();
  await page.getByRole("heading", { name: "Cześć, Roch." }).waitFor();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
  proxy.closeAllConnections();
  await new Promise((resolve) => proxy.close(resolve));
  const response = await page.goto("http://127.0.0.1:3210/network-is-now-down");
  await page.getByRole("heading", { name: "Wrócimy za chwilę." }).waitFor();
  console.log(
    "ACTUAL_ORIGIN_OFFLINE",
    response.status(),
    "FROM_SERVICE_WORKER",
    response.fromServiceWorker(),
  );
  if (response.status() !== 200 || !response.fromServiceWorker())
    process.exitCode = 1;
  await fs.mkdir("artifacts/ui-review", { recursive: true });
  await page.screenshot({
    path: "artifacts/ui-review/webkit-real-offline.png",
    fullPage: true,
  });
} finally {
  await browser.close();
  proxy.closeAllConnections();
  if (proxy.listening) await new Promise((resolve) => proxy.close(resolve));
}
