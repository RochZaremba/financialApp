export type StockUnit = "szt" | "kg" | "g" | "l" | "ml" | "opak";
export type StockLocation = "fridge" | "freezer" | "pantry" | "cupboard";
export const locations: Record<StockLocation, string> = {
  fridge: "Lodówka",
  freezer: "Zamrażarka",
  pantry: "Spiżarnia",
  cupboard: "Szafka domowa",
};
export const units: Record<StockUnit, string> = {
  szt: "szt.",
  kg: "kg",
  g: "g",
  l: "l",
  ml: "ml",
  opak: "opak.",
};
export function parseQuantity(value: string, allowZero = false): number {
  const clean = value.trim();
  if (!/^\d{1,7}([,.]\d{1,3})?$/.test(clean))
    throw new Error(
      "Podaj ilość, np. 2 lub 0,5. Maksymalnie trzy miejsca po przecinku.",
    );
  const [whole, fraction = ""] = clean.replace(",", ".").split(".");
  const quantity = Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
  if (quantity > 1_000_000_000 || (!allowZero && quantity === 0))
    throw new Error(
      "Ilość musi być większa od zera i nie większa niż 1 000 000.",
    );
  return quantity;
}
export function quantityInput(value: number): string {
  const fraction = String(value % 1000)
    .padStart(3, "0")
    .replace(/0+$/, "");
  return `${Math.trunc(value / 1000)}${fraction ? "," + fraction : ""}`;
}
export function quantityLabel(value: number, unit: StockUnit): string {
  return `${quantityInput(value)} ${units[unit]}`;
}
export interface Product {
  name: string;
  quantity: number;
  unit: StockUnit;
  location: StockLocation;
}
export interface StockItem extends Product {
  id: string;
  updated_at: string;
  minimum: number;
  expires_on: string | null;
}
export interface ShoppingItem extends Product {
  id: string;
  updated_at: string;
  category_id: string | null;
  estimated_amount: number | null;
  actual_amount: number | null;
  purchased_on: string | null;
  merchant: string;
  receipt_item_id: string | null;
  inventory_id: string | null;
}
export interface ShoppingOverview {
  items: ShoppingItem[];
  stock: StockItem[];
  suggestions: Product[];
  estimated_total: number;
  unpriced_count: number;
  expiring_count: number;
  today: string;
}
export interface PurchaseHistory {
  items: ShoppingItem[];
  total: number;
}
export interface ShoppingReceipt {
  id: string;
  merchant: string;
  date: string;
  items: {
    id: string;
    name: string;
    quantity: string;
    amount: number;
    imported: boolean;
  }[];
}
