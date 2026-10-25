export type MeterUnit = "kWh" | "m3" | "GJ";
export type Meter = {
  id: string;
  name: string;
  unit: MeterUnit;
  interval_days: number;
  updated_at: string;
};
export type MeterPhoto = {
  id: string;
  created_at: string;
  provider: string;
  proposal: {
    value: number | null;
    confidence: number;
    unit: MeterUnit | null;
  } | null;
  diagnostics: { code?: string; message?: string; http_status?: number | null };
};
export type MeterReading = {
  id: string;
  date: string;
  value: number;
  photo_id: string | null;
  updated_at: string;
  created_by_name: string | null;
  consumption: number | null;
  days: number | null;
  average: number | null;
  from_date: string | null;
};
export type MeterDetail = {
  meter: Meter;
  readings: MeterReading[];
  photos: MeterPhoto[];
  next_due: string | null;
  overdue: boolean;
  truncated: boolean;
  today: string;
};

export function meterUnit(unit: MeterUnit) {
  return unit === "m3" ? "m³" : unit;
}
export function parseReading(text: string): number {
  const normalized = text.replace(/\s/g, "").replace(",", ".");
  if (!/^[0-9]{1,10}(?:\.[0-9]{1,3})?$/.test(normalized))
    throw new Error(
      "Wpisz stan licznika: liczbę z najwyżej trzema miejscami po przecinku.",
    );
  const [whole, fractional = ""] = normalized.split(".");
  const value = Number(whole) * 1000 + Number(fractional.padEnd(3, "0"));
  if (!Number.isSafeInteger(value) || value > 1_000_000_000_000)
    throw new Error("Stan licznika jest zbyt duży.");
  return value;
}
export function readingNumber(value: number): string {
  const fractional = String(value % 1000)
    .padStart(3, "0")
    .replace(/0+$/, "");
  return (
    new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0 }).format(
      Math.floor(value / 1000),
    ) + (fractional ? "," + fractional : "")
  );
}
export function meterDate(date: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Europe/Warsaw",
  }).format(new Date(date + "T12:00:00Z"));
}

export function averageNumber(average: number, consumption: number): string {
  return average === 0 && consumption > 0 ? "<0,001" : readingNumber(average);
}
export function meterDays(days: number): string {
  return `${days} ${days === 1 ? "dzień" : "dni"}`;
}
