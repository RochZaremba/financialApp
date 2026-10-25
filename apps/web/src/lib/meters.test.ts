import { describe, expect, it } from "vitest";
import { parseReading, readingNumber, averageNumber } from "./meters";

describe("exact utility readings", () => {
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
