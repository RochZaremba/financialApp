import { describe, expect, it, vi } from "vitest";
import {
  dateLabel,
  money,
  moneyInput,
  monthName,
  parseMoney,
  parseSignedMoney,
  shiftMonth,
  warsawDate,
} from "./money";
describe("integer-grosz boundary and Polish display", () => {
  it("parses Polish amounts without float arithmetic", () => {
    expect(parseMoney("139,75")).toBe(13975);
    expect(parseMoney("1 200,00")).toBe(120000);
    expect(parseMoney("0,01")).toBe(1);
    expect(parseMoney("49.9")).toBe(4990);
    expect(parseMoney("10")).toBe(1000);
  });
  it("rejects rounding, scientific notation, negative and unsafe values", () => {
    for (const s of ["1,999", "1e3", "-1", "NaN", "", ".5", "99999999999"])
      expect(() => parseMoney(s)).toThrow();
  });
  it("preserves every grosz in input round-trips", () => {
    for (const n of [0, 1, 11, 99, 100, 13975, 120000, 100000000000])
      expect(parseMoney(moneyInput(n))).toBe(n);
  });
  it("preserves signed account and receipt amounts without rounding", () => {
    for (const amount of [-100000000000, -101, -99, -1, 0, 1, 101])
      expect(parseSignedMoney(moneyInput(amount))).toBe(amount);
    expect(parseSignedMoney("−0,01")).toBe(-1);
    expect(money(1, false)).toBe("0,01 zł");
    expect(() => parseSignedMoney("-0,001")).toThrow();
    expect(() => parseSignedMoney("--1")).toThrow();
  });
  it("formats whole and fractional parts separately", () => {
    expect(money(13975)).toBe("139,75 zł");
    expect(money(13975, true, "EUR")).toBe("139,75 EUR");
    expect(money(-1, true, "CHF")).toBe("−0,01 CHF");
    expect(money(-1)).toBe("−0,01 zł");
    expect(money(100000, false).replace(/\s/g, " ")).toBe("1 000 zł");
  });
  it("keeps months stable across year boundaries", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(monthName("2026-10")).toBe("październik 2026");
    expect(dateLabel("2026-10-04")).toContain("4");
  });
  it("uses Warsaw date at UTC month boundaries", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-31T22:30:00Z"));
    expect(warsawDate()).toBe("2026-04-01");
    vi.useRealTimers();
  });
});
