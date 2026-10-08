"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Plus,
  Pencil,
  ArrowUpRight,
  Check,
  Download,
  Copy,
  Trash2,
  Repeat2,
  ShieldCheck,
  Users,
  LogOut,
  Landmark,
  Info,
  X,
} from "lucide-react";
import { api, json } from "@/lib/api";
import {
  dateLabel,
  money,
  moneyInput,
  monthName,
  parseMoney,
  parseSignedMoney,
} from "@/lib/money";
import type { Analytics, Goal, Recurring, Category } from "@/lib/types";
import { useApp, useCommand } from "./context";
import {
  Amount,
  Card,
  Empty,
  ErrorMessage,
  Field,
  Icon,
  MoneyField,
  Progress,
  SectionTitle,
  Select,
  Skeleton,
  Submit,
} from "./ui";
import { ReminderPanel } from "./reminder-panel";
import { PageHeading } from "./budget-screens";

export function GoalsScreen() {
  const { data } = useApp();
  const [editing, setEditing] = useState<Goal | "new" | null>(null);
  return (
    <>
      <PageHeading
        title="Wasze cele."
        description="Małe, regularne kroki zamieniają plany w rzeczywistość."
        action={
          <button className="button primary" onClick={() => setEditing("new")}>
            <Plus size={18} />
            Nowy cel
          </button>
        }
      />
      {editing && (
        <GoalForm
          key={editing === "new" ? "new" : editing.id}
          goal={editing === "new" ? undefined : editing}
          close={() => setEditing(null)}
        />
      )}
      <div className="goals-grid">
        {data.goals.map((goal) => (
          <Card className="goal-card" key={goal.id}>
            <div className="goal-card-top">
              <Icon name={goal.icon} size={26} />
              <button
                className="icon-button"
                aria-label={`Edytuj cel: ${goal.name}`}
                onClick={() => setEditing(goal)}
              >
                <Pencil size={17} />
              </button>
            </div>
            <span className="eyebrow">
              {goal.current >= goal.target
                ? "CEL OSIĄGNIĘTY"
                : "WASZ WSPÓLNY CEL"}
            </span>
            <h2>{goal.name}</h2>
            <div className="goal-amount">
              <strong>{money(goal.current, false)}</strong>
              <span> z {money(goal.target, false)}</span>
            </div>
            <Progress value={goal.current} total={goal.target} />
            <div className="goal-progress-meta">
              <span>
                {Math.min(100, Math.round((goal.current / goal.target) * 100))}%
                drogi za Wami
              </span>
              <span>
                {money(Math.max(0, goal.target - goal.current), false)} do celu
              </span>
            </div>
            <div className="goal-plan">
              <div>
                <span>Planujecie odkładać</span>
                <strong>
                  {money(goal.monthly_amount, false)}
                  <small> / miesiąc</small>
                </strong>
              </div>
              <div>
                <span>W tym tempie</span>
                <strong>
                  {goal.current >= goal.target
                    ? "Gotowe!"
                    : goal.estimated_date
                      ? monthName(goal.estimated_date.slice(0, 7))
                      : "Bez ustalonej daty"}
                </strong>
              </div>
            </div>
            <Link
              className="button secondary"
              href={`/dodaj?type=saving&goal=${goal.id}`}
            >
              <Plus size={17} />
              Odłóż na cel
            </Link>
          </Card>
        ))}
      </div>
      {!data.goals.length && !editing && (
        <Card>
          <Empty
            icon="flag"
            title="O czym marzy Wasz dom?"
            description="Wakacje, poduszka bezpieczeństwa, własne cztery kąty. Dodaj pierwszy cel przyciskiem powyżej."
          />
        </Card>
      )}
      <div className="quiet-tip">
        <Info size={18} />
        <p>
          Przewidywana data zakłada regularne wpłaty. Zmiana planu celu nie
          zmienia budżetów wcześniejszych miesięcy.
        </p>
      </div>
    </>
  );
}
function GoalForm({ goal, close }: { goal?: Goal; close: () => void }) {
  const { household } = useApp();
  const command = useCommand();
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      (key) =>
        api(
          `/households/${household}/goals${goal ? "/" + goal.id : ""}`,
          json(
            goal ? "PUT" : "POST",
            {
              name: f.get("name"),
              target: parseMoney(String(f.get("target"))),
              opening_amount: parseMoney(String(f.get("opening"))),
              monthly_amount: parseMoney(String(f.get("monthly"))),
              icon: f.get("icon"),
            },
            key,
          ),
        ),
      goal ? "Cel zaktualizowany" : "Nowy cel gotowy",
      close,
    );
  }
  return (
    <Card className="form-card">
      <div className="section-title">
        <h2>{goal ? "Edytuj Wasz cel" : "Co planujecie?"}</h2>
        <button
          className="icon-button"
          onClick={close}
          aria-label="Zamknij formularz celu"
        >
          <X size={18} />
        </button>
      </div>
      <form onSubmit={submit}>
        <Field
          label="Nazwa celu"
          name="name"
          defaultValue={goal?.name}
          placeholder="np. Nasze wakacje"
          required
          maxLength={80}
        />
        <div className="form-grid">
          <MoneyField
            label="Chcemy zebrać (zł)"
            name="target"
            defaultValue={goal ? moneyInput(goal.target) : ""}
            required
          />
          <MoneyField
            label="Już odłożone na start (zł)"
            name="opening"
            defaultValue={moneyInput(goal?.opening_amount || 0)}
            required
            hint="Bez wpłat zapisanych później w aplikacji."
          />
          <MoneyField
            label="Miesięczny plan (zł)"
            name="monthly"
            defaultValue={moneyInput(goal?.monthly_amount || 0)}
            required
          />
          <Select
            label="Symbol celu"
            name="icon"
            defaultValue={goal?.icon || "flag"}
          >
            <option value="flag">Cel</option>
            <option value="shield">Bezpieczeństwo</option>
            <option value="sun">Wakacje</option>
            <option value="house">Dom</option>
          </Select>
        </div>
        <ErrorMessage error={command.error} />
        <div className="form-actions">
          <button className="button secondary" type="button" onClick={close}>
            Anuluj
          </button>
          <Submit busy={command.busy}>Zapisz cel</Submit>
        </div>
      </form>
    </Card>
  );
}
export function AnalyticsScreen() {
  const { household, month, data } = useApp();
  const result = useQuery({
    queryKey: ["analytics", household, month],
    queryFn: () =>
      api<Analytics>(`/households/${household}/analytics?month=${month}`),
  });
  if (result.isPending) return <Skeleton />;
  if (result.isError)
    return (
      <Card>
        <ErrorMessage error={result.error.message} />
        <button className="button secondary" onClick={() => result.refetch()}>
          Spróbuj ponownie
        </button>
      </Card>
    );
  const a = result.data;
  const rows = a.budget.allocations
    .filter((x) => x.kind === "category" && x.spent > 0)
    .sort((x, y) => y.spent - x.spent);
  const max = Math.max(1, ...a.trend.map((x) => x.spent));
  return (
    <>
      <PageHeading
        title="Wasz miesiąc w liczbach."
        description="Kilka liczb, które pomagają podjąć dobre decyzje."
      />
      {a.budget.spent === 0 ? (
        <Card>
          <Empty
            icon="basket"
            title="Jeszcze za wcześnie na wnioski"
            description="Dodaj pierwsze transakcje w tym miesiącu. Wtedy pokażemy, dokąd idą pieniądze."
            action="Dodaj transakcję"
            href="/dodaj"
          />
        </Card>
      ) : (
        <>
          <div className="budget-summary analytics-summary">
            <Card>
              <span className="eyebrow">WSPÓLNE WYDATKI</span>
              <strong>{money(a.budget.expenses + a.budget.pocket)}</strong>
              <small>Zakupy i wypłacone kieszonkowe</small>
            </Card>
            <Card>
              <span className="eyebrow">ODŁOŻONE W TYM MIESIĄCU</span>
              <strong className="positive-text">
                {money(a.budget.savings)}
              </strong>
              <small>
                {a.savings_rate !== null
                  ? `${a.savings_rate}% rzeczywistych wpływów`
                  : "Dodaj wpływy, aby policzyć udział oszczędności"}
              </small>
            </Card>
            <Card>
              <span className="eyebrow">SZACUNEK NA KONIEC MIESIĄCA</span>
              <strong
                className={
                  a.forecast_remaining !== null && a.forecast_remaining < 0
                    ? "negative"
                    : ""
                }
              >
                {a.forecast === null
                  ? "Jeszcze bez prognozy"
                  : money(a.forecast)}
              </strong>
              <small>
                {a.forecast_remaining === null
                  ? "Brak dni obserwacji"
                  : a.forecast_remaining < 0
                    ? `${money(-a.forecast_remaining)} ponad plan`
                    : `${money(a.forecast_remaining)} może pozostać`}
              </small>
            </Card>
          </div>
          <div className="two-columns analytics-columns">
            <Card>
              <SectionTitle title="Na co wydajecie?" />
              {rows.length ? (
                rows.map((row) => {
                  const cat = data.categories.find(
                    (c) => c.id === row.reference_id,
                  );
                  return (
                    <div className="analysis-category" key={row.id}>
                      <div>
                        <Icon name={cat?.icon || "basket"} color={cat?.color} />
                        <strong>{row.label}</strong>
                        <Amount value={row.spent} />
                      </div>
                      <Progress
                        value={row.spent}
                        total={a.budget.expenses}
                        color={cat?.color}
                      />
                      <small>
                        {Math.round((row.spent / a.budget.expenses) * 100)}%
                        wydatków · plan {money(row.amount)}
                      </small>
                    </div>
                  );
                })
              ) : (
                <p className="muted">W tym miesiącu jeszcze bez zakupów.</p>
              )}
              {a.budget.unallocated > 0 && (
                <div className="notice warning">
                  {money(a.budget.unallocated)} jeszcze bez kategorii.
                  <Link href="/inbox">Przypisz</Link>
                </div>
              )}
            </Card>
            <Card>
              <SectionTitle title="Miesiąc po miesiącu" />
              <p className="muted small">
                Zakupy i kieszonkowe. Przelewy oraz oszczędności są liczone
                osobno.
              </p>
              <div
                className="trend-chart"
                role="list"
                aria-label="Wydatki ostatnich sześciu miesięcy"
              >
                {a.trend.map((t) => (
                  <div className="trend-column" role="listitem" key={t.month}>
                    <span className="trend-label">
                      {new Intl.DateTimeFormat("pl-PL", {
                        month: "short",
                      }).format(new Date(t.month + "-15T12:00:00"))}
                    </span>
                    <div className="trend-track" aria-hidden="true">
                      <div
                        style={{
                          width: `${Math.max(t.spent > 0 ? 3 : 0, (t.spent / max) * 100)}%`,
                        }}
                        className={t.month === month ? "current" : ""}
                      />
                    </div>
                    <span className="trend-value">{money(t.spent, false)}</span>
                  </div>
                ))}
              </div>
              <div className="chart-legend">
                <i />
                Wydatki rzeczywiste
              </div>
            </Card>
          </div>
          <Card className="forecast-note">
            <Info size={20} />
            <div>
              <h3>Prognoza to wskazówka, nie obietnica.</h3>
              <p>
                Szacujemy wydatki zmienne według tempa z {a.elapsed_days}{" "}
                {a.elapsed_days === 1 ? "dnia" : "dni"}. Dodajemy opłacone i
                oczekujące stałe płatności ({money(a.outstanding_recurring)})
                oraz dotychczasowe kieszonkowe i oszczędności. Przy kilku dniach
                danych wynik może się mocno zmieniać.
              </p>
            </div>
          </Card>
          <Card>
            <SectionTitle title="Plan i rzeczywistość" />
            {a.budget.allocations.map((row) => (
              <div className="plan-actual-row" key={row.id}>
                <strong>{row.label}</strong>
                <span>
                  Plan <b>{money(row.amount)}</b>
                </span>
                <span>
                  Wykorzystano{" "}
                  <b className={row.spent > row.amount ? "negative" : ""}>
                    {money(row.spent)}
                  </b>
                </span>
              </div>
            ))}
          </Card>
        </>
      )}
    </>
  );
}
export function AccountsScreen() {
  const { data, household } = useApp();
  const [adding, setAdding] = useState(false);
  const [currency, setCurrency] = useState("PLN");
  const command = useCommand();
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      (key) =>
        api(
          `/households/${household}/accounts`,
          json(
            "POST",
            {
              name: f.get("name"),
              kind: f.get("kind"),
              currency: f.get("currency"),
              opening_balance: parseSignedMoney(String(f.get("opening"))),
            },
            key,
          ),
        ),
      "Konto dodane",
      () => setAdding(false),
    );
  }
  return (
    <>
      <PageHeading
        title="Wasze konta."
        description="Salda na podstawie zapisanych wpływów i transakcji."
        action={
          <button
            className="button secondary"
            onClick={() => setAdding(!adding)}
          >
            <Plus size={18} />
            Dodaj konto
          </button>
        }
      />
      <Card className="accounts-total">
        <span className="eyebrow">RAZEM NA WASZYCH KONTACH</span>
        <strong>
          {data.account_valuation.total_pln === null
            ? "Brak aktualnej wyceny"
            : money(data.account_valuation.total_pln)}
        </strong>
        {data.accounts.some((a) => a.currency !== "PLN") ? (
          <p
            role={
              data.account_valuation.status !== "current" ? "status" : undefined
            }
          >
            {data.account_valuation.status === "unavailable"
              ? "Nie udało się pobrać kursów NBP. Pełna suma będzie dostępna po ponownym połączeniu."
              : `Wycena według kursów średnich NBP z ${data.account_valuation.rate_date}.${data.account_valuation.status === "cached" ? " Nie udało się odświeżyć kursów — pokazujemy ostatnie pobrane." : ""}`}
          </p>
        ) : (
          <p>Przelewy między Waszymi kontami nie zmieniają wspólnego salda.</p>
        )}
      </Card>
      {adding && (
        <Card className="form-card">
          <h2>Nowe konto</h2>
          <form onSubmit={submit}>
            <Field
              name="name"
              label="Nazwa konta"
              required
              maxLength={80}
              placeholder="np. Wspólne oszczędności"
            />
            <div className="form-grid">
              <Select name="kind" label="Rodzaj">
                <option value="checking">Konto bieżące</option>
                <option value="cash">Gotówka</option>
                <option value="savings">Oszczędności</option>
              </Select>
              <Select
                name="currency"
                label="Waluta"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
              >
                <option value="PLN">PLN — złoty</option>
                <option value="EUR">EUR — euro</option>
                <option value="USD">USD — dolar amerykański</option>
                <option value="GBP">GBP — funt brytyjski</option>
                <option value="CHF">CHF — frank szwajcarski</option>
              </Select>
              <MoneyField
                label={`Saldo na start (${currency === "PLN" ? "zł" : currency})`}
                name="opening"
                defaultValue="0,00"
                required
                hint="Saldo sprzed zapisanych transakcji. Może być ujemne, np. −50,00."
              />
            </div>
            {currency !== "PLN" && (
              <p className="muted small">
                Saldo przeliczymy na złote w podsumowaniu. Transakcje budżetu
                zapisujecie na kontach PLN.
              </p>
            )}
            <ErrorMessage error={command.error} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setAdding(false)}
              >
                Anuluj
              </button>
              <Submit busy={command.busy}>Dodaj konto</Submit>
            </div>
          </form>
        </Card>
      )}
      <div className="accounts-grid">
        {data.accounts.map((a) => (
          <Card className="account-card" key={a.id}>
            <Icon
              name={a.kind === "cash" ? "pocket" : "account"}
              color={a.kind === "savings" ? "green" : "gray"}
              size={24}
            />
            <span className="eyebrow">
              {a.kind === "savings"
                ? "NA PRZYSZŁOŚĆ"
                : a.kind === "cash"
                  ? "POD RĘKĄ"
                  : "NA CODZIENNOŚĆ"}
            </span>
            <h2>{a.name}</h2>
            <strong>{money(a.balance, true, a.currency)}</strong>
            {a.currency !== "PLN" && (
              <p className="muted small">
                {a.balance_pln === null
                  ? "Wycena PLN niedostępna"
                  : `≈ ${money(a.balance_pln)} · 1 ${a.currency} = ${a.exchange_rate?.replace(".", ",")} zł`}
              </p>
            )}
            {a.currency === "PLN" && (
              <Link href="/dodaj?type=transfer" className="text-button">
                Zrób przelew
                <ArrowUpRight size={17} />
              </Link>
            )}
          </Card>
        ))}
      </div>
      <div className="quiet-tip">
        <Landmark size={18} />
        <p>
          Konta prowadzicie samodzielnie. Salda nie są pobierane z banku. Konto
          osobiste po wypłacie kieszonkowego nie należy do wspólnego budżetu.
        </p>
      </div>
    </>
  );
}
export function RecurringScreen() {
  const { data, household } = useApp();
  const [editing, setEditing] = useState<Recurring | "new" | null>(null);
  const command = useCommand();
  const rows = data.recurring.filter((r) => r.active && r.scheduled);
  const total = rows.reduce((s, r) => s + r.amount, 0);
  const remaining = rows
    .filter((r) => !r.paid)
    .reduce((s, r) => s + r.amount, 0);
  async function pay(row: Recurring) {
    await command.run(
      () =>
        api(
          `/households/${household}/recurring/${row.id}/pay/${row.due_date}`,
          {
            method: "POST",
          },
        ),
      "Płatność zapisana",
    );
  }
  async function toggle(row: Recurring) {
    await command.run(
      () =>
        api(
          `/households/${household}/recurring/${row.id}`,
          json("PUT", {
            name: row.name,
            amount: row.amount,
            day: row.day,
            frequency: row.frequency,
            start_date: row.start_date,
            reminder_days: row.reminder_days,
            category_id: row.category_id,
            account_id: row.account_id,
            active: !row.active,
          }),
        ),
      row.active ? "Stały wydatek wyłączony" : "Stały wydatek włączony",
    );
  }
  return (
    <>
      <PageHeading
        title="Stałe wydatki."
        description="Powtarzalne płatności czekają na Wasze potwierdzenie. Nie zapisujemy ich automatycznie."
        action={
          <button className="button primary" onClick={() => setEditing("new")}>
            <Plus size={18} />
            Nowy stały wydatek
          </button>
        }
      />
      <div className="form-actions">
        <button
          type="button"
          className="button secondary"
          disabled={command.busy || !data.recurring.some((r) => r.active)}
          onClick={() =>
            command.run(async () => {
              const response = await fetch(
                `/api/households/${household}/recurring/calendar`,
                { credentials: "same-origin" },
              );
              if (!response.ok)
                throw new Error(
                  "Nie udało się pobrać kalendarza. Spróbuj ponownie.",
                );
              const url = URL.createObjectURL(await response.blob());
              const link = document.createElement("a");
              link.href = url;
              link.download = "razem-platnosci.ics";
              link.click();
              setTimeout(() => URL.revokeObjectURL(url), 1000);
            }, "Kalendarz pobrany")
          }
        >
          {" "}
          <Download size={17} />
          Przypomnij w kalendarzu
        </button>
      </div>
      <p className="muted small">
        Zaimportuj pobrany plik do kalendarza telefonu. Zawiera terminy i alarmy
        na najbliższy rok; po zmianie harmonogramu pobierz go ponownie.
      </p>
      <ReminderPanel />
      <div className="budget-summary two">
        <Card>
          <span className="eyebrow">PŁATNOŚCI W TYM MIESIĄCU</span>
          <strong>{money(total)}</strong>
        </Card>
        <Card>
          <span className="eyebrow">JESZCZE DO OPŁACENIA</span>
          <strong>{money(remaining)}</strong>
          <small>W wybranym miesiącu</small>
        </Card>
      </div>
      {editing && (
        <RecurringForm
          key={editing === "new" ? "new" : editing.id}
          row={editing === "new" ? undefined : editing}
          close={() => setEditing(null)}
        />
      )}
      <ErrorMessage error={command.error} />
      <Card className="recurring-list">
        {data.recurring.length ? (
          data.recurring
            .slice()
            .sort((a, b) => a.due_date.localeCompare(b.due_date))
            .map((row) => (
              <div
                className={`recurring-row ${row.active ? "" : "inactive"}`}
                key={`${row.id}:${row.due_date}`}
              >
                <span className="date-tile">
                  <small>{dateLabel(row.due_date).split(" ")[1]}</small>
                  <strong>{dateLabel(row.due_date).split(" ")[0]}</strong>
                </span>
                <div className="recurring-name">
                  <strong>{row.name}</strong>
                  <small>
                    {
                      data.categories.find((c) => c.id === row.category_id)
                        ?.name
                    }{" "}
                    · {data.accounts.find((a) => a.id === row.account_id)?.name}
                    ·{" "}
                    {
                      {
                        weekly: "Co tydzień",
                        monthly: "Co miesiąc",
                        quarterly: "Co kwartał",
                        yearly: "Co rok",
                      }[row.frequency]
                    }
                  </small>
                </div>
                <Amount value={row.amount} />
                <div className="recurring-actions">
                  {!row.scheduled && row.active ? (
                    <span className="pill neutral">Nie w tym miesiącu</span>
                  ) : row.paid ? (
                    <span className="pill positive">
                      <Check size={14} />
                      Opłacone
                    </span>
                  ) : row.active ? (
                    <button
                      className="button secondary"
                      onClick={() => pay(row)}
                      disabled={command.busy}
                    >
                      <Check size={15} />
                      Opłacone
                    </button>
                  ) : (
                    <span className="pill neutral">Wyłączone</span>
                  )}
                  <button
                    className="icon-button"
                    aria-label={`Edytuj stały wydatek: ${row.name}`}
                    onClick={() => setEditing(row)}
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`${row.active ? "Wyłącz" : "Włącz"}: ${row.name}`}
                    onClick={() => toggle(row)}
                    disabled={command.busy}
                  >
                    <Repeat2 size={16} />
                  </button>
                </div>
              </div>
            ))
        ) : (
          <Empty
            icon="account"
            title="Stałe płatności w jednym miejscu"
            description="Dodaj czynsz, internet, ubezpieczenie lub inne powtarzalne opłaty."
          />
        )}
      </Card>
      <div className="quiet-tip">
        <ShieldCheck size={18} />
        <p>
          Każdy termin potwierdzasz raz. Ponowne kliknięcie nie utworzy
          kolejnego wydatku. Gdy miesiąc jest krótszy, płatność wypada w jego
          ostatnim dniu.
        </p>
      </div>
    </>
  );
}
function RecurringForm({ row, close }: { row?: Recurring; close: () => void }) {
  const { household, data, month } = useApp();
  const [frequency, setFrequency] = useState(row?.frequency || "monthly");
  const command = useCommand();
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      (key) =>
        api(
          `/households/${household}/recurring${row ? "/" + row.id : ""}`,
          json(
            row ? "PUT" : "POST",
            {
              name: f.get("name"),
              amount: parseMoney(String(f.get("amount"))),
              day:
                frequency === "monthly"
                  ? Number(f.get("day"))
                  : Number(String(f.get("start_date")).slice(8, 10)),
              frequency,
              start_date: f.get("start_date") || null,
              reminder_days: Number(f.get("reminder_days")),
              category_id: f.get("category"),
              account_id: f.get("account"),
              active: row?.active ?? true,
            },
            key,
          ),
        ),
      "Stały wydatek zapisany",
      close,
    );
  }
  return (
    <Card className="form-card">
      <div className="section-title">
        <h2>{row ? "Edytuj stały wydatek" : "Powtarzalna płatność"}</h2>
        <button
          className="icon-button"
          aria-label="Zamknij formularz"
          onClick={close}
        >
          <X size={18} />
        </button>
      </div>
      <form onSubmit={submit}>
        <Field
          name="name"
          label="Nazwa płatności"
          defaultValue={row?.name}
          placeholder="np. Internet"
          required
          maxLength={120}
        />
        <div className="form-grid">
          <MoneyField
            name="amount"
            label="Kwota (zł)"
            defaultValue={row ? moneyInput(row.amount) : ""}
            required
          />
          {frequency === "monthly" && (
            <Field
              name="day"
              label="Dzień miesiąca"
              type="number"
              min={1}
              max={31}
              defaultValue={row?.day || 1}
              required
            />
          )}
          <Select
            label="Jak często?"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value as typeof frequency)}
          >
            <option value="weekly">Co tydzień</option>
            <option value="monthly">Co miesiąc</option>
            <option value="quarterly">Co kwartał</option>
            <option value="yearly">Co rok</option>
          </Select>
          <Field
            name="start_date"
            label="Pierwsza płatność / od kiedy"
            type="date"
            min="2000-01-01"
            max="2100-12-31"
            defaultValue={row?.start_date || (row ? "" : `${month}-01`)}
            required={frequency !== "monthly"}
          />
          <Field
            name="reminder_days"
            label="Przypomnij wcześniej (dni)"
            type="number"
            min={0}
            max={30}
            defaultValue={row?.reminder_days ?? 3}
            required
          />
          <Select
            name="category"
            label="Kategoria"
            defaultValue={row?.category_id}
            required
          >
            {data.categories
              .filter((c) => !c.archived)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </Select>
          <Select
            name="account"
            label="Konto"
            defaultValue={row?.account_id}
            required
          >
            {data.accounts
              .filter((a) => a.currency === "PLN")
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
          </Select>
        </div>
        <ErrorMessage error={command.error} />
        <div className="form-actions">
          <button className="button secondary" type="button" onClick={close}>
            Anuluj
          </button>
          <Submit busy={command.busy}>Zapisz płatność</Submit>
        </div>
      </form>
    </Card>
  );
}
export function SettingsScreen({ logout }: { logout: () => void }) {
  const { data, household, me, notify } = useApp();
  const command = useCommand();
  const [invitation, setInvitation] = useState("");
  const [category, setCategory] = useState<Category | "new" | null>(null);
  const [archive, setArchive] = useState("");
  const [deleting, setDeleting] = useState(false);
  const owner = me.households.find((h) => h.id === household)?.role === "owner";
  async function invite() {
    await command.run(
      () =>
        api<{ token: string }>(`/households/${household}/invitations`, {
          method: "POST",
        }),
      "Zaproszenie jest gotowe",
      (r) => setInvitation(`${window.location.origin}/dolacz?token=${r.token}`),
    );
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(invitation);
      notify("Link skopiowany");
    } catch {
      command.setError("Skopiuj link ręcznie z pola poniżej.");
    }
  }
  async function exportData() {
    await command.run(async () => {
      const exported = await api(`/households/${household}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(exported, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `razem-${household}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }, "Eksport pobrany");
  }
  async function remove(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      () =>
        api(
          `/households/${household}`,
          json("DELETE", { name: f.get("name") }),
        ),
      "Gospodarstwo usunięte",
    );
  }
  return (
    <>
      <PageHeading
        title="Wasz dom i ustawienia."
        description="Osoby, koperty i dane. Wszystko w jednym miejscu."
      />
      <ErrorMessage error={command.error} />
      <div className="settings-grid">
        <Card>
          <div className="section-title">
            <h2>Nasz dom</h2>
            <Users size={20} />
          </div>
          <p className="household-name">{data.household.name}</p>
          {data.members.map((m) => (
            <div className="member-row" key={m.id}>
              <span className={`avatar ${m.name === "Kaja" ? "peach" : ""}`}>
                {m.name.slice(0, 1)}
              </span>
              <div>
                <strong>{m.name}</strong>
                <small>
                  {m.role === "owner" ? "Właściciel domu" : "Domownik"}
                </small>
              </div>
              {m.user_id === me.user.id && (
                <span className="pill neutral">Ty</span>
              )}
            </div>
          ))}
          {owner && (
            <button
              className="button secondary"
              onClick={invite}
              disabled={command.busy}
            >
              <Plus size={17} />
              Zaproś do wspólnego budżetu
            </button>
          )}
          {invitation && (
            <div className="invitation">
              <Field
                label="Link zaproszenia (ważny 7 dni)"
                value={invitation}
                readOnly
                onFocus={(e) => e.target.select()}
              />
              <button className="button secondary" onClick={copy}>
                <Copy size={16} />
                Kopiuj link
              </button>
              <small>
                Przekaż link drugiej osobie. Zaproszenie można wykorzystać raz.
              </small>
            </div>
          )}
        </Card>
        <Card>
          <SectionTitle title="Twoje konto" />
          <div className="profile-info">
            <span className="avatar large">{me.user.name.slice(0, 1)}</span>
            <strong>{me.user.name}</strong>
            <span>{me.user.email}</span>
          </div>
          <p className="muted small">
            PLN · język polski · strefa Europe/Warsaw
          </p>
          <button className="button secondary" onClick={logout}>
            <LogOut size={16} />
            Wyloguj się
          </button>
        </Card>
      </div>
      {category && (
        <CategoryForm
          key={category === "new" ? "new" : category.id}
          category={category === "new" ? undefined : category}
          close={() => setCategory(null)}
        />
      )}
      <Card className="categories-settings">
        <div className="section-title">
          <h2>Wasze kategorie</h2>
          <button
            className="button secondary"
            onClick={() => setCategory("new")}
          >
            <Plus size={17} />
            Dodaj kategorię
          </button>
        </div>
        <p className="muted small">
          Nazwy w zapisanych miesięcznych planach zostają bez zmian.
          Archiwizacja zachowuje historię zakupów.
        </p>
        {data.categories
          .filter((c) => !c.archived)
          .map((c) => (
            <div key={c.id}>
              <div className="category-setting-row">
                <Icon name={c.icon} color={c.color} />
                <div>
                  <strong>{c.name}</strong>
                  <small>{c.group}</small>
                </div>
                <button
                  className="icon-button"
                  aria-label={`Edytuj kategorię: ${c.name}`}
                  onClick={() => setCategory(c)}
                >
                  <Pencil size={16} />
                </button>
                <button
                  className="icon-button"
                  aria-label={`Archiwizuj kategorię: ${c.name}`}
                  onClick={() => setArchive(archive === c.id ? "" : c.id)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {archive === c.id && (
                <div className="notice warning">
                  <span>
                    Kategoria zostanie w historii. Nie użyjesz jej do nowych
                    zakupów.
                  </span>
                  <button
                    className="button secondary"
                    disabled={command.busy}
                    onClick={() =>
                      command.run(
                        () =>
                          api(`/households/${household}/categories/${c.id}`, {
                            method: "DELETE",
                          }),
                        "Kategoria zarchiwizowana",
                        () => setArchive(""),
                      )
                    }
                  >
                    Archiwizuj
                  </button>
                  <button
                    className="text-button"
                    onClick={() => setArchive("")}
                  >
                    Anuluj
                  </button>
                </div>
              )}
            </div>
          ))}
      </Card>
      <Card>
        <SectionTitle title="Zapamiętane przypisania" />
        <p className="muted small">
          Tylko Wasze reguły. Kolejne zakupy z tą samą nazwą trafią do wybranej
          kategorii.
        </p>
        {data.rules.length ? (
          data.rules.map((rule) => (
            <div className="rule-row" key={rule.id}>
              <div>
                <strong>{rule.pattern}</strong>
                <small>
                  {data.categories.find((c) => c.id === rule.category_id)?.name}
                </small>
              </div>
              <button
                className="icon-button"
                aria-label={`Zapomnij przypisanie: ${rule.pattern}`}
                disabled={command.busy}
                onClick={() =>
                  command.run(
                    () =>
                      api(`/households/${household}/rules/${rule.id}`, {
                        method: "DELETE",
                      }),
                    "Przypisanie usunięte",
                  )
                }
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))
        ) : (
          <p className="muted">
            Pierwszą regułę zapamiętamy, gdy poprawisz kategorię na paragonie.
          </p>
        )}
      </Card>
      <Card className="privacy-card">
        <Icon name="shield" />
        <div>
          <h2>Wasze dane należą do Was.</h2>
          <p>
            Wyeksportuj dane gospodarstwa w JSON. Kwoty są zapisane w groszach.
            Zdjęcia paragonów pobierzesz z ich szczegółów.
          </p>
        </div>
        <button
          className="button secondary"
          onClick={exportData}
          disabled={command.busy}
        >
          <Download size={17} />
          Pobierz dane
        </button>
      </Card>
      {owner && (
        <Card className="danger-zone">
          <h2>Usunięcie gospodarstwa</h2>
          <p>
            Trwale usuniemy wspólny budżet, historię, cele, reguły i zdjęcia.
            Konta użytkowników pozostaną.
          </p>
          <button
            className="button danger-outline"
            onClick={() => setDeleting(!deleting)}
          >
            <Trash2 size={16} />
            Usuń gospodarstwo
          </button>
          {deleting && (
            <form onSubmit={remove}>
              <Field
                name="name"
                label={`Wpisz nazwę: ${data.household.name}`}
                required
                autoComplete="off"
              />
              <div className="form-actions">
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setDeleting(false)}
                >
                  Anuluj
                </button>
                <button
                  className="button danger-button"
                  disabled={command.busy}
                >
                  Usuń bezpowrotnie
                </button>
              </div>
            </form>
          )}
        </Card>
      )}
    </>
  );
}
function CategoryForm({
  category,
  close,
}: {
  category?: Category;
  close: () => void;
}) {
  const { household } = useApp();
  const command = useCommand();
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      (key) =>
        api(
          `/households/${household}/categories${category ? "/" + category.id : ""}`,
          json(
            category ? "PATCH" : "POST",
            {
              name: f.get("name"),
              group: f.get("group"),
              icon: f.get("icon"),
              color: f.get("color"),
            },
            key,
          ),
        ),
      category ? "Kategoria zaktualizowana" : "Kategoria dodana",
      close,
    );
  }
  return (
    <Card className="form-card">
      <div className="section-title">
        <h2>{category ? "Edytuj kategorię" : "Nowa koperta"}</h2>
        <button
          className="icon-button"
          aria-label="Zamknij formularz"
          onClick={close}
        >
          <X size={18} />
        </button>
      </div>
      <form onSubmit={submit}>
        <Field
          label="Nazwa kategorii"
          name="name"
          defaultValue={category?.name}
          required
          maxLength={80}
        />
        <div className="form-grid">
          <Select
            label="Grupa"
            name="group"
            defaultValue={category?.group || "Potrzeby"}
          >
            <option>Potrzeby</option>
            <option>Na co dzień</option>
          </Select>
          <Select
            label="Symbol"
            name="icon"
            defaultValue={category?.icon || "basket"}
          >
            <option value="basket">Zakupy</option>
            <option value="house">Dom</option>
            <option value="zap">Rachunki</option>
            <option value="car">Transport</option>
            <option value="coffee">Przyjemności</option>
            <option value="shopping">Inne zakupy</option>
          </Select>
          <Select
            label="Kolor"
            name="color"
            defaultValue={category?.color || "green"}
          >
            <option value="green">Zielony</option>
            <option value="blue">Niebieski</option>
            <option value="amber">Bursztynowy</option>
            <option value="purple">Fioletowy</option>
          </Select>
        </div>
        <ErrorMessage error={command.error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={close}>
            Anuluj
          </button>
          <Submit busy={command.busy}>Zapisz kategorię</Submit>
        </div>
      </form>
    </Card>
  );
}
