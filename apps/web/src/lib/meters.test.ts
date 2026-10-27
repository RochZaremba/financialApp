import { describe, expect, it } from "vitest";
import {
  parseReading,
  readingNumber,
  averageNumber,
  warsawClock,
  readingDuration,
  activitySummary,
} from "./meters";

describe("exact utility readings", () => {
  it("formats Polish measurement clocks and distinguishes no from unknown", () => {
    expect(warsawClock(new Date("2026-01-01T23:15:00Z"))).toBe("00:15");
    expect(warsawClock(new Date("2026-07-01T18:05:00Z"))).toBe("20:05");
    expect(
      readingDuration({ elapsed_seconds: 23 * 3600 + 30 * 60, days: 1 }),
    ).toBe("23 godz. 30 min");
    expect(readingDuration({ elapsed_seconds: null, days: 1 })).toBe(
      "1 dzień (wg dat)",
    );
    expect(activitySummary({ oven: false, cooking: true })).toBe(
      "Gotowanie: tak · Piekarnik: nie",
    );
    expect(activitySummary({})).toBe("");
  });
  it("distinguishes a tiny positive daily average from actual zero usage", () => {
    expect(averageNumber(0, 1)).toBe("<0,001");
    expect(averageNumber(0, 0)).toBe("0");
    expect(averageNumber(1234, 12340)).toBe("1,234");
  });
  it("keeps zeros and decimal thousandths without float rounding", () => {
    for (const [text, value] of [
      ["0", 0],
      ["0,001", 1],
      ["12 345,678", 12345678],
      ["2.1", 2100],
      ["1000000000", 1000000000000],
    ] as const) {
      expect(parseReading(text)).toBe(value);
      expect(parseReading(readingNumber(value))).toBe(value);
    }
  });
  it("rejects ambiguous, negative, over-precision and unbounded states", () => {
    for (const text of [
      "",
      "1e3",
      "NaN",
      "-1",
      "1,2345",
      "1.234.56",
      "1000000001",
      "1,234.56",
    ])
      expect(() => parseReading(text)).toThrow();
  });
});
