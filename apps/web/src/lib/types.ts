export type User = { id: string; name: string; email: string };
export type Household = {
  id: string;
  name: string;
  member_id: string;
  role: string;
};
export type Me = {
  user: User;
  households: Household[];
  receipt_provider: string;
  receipt_ai_available: boolean;
  budget_ai_available: boolean;
  thresholds: { auto: number; review: number };
};
export type Category = {
  id: string;
  name: string;
  group: string;
  icon: string;
  color: string;
  archived: boolean;
};
export type Member = {
  id: string;
  name: string;
  user_id: string;
  role: string;
};
export type Account = {
  currency: "PLN" | "EUR" | "USD" | "GBP" | "CHF";
  balance_pln: number | null;
  exchange_rate: string | null;
  id: string;
  name: string;
  kind: string;
  opening_balance: number;
  balance: number;
};
export type Goal = {
  id: string;
  name: string;
  target: number;
  opening_amount: number;
  current: number;
  monthly_amount: number;
  icon: string;
  estimated_date: string | null;
};
export type Allocation = {
  id: string;
  kind: "category" | "pocket" | "goal";
  reference_id: string;
  label: string;
  group: string;
  amount: number;
  spent: number;
  remaining: number;
  carry_in?: number;
  reserved_out?: number;
};
export type IncomeSource = {
  id: string;
  name: string;
  member_id: string | null;
  amount: number;
};
export type Budget = {
  available: number;
  carry_in: number;
  carry_out: number;
  distributed_out: number;
  settlement: import("@/components/surplus").Settlement | null;
  period: { id: string; updated_at: string } | null;
  month: string;
  planned_income: number;
  income_sources: IncomeSource[];
  assigned: number;
  unassigned: number;
  spent: number;
  expenses: number;
  pocket: number;
  savings: number;
  income: number;
  remaining: number;
  unallocated: number;
  allocations: Allocation[];
};
export type Split = { category_id: string; amount: number };
export type Transaction = {
  updated_at: string;
  id: string;
  kind: string;
  amount: number;
  date: string;
  description: string;
  status: string;
  account_id: string;
  destination_id: string | null;
  member_id: string | null;
  goal_id: string | null;
  source: string;
  source_id: string | null;
  allocations: Split[];
};
export type Task = {
  id: string;
  kind: string;
  title: string;
  receipt_id: string | null;
  transaction_id: string | null;
  resolved: boolean;
};
export type Recurring = {
  frequency: "weekly" | "monthly" | "quarterly" | "yearly";
  start_date: string | null;
  reminder_days: number;
  scheduled: boolean;
  reminder_status: "overdue" | "upcoming" | "later" | null;
  id: string;
  name: string;
  amount: number;
  day: number;
  category_id: string;
  account_id: string;
  active: boolean;
  paid: boolean;
  due_date: string;
};
export type Rule = {
  id: string;
  pattern: string;
  category_id: string;
  kind: string;
};
export type Overview = {
  household: Household;
  members: Member[];
  categories: Category[];
  budget: Budget;
  accounts: Account[];
  account_valuation: {
    total_pln: number | null;
    rate_date: string | null;
    status: "current" | "cached" | "unavailable";
  };
  goals: Goal[];
  tasks: Task[];
  recent: Transaction[];
  recurring: Recurring[];
  reminders: Recurring[];
  rules: Rule[];
};
export type ReceiptItem = {
  id?: string;
  name: string;
  quantity: string;
  amount: number | null;
  category_id: string | null;
  confidence: number;
  reviewed: boolean;
};
export type Receipt = {
  id: string;
  merchant: string;
  date: string | null;
  total: number | null;
  status: string;
  provider: string;
  error: string | null;
  transaction_id: string | null;
  items: ReceiptItem[];
};
export type Analytics = {
  budget: Budget;
  forecast: number | null;
  forecast_remaining: number | null;
  elapsed_days: number;
  days_in_month: number;
  outstanding_recurring: number;
  recurring_actual: number;
  savings_rate: number | null;
  trend: {
    month: string;
    planned: number;
    spent: number;
    savings: number;
    income: number;
  }[];
};

export type BudgetCopyPreview = {
  source_month: string;
  planned_income: number;
  income_sources: Omit<IncomeSource, "id">[];
  allocations: Pick<Allocation, "kind" | "reference_id" | "amount" | "label">[];
  omitted: string[];
};
