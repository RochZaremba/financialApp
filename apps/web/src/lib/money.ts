export function parseMoney(value: string): number {
  const clean = value.trim().replace(/[\s\u00a0\u202f]/g, "");
  if (!/^\d{1,10}([,.]\d{1,2})?$/.test(clean))
    throw new Error(
      "Podaj kwotę, np. 49,90. Maksymalnie dwa miejsca po przecinku.",
    );
  const [whole, fraction = ""] = clean.replace(",", ".").split(".");
  const amount = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(amount) || amount > 100_000_000_000)
    throw new Error("Kwota jest za duża.");
  return amount;
}
export function parseSignedMoney(value: string): number {
  const clean = value.trim().replace(/^−/, "-");
  return clean.startsWith("-")
    ? -parseMoney(clean.slice(1))
    : parseMoney(clean);
}
export function moneyInput(amount: number): string {
  return `${amount < 0 ? "-" : ""}${Math.trunc(Math.abs(amount) / 100)},${String(Math.abs(amount % 100)).padStart(2, "0")}`;
}
export function money(amount: number, decimals = true): string {
  const sign = amount < 0 ? "−" : "";
  const whole = new Intl.NumberFormat("pl-PL", {
    useGrouping: "always",
  }).format(Math.trunc(Math.abs(amount) / 100));
  const fraction = String(Math.abs(amount) % 100).padStart(2, "0");
  return `${sign}${whole}${decimals || Math.abs(amount) % 100 !== 0 ? "," + fraction : ""} zł`;
}
export function warsawDate(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Warsaw",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function monthName(month: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    month: "long",
    year: "numeric",
    timeZone: "Europe/Warsaw",
  }).format(new Date(`${month}-15T12:00:00+01:00`));
}
export function dateLabel(date: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    day: "numeric",
    month: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(date.slice(0, 10) + "T12:00:00+01:00"));
}
export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + m - 1 + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}
