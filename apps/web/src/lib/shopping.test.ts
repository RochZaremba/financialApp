import { describe, expect, it } from "vitest";
import { parseQuantity, quantityInput } from "./shopping";
describe("integer stock quantities", () => {
  it("preserves fractional quantities exactly through repeated consumption", () => {
    const stock =
      parseQuantity("0,3") - parseQuantity("0,1") - parseQuantity("0.1");
    expect(stock).toBe(100);
    expect(quantityInput(stock)).toBe("0,1");
    expect(parseQuantity("0.001")).toBe(1);
    expect(parseQuantity(quantityInput(1_000_000_000))).toBe(1_000_000_000);
    expect(parseQuantity("0", true)).toBe(0);
  });
  it("rejects quantities that would silently round, underflow or overflow", () => {
    for (const value of [
      "0",
      "-1",
      "1e2",
      "0.0001",
      "1000000.001",
      "NaN",
      "",
    ]) {
      expect(() => parseQuantity(value)).toThrow();
    }
  });
});
