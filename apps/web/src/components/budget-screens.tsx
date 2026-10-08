"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Plus,
  ScanLine,
  Check,
  Pencil,
  ChevronDown,
  Search,
  ArrowUpRight,
  Inbox,
  Flag,
  ChartNoAxesCombined,
  Landmark,
  Settings,
  Repeat2,
  CircleCheck,
  Trash2,
} from "lucide-react";
import { api, json } from "@/lib/api";
import {
  dateLabel,
  money,
  moneyInput,
  monthName,
  parseMoney,
} from "@/lib/money";
import type { Allocation, Overview, Transaction } from "@/lib/types";
import { useApp, useCommand } from "./context";
import {
  Amount,
  Card,
  Empty,
  ErrorMessage,
  Icon,
  MoneyField,
  Field,
  Progress,
  SectionTitle,
  Select,
  Submit,
  Skeleton,
} from "./ui";

import { ManualTransaction, type MovementKind } from "./movement-form";
import { MonthCopy } from "./month-copy";

function pendingText(count: number) {
  if (count === 1) return "1 sprawa czeka";
  const few =
    count % 10 >= 2 &&
    count % 10 <= 4 &&
    !(count % 100 >= 12 && count % 100 <= 14);
  return `${count} ${few ? "sprawy czekają" : "spraw czeka"}`;
}

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
function Envelope({ a, data }: { a: Allocation; data: Overview }) {
  const category = data.categories.find((c) => c.id === a.reference_id);
  return (
    <div className="envelope">
      <Icon
        name={
          a.kind === "pocket"
            ? "pocket"
            : a.kind === "goal"
              ? "flag"
              : category?.icon || "basket"
        }
        color={category?.color}
      />
      <div className="envelope-info">
        <div className="envelope-label">
          <strong>{a.label}</strong>
          <span className={a.remaining < 0 ? "negative" : ""}>
            {a.remaining < 0 ? "Ponad plan: " : "Zostało "}
            {money(Math.abs(a.remaining))}
          </span>
        </div>
        <Progress value={a.spent} total={a.amount} color={category?.color} />
        <div className="envelope-meta">
          <span>{money(a.spent)} wykorzystane</span>
          <span>z {money(a.amount)}</span>
        </div>
      </div>
    </div>
  );
}
export function Home() {
  const { data, me, month } = useApp();
  const b = data.budget;
  const review = data.tasks.length;
  const categories = b.allocations.filter((a) => a.kind === "category");
  const pocket = b.allocations.filter((a) => a.kind === "pocket");
  const next =
    data.reminders[0] ||
    data.recurring
      .filter((r) => r.active && r.scheduled && !r.paid)
      .sort((a, b) => a.due_date.localeCompare(b.due_date))[0];
  return (
    <>
      <PageHeading
        title={`Cześć, ${me.user.name}.`}
        description="Dobrze wiedzieć, na czym stoicie."
        action={
          <Link className="button primary desktop-add" href="/dodaj">
            <Plus size={19} />
            Dodaj
          </Link>
        }
      />
      {!b.period ? (
        <Card>
          <Empty
            icon="pocket"
            title="Dobry miesiąc zaczyna się od planu"
            description="Wpisz wspólny dochód i daj każdemu złotemu swoje miejsce."
            action="Zaplanuj miesiąc"
            href="/budzet"
          />
        </Card>
      ) : (
        <div className="dashboard-hero">
          <Card className="balance-card">
            <div className="balance-top">
              <span className="eyebrow">POZOSTAŁO W TYM MIESIĄCU</span>
              <span
                className={`pill ${b.planned_income > 0 && b.unassigned === 0 ? "positive" : b.unassigned < 0 ? "warning" : "neutral"}`}
              >
                {b.planned_income > 0 && b.unassigned === 0 ? (
                  <>
                    <Check size={13} />
                    Plan gotowy
                  </>
                ) : b.unassigned < 0 ? (
                  "Plan przekracza dochód"
                ) : b.planned_income === 0 ? (
                  "Uzupełnij dochód"
                ) : (
                  <>Do podziału {money(b.unassigned, false)}</>
                )}
              </span>
            </div>
            <div
              className={`balance-number ${b.remaining < 0 ? "negative" : ""}`}
            >
              {money(b.remaining)}
              <span>na Wasz wspólny plan</span>
            </div>
            <Progress value={b.spent} total={b.planned_income} />
            <div className="balance-stats">
              <div>
                <span>Wykorzystano</span>
                <strong>{money(b.spent)}</strong>
              </div>
              <div>
                <span>Zaplanowano</span>
                <strong>{money(b.planned_income)}</strong>
              </div>
              <span className="balance-percent">
                {b.planned_income
                  ? Math.round((b.spent / b.planned_income) * 100)
                  : 0}
                % planu
              </span>
            </div>
            <div className="balance-footnote">
              W tym {money(b.savings, false)} odłożone i{" "}
              {money(b.pocket, false)} kieszonkowego.
            </div>
          </Card>
          <Card className="scan-card">
            <div className="receipt-illustration" aria-hidden="true">
              <div>
                <ScanLine size={25} />
                <i />
                <i />
                <i />
                <span>139,75 zł</span>
              </div>
              <span className="receipt-check">
                <Check size={14} />
              </span>
            </div>
            <h2>Zakupy? Wystarczy zdjęcie.</h2>
            <p>
              Dodaj paragon. Podzielimy go na kategorie, a Ty sprawdzisz tylko
              niepewne pozycje.
            </p>
            <Link className="text-button" href="/dodaj">
              Zeskanuj paragon
              <ArrowRight size={17} />
            </Link>
          </Card>
        </div>
      )}
      {b.unallocated > 0 && (
        <div className="notice warning">
          <Inbox size={18} />
          <span>
            {money(b.unallocated)} wydatków czeka na kategorię. Są już
            uwzględnione w pozostałym budżecie.
          </span>
          <Link href="/inbox">
            Sprawdź
            <ArrowRight size={16} />
          </Link>
        </div>
      )}
      <div className="dashboard-columns">
        <div>
          <Card className="envelopes-card">
            <SectionTitle
              title="Wasze koperty"
              href="/budzet"
              action="Cały budżet"
            />
            {categories.length ? (
              categories
                .slice(0, 5)
                .map((a) => <Envelope key={a.id} a={a} data={data} />)
            ) : (
              <Empty
                icon="basket"
                title="Miejsce na Wasze priorytety"
                description="Dodaj pierwsze kwoty do kategorii w budżecie."
                action="Otwórz budżet"
                href="/budzet"
              />
            )}
          </Card>
          <Card className="recent-card">
            <SectionTitle
              title="Ostatnio w Waszym domu"
              href="/transakcje"
              action="Historia"
            />
            {data.recent.length ? (
              <TransactionRows transactions={data.recent} />
            ) : (
              <Empty
                title="Jeszcze bez transakcji"
                description="Pierwszy wydatek lub wpływ pojawi się tutaj."
                action="Dodaj transakcję"
                href="/dodaj"
              />
            )}
          </Card>
        </div>
        <div className="dashboard-aside">
          <Link
            href="/inbox"
            className={`review-card ${review ? "has-review" : ""}`}
          >
            <span className="review-icon">
              <Inbox size={23} />
            </span>
            <div>
              <strong>
                {review ? pendingText(review) : "Wszystko sprawdzone"}
              </strong>
              <p>
                {review
                  ? "Chwila uwagi i plan znów będzie aktualny."
                  : "Możecie spokojnie iść dalej."}
              </p>
            </div>
            <ArrowRight size={19} />
          </Link>
          <Card className="pocket-card">
            <SectionTitle title="Coś dla siebie" />
            <p className="muted small">
              Kieszonkowe jest Wasze. Bez rozliczania prywatnych zakupów.
            </p>
            {pocket.length ? (
              pocket.map((a) => (
                <div className="pocket-row" key={a.id}>
                  <span
                    className={`avatar ${a.label === "Kaja" ? "peach" : ""}`}
                  >
                    {a.label.slice(0, 1)}
                  </span>
                  <div>
                    <strong>{a.label}</strong>
                    <small>
                      {a.spent >= a.amount && a.amount > 0 ? (
                        <span className="positive-text">
                          <Check size={12} />
                          Wypłacone
                        </span>
                      ) : (
                        "Zaplanowane"
                      )}
                    </small>
                  </div>
                  <Amount value={a.amount} />
                  {a.spent < a.amount && (
                    <Link
                      href={`/dodaj?type=pocket&member=${a.reference_id}`}
                      className="icon-button"
                      aria-label={`Wypłać kieszonkowe: ${a.label}`}
                    >
                      <ArrowUpRight size={17} />
                    </Link>
                  )}
                </div>
              ))
            ) : (
              <Link className="text-button" href="/budzet">
                Zaplanuj kieszonkowe
                <ArrowRight size={16} />
              </Link>
            )}
          </Card>
          {data.goals[0] && (
            <Card className="goal-preview">
              <div className="goal-preview-header">
                <Icon name={data.goals[0].icon} />
                <Link
                  href="/cele"
                  aria-label="Zobacz cele"
                  className="icon-button"
                >
                  <ArrowUpRight size={18} />
                </Link>
              </div>
              <span className="eyebrow">MAŁE KROKI, DUŻY CEL</span>
              <h3>{data.goals[0].name}</h3>
              <div>
                <strong>{money(data.goals[0].current, false)}</strong>
                <span> z {money(data.goals[0].target, false)}</span>
              </div>
              <Progress
                value={data.goals[0].current}
                total={data.goals[0].target}
              />
              <p>
                {data.goals[0].monthly_amount
                  ? `${money(data.goals[0].monthly_amount, false)} miesięcznie bliżej celu.`
                  : "Każda wpłata przybliża Was do celu."}
              </p>
            </Card>
          )}
          {next && (
            <div className="quiet-insight">
              <Repeat2 size={19} />
              <div>
                <strong>
                  {next.reminder_status === "overdue"
                    ? "Płatność czeka na potwierdzenie"
                    : "Najbliższy stały wydatek"}
                </strong>
                <p>
                  {next.name} · {dateLabel(next.due_date)}
                  <br />
                  {money(next.amount)}
                </p>
                <Link href="/cykliczne">
                  Zobacz plan płatności
                  <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          )}
          <div className="month-note">
            <CircleCheck size={15} />
            <span>{monthName(month)} · Wasz wspólny plan</span>
          </div>
        </div>
      </div>
    </>
  );
}
export function BudgetScreen() {
  const { data, month } = useApp();
  const [editing, setEditing] = useState(false);
  const b = data.budget;
  return (
    <>
      <PageHeading
        title="Wasz plan na miesiąc."
        description="Na to, co potrzebne. Na przyjemności. Na przyszłość."
        action={
          b.period && !editing ? (
            <button
              className="button secondary"
              onClick={() => setEditing(true)}
            >
              <Pencil size={17} />
              Edytuj plan
            </button>
          ) : undefined
        }
      />
      {editing || !b.period ? (
        <BudgetEditor key={month} close={() => setEditing(false)} />
      ) : (
        <>
          <div className="budget-summary">
            <Card>
              <span className="eyebrow">PLANOWANY DOCHÓD</span>
              <strong>{money(b.planned_income)}</strong>
              <small>Wspólna pula na ten miesiąc</small>
            </Card>
            <Card
              className={
                b.planned_income > 0 && b.unassigned === 0 ? "zero-card" : ""
              }
            >
              <span className="eyebrow">
                {b.unassigned < 0
                  ? "PLAN PRZEKRACZA DOCHÓD"
                  : "DO PRZYDZIELENIA"}
              </span>
              <strong className={b.unassigned < 0 ? "negative" : ""}>
                {money(b.unassigned)}
              </strong>
              <small>
                {b.planned_income > 0 && b.unassigned === 0 ? (
                  <>
                    <Check size={14} />
                    Wszystko ma swoje miejsce
                  </>
                ) : b.planned_income === 0 ? (
                  "Dodaj źródła dochodu"
                ) : (
                  "Dostosuj kwoty w planie"
                )}
              </small>
            </Card>
            <Card>
              <span className="eyebrow">WPŁYNĘŁO NA KONTA</span>
              <strong>{money(b.income)}</strong>
              <small>Rzeczywisty dochód tego miesiąca</small>
            </Card>
          </div>
          <Card className="income-overview">
            <SectionTitle title="Źródła dochodu" />
            {b.income_sources.length ? (
              b.income_sources.map((source) => (
                <div className="income-source-summary" key={source.id}>
                  <div>
                    <strong>{source.name}</strong>
                    <small>
                      {data.members.find((m) => m.id === source.member_id)
                        ?.name || "Wspólny dochód"}
                    </small>
                  </div>
                  <Amount value={source.amount} />
                </div>
              ))
            ) : (
              <p className="muted">
                Dodaj źródła, gdy znasz planowane dochody.
              </p>
            )}
          </Card>
          {b.unallocated > 0 && (
            <div className="notice warning">
              <Inbox size={18} />
              {money(b.unallocated)} czeka na kategorię.
              <Link href="/inbox">Przypisz</Link>
            </div>
          )}
          {["Potrzeby", "Na co dzień", "Kieszonkowe", "Przyszłość"].map(
            (group) => {
              const allocations = b.allocations.filter(
                (a) => a.group === group,
              );
              return allocations.length ? (
                <Card className="budget-group" key={group}>
                  <SectionTitle title={group} />
                  {group === "Kieszonkowe" && (
                    <p className="muted small">
                      Po wypłacie pieniądze są prywatne. Nie potrzebujemy ich
                      paragonów.
                    </p>
                  )}
                  <div className="budget-table-head">
                    <span>Koperta</span>
                    <span>Plan</span>
                    <span>Wykorzystano</span>
                    <span>Pozostało</span>
                  </div>
                  {allocations.map((a) => {
                    const category = data.categories.find(
                      (c) => c.id === a.reference_id,
                    );
                    return (
                      <div className="budget-row" key={a.id}>
                        <div className="budget-label">
                          <Icon
                            name={
                              a.kind === "pocket"
                                ? "pocket"
                                : a.kind === "goal"
                                  ? "flag"
                                  : category?.icon || "basket"
                            }
                            color={category?.color}
                          />
                          <div>
                            <strong>{a.label}</strong>
                            <Progress
                              value={a.spent}
                              total={a.amount}
                              color={category?.color}
                            />
                          </div>
                        </div>
                        <div>
                          <small>Plan</small>
                          <Amount value={a.amount} />
                        </div>
                        <div>
                          <small>Wykorzystano</small>
                          <Amount value={a.spent} />
                        </div>
                        <div>
                          <small>Pozostało</small>
                          <Amount
                            value={a.remaining}
                            className={
                              a.remaining < 0 ? "negative" : "positive-text"
                            }
                          />
                          {a.kind === "pocket" && a.spent < a.amount && (
                            <Link
                              href={`/dodaj?type=pocket&member=${a.reference_id}`}
                              className="small-link"
                            >
                              Wypłać
                              <ArrowUpRight size={13} />
                            </Link>
                          )}
                          {a.kind === "goal" && a.spent < a.amount && (
                            <Link
                              href={`/dodaj?type=saving&goal=${a.reference_id}`}
                              className="small-link"
                            >
                              Odłóż
                              <ArrowUpRight size={13} />
                            </Link>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </Card>
              ) : null;
            },
          )}
        </>
      )}
    </>
  );
}
function BudgetEditor({ close }: { close: () => void }) {
  const { data, household, month, me } = useApp();
  const command = useCommand();
  const b = data.budget;
  const [copyOpen, setCopyOpen] = useState(false);
  const [revision] = useState(b.period?.updated_at || null);
  const base: {
    kind: Allocation["kind"];
    reference_id: string;
    label: string;
    group: string;
  }[] = [
    ...data.categories
      .filter(
        (c) =>
          !c.archived || b.allocations.some((a) => a.reference_id === c.id),
      )
      .map((c) => ({
        kind: "category" as const,
        reference_id: c.id,
        label: c.name,
        group: c.group,
      })),
    ...data.members.map((m) => ({
      kind: "pocket" as const,
      reference_id: m.id,
      label: m.name,
      group: "Kieszonkowe",
    })),
    ...data.goals.map((g) => ({
      kind: "goal" as const,
      reference_id: g.id,
      label: g.name,
      group: "Przyszłość",
    })),
  ];
  const currentMember =
    data.members.find((m) => m.user_id === me.user.id)?.id || "";
  const [sources, setSources] = useState(() =>
    b.income_sources.length
      ? b.income_sources.map((s) => ({
          ...s,
          member_id: s.member_id || "",
          amount: moneyInput(s.amount),
        }))
      : [
          {
            id: "initial",
            name: "Wynagrodzenie",
            member_id: currentMember,
            amount: "0,00",
          },
        ],
  );
  function updateSource(id: string, patch: Partial<(typeof sources)[number]>) {
    setSources((rows) =>
      rows.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  }
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      base.map((a) => [
        a.reference_id,
        moneyInput(
          b.allocations.find((x) => x.reference_id === a.reference_id)
            ?.amount || 0,
        ),
      ]),
    ),
  );
  const safe = (s: string) => {
    try {
      return parseMoney(s);
    } catch {
      return 0;
    }
  };
  const income = sources.reduce((sum, source) => sum + safe(source.amount), 0);
  const unassigned =
    income - Object.values(values).reduce((sum, s) => sum + safe(s), 0);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await command.run(
      async (key) => {
        const payload = {
          expected_updated_at: revision,
          income_sources: sources.map((source) => ({
            name: source.name.trim(),
            member_id: source.member_id || null,
            amount: parseMoney(source.amount),
          })),
          allocations: base.map((a) => ({
            kind: a.kind,
            reference_id: a.reference_id,
            amount: parseMoney(values[a.reference_id] || "0"),
          })),
        };
        return api(
          `/households/${household}/budget/${month}`,
          json("PUT", payload, key),
        );
      },
      "Plan miesiąca zapisany",
      close,
    );
  }
  return (
    <form onSubmit={submit} className="budget-editor">
      <MonthCopy
        onOpen={setCopyOpen}
        apply={(proposal) => {
          setSources(
            proposal.income_sources.map((source, index) => ({
              ...source,
              id: `copy-${index}`,
              member_id: source.member_id || "",
              amount: moneyInput(source.amount),
            })),
          );
          setValues(
            Object.fromEntries(
              base.map((a) => [
                a.reference_id,
                moneyInput(
                  proposal.allocations.find(
                    (x) =>
                      x.kind === a.kind && x.reference_id === a.reference_id,
                  )?.amount || 0,
                ),
              ]),
            ),
          );
        }}
      />
      <Card className="income-plan">
        <div className="income-heading">
          <div>
            <h2>Skąd będą pieniądze?</h2>
            <p className="muted">
              Dodaj dochody, których spodziewacie się w tym miesiącu.
            </p>
          </div>
          <div className="income-total" aria-live="polite">
            <span className="eyebrow">RAZEM W PLANIE</span>
            <strong>{money(income)}</strong>
          </div>
        </div>
        <fieldset className="income-fields" disabled={command.busy}>
          {sources.map((source, index) => (
            <div
              className="income-source-editor"
              key={source.id}
              role="group"
              aria-label={`Źródło dochodu ${index + 1}`}
            >
              <Field
                label={`Nazwa źródła ${index + 1}`}
                placeholder="np. Wynagrodzenie, Zlecenia"
                maxLength={80}
                value={source.name}
                onChange={(e) =>
                  updateSource(source.id, { name: e.target.value })
                }
                required
              />
              <Select
                label={`Kto dostarcza dochód ${index + 1}`}
                value={source.member_id}
                onChange={(e) =>
                  updateSource(source.id, { member_id: e.target.value })
                }
              >
                <option value="">Wspólny dochód</option>
                {data.members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
              <MoneyField
                label={`Kwota źródła ${index + 1} (zł)`}
                value={source.amount}
                onChange={(e) =>
                  updateSource(source.id, { amount: e.target.value })
                }
                required
              />
              <button
                className="button secondary income-remove"
                type="button"
                aria-label={`Usuń źródło ${index + 1}`}
                onClick={() =>
                  setSources((rows) => rows.filter((s) => s.id !== source.id))
                }
              >
                <Trash2 size={17} />
                <span>Usuń</span>
              </button>
            </div>
          ))}
          {!sources.length && (
            <p className="muted">
              Nie ma jeszcze źródeł dochodu. Dodaj pierwsze, gdy znasz kwotę.
            </p>
          )}
          <button
            className="button secondary income-add"
            type="button"
            disabled={sources.length >= 50}
            onClick={() =>
              setSources((rows) => [
                ...rows,
                {
                  id: crypto.randomUUID(),
                  name: "",
                  member_id: currentMember,
                  amount: "",
                },
              ])
            }
          >
            <Plus size={18} />
            Dodaj źródło dochodu
          </button>
        </fieldset>
        <p className="muted small income-note">
          To plan. Gdy pieniądze wpłyną na konto, dodaj wpływ w transakcjach.
        </p>
      </Card>
      <div
        className={`plan-feedback ${income > 0 && unassigned === 0 ? "complete" : unassigned < 0 ? "over" : ""}`}
      >
        <span>
          {income === 0 && unassigned === 0 ? (
            "Dodaj planowane dochody"
          ) : unassigned === 0 ? (
            <>
              <Check size={19} />
              Wszystko przydzielone. Dobry plan!
            </>
          ) : unassigned < 0 ? (
            "Plan przekracza dochód"
          ) : (
            "Jeszcze do przydzielenia"
          )}
        </span>
        <strong>{money(unassigned)}</strong>
      </div>
      {["Potrzeby", "Na co dzień", "Kieszonkowe", "Przyszłość"].map((group) => (
        <Card className="plan-group" key={group}>
          <SectionTitle title={group} />
          {group === "Kieszonkowe" && (
            <p className="muted small">
              Stała kwota dla każdej osoby. Prywatne wydatki zostają prywatne.
            </p>
          )}
          {group === "Przyszłość" && !base.some((a) => a.group === group) && (
            <p className="muted">
              Najpierw{" "}
              <Link className="small-link" href="/cele">
                dodaj cel
              </Link>
              , potem zaplanuj comiesięczne odkładanie.
            </p>
          )}
          {base
            .filter((a) => a.group === group)
            .map((a) => (
              <div className="plan-row" key={a.reference_id}>
                <div>
                  <Icon
                    name={
                      a.kind === "pocket"
                        ? "pocket"
                        : a.kind === "goal"
                          ? "flag"
                          : data.categories.find((c) => c.id === a.reference_id)
                              ?.icon || "basket"
                    }
                  />
                  <strong>{a.label}</strong>
                </div>
                <MoneyField
                  label={`${a.label} — plan (zł)`}
                  value={values[a.reference_id] || "0,00"}
                  onChange={(e) =>
                    setValues({ ...values, [a.reference_id]: e.target.value })
                  }
                  required
                />
              </div>
            ))}
        </Card>
      ))}
      {!copyOpen && (
        <div className="form-actions sticky-actions">
          <ErrorMessage error={command.error} />
          <span>
            {command.error
              ? "Popraw dane i zapisz ponownie."
              : income > 0 && unassigned === 0
                ? "Gotowe. Wasz miesiąc ma plan."
                : "Możesz zapisać i dokończyć plan później."}
          </span>
          <div>
            {b.period && (
              <button
                className="button secondary"
                type="button"
                onClick={close}
              >
                Anuluj
              </button>
            )}
            <Submit busy={command.busy}>Zapisz plan</Submit>
          </div>
        </div>
      )}
    </form>
  );
}
export function TransactionRows({
  transactions,
  expanded = false,
}: {
  transactions: Transaction[];
  expanded?: boolean;
}) {
  const { data } = useApp();
  return (
    <div className="transaction-list">
      {transactions.map((t) => {
        const category = data.categories.find(
          (c) => c.id === t.allocations[0]?.category_id,
        );
        const positive = t.kind === "income";
        const icon = positive
          ? "account"
          : t.kind === "pocket"
            ? "pocket"
            : t.kind === "saving"
              ? "flag"
              : t.kind === "transfer"
                ? "account"
                : category?.icon || "receipt";
        return (
          <details
            className="transaction"
            key={t.id}
            open={expanded || undefined}
          >
            <summary>
              <Icon
                name={icon}
                color={positive ? "green" : category?.color || "gray"}
              />
              <div className="transaction-description">
                <strong>{t.description}</strong>
                <span>
                  {dateLabel(t.date)}
                  <i />{" "}
                  {t.kind === "income"
                    ? "Wpływ"
                    : t.kind === "pocket"
                      ? "Kieszonkowe"
                      : t.kind === "saving"
                        ? "Oszczędności"
                        : t.kind === "transfer"
                          ? "Przelew między kontami"
                          : t.status === "unallocated"
                            ? "Do przypisania"
                            : t.allocations.length > 1
                              ? `${t.allocations.length} kategorie`
                              : category?.name || "Wydatek"}
                </span>
              </div>
              <span
                className={`transaction-amount ${positive ? "positive-text" : ""}`}
              >
                {positive ? "+" : t.kind === "transfer" ? "" : "−"}
                {money(t.amount)}
              </span>
              <ChevronDown size={16} className="details-chevron" />
            </summary>
            <div className="transaction-details">
              <div>
                <span>Konto</span>
                <strong>
                  {data.accounts.find((a) => a.id === t.account_id)?.name}
                </strong>
              </div>
              {t.destination_id && (
                <div>
                  <span>Konto docelowe</span>
                  <strong>
                    {data.accounts.find((a) => a.id === t.destination_id)?.name}
                  </strong>
                </div>
              )}
              {t.allocations.map((a) => (
                <div key={a.category_id}>
                  <span>
                    {data.categories.find((c) => c.id === a.category_id)?.name}
                  </span>
                  <Amount value={a.amount} />
                </div>
              ))}
              {t.kind === "pocket" && (
                <p className="muted small">
                  Wypłacone{" "}
                  {data.members.find((m) => m.id === t.member_id)?.name}.
                  Prywatnych zakupów nie rozliczamy.
                </p>
              )}
              {t.source === "receipt" && (
                <Link className="text-button" href={`/paragony/${t.source_id}`}>
                  Zobacz paragon
                  <ArrowRight size={16} />
                </Link>
              )}
              <Link className="text-button" href={`/transakcje?edit=${t.id}`}>
                <Pencil size={16} />
                Edytuj transakcję
              </Link>
              {t.status === "unallocated" && (
                <CategorizeTransaction transaction={t} />
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
function CategorizeTransaction({ transaction }: { transaction: Transaction }) {
  const { data, household } = useApp();
  const command = useCommand();
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      () =>
        api(
          `/households/${household}/transactions/${transaction.id}/allocations`,
          json("PUT", [
            { category_id: f.get("category"), amount: transaction.amount },
          ]),
        ),
      "Kategoria przypisana",
    );
  }
  return (
    <form onSubmit={submit} className="inline-form">
      <Select label="Kategoria wydatku" name="category" required>
        <option value="">Wybierz kategorię</option>
        {data.categories
          .filter((c) => !c.archived)
          .map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
      </Select>
      <ErrorMessage error={command.error} />
      <Submit busy={command.busy}>Przypisz kategorię</Submit>
    </form>
  );
}
export function TransactionsScreen() {
  const { household, month } = useApp();
  const params = useSearchParams();
  const editId = params.get("edit");
  const focusedId = editId || params.get("item");
  const focused = useQuery({
    queryKey: ["transaction-detail", household, focusedId],
    queryFn: () =>
      api<Transaction>(`/households/${household}/transactions/${focusedId}`),
    enabled: !!focusedId,
  });
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const result = useQuery({
    queryKey: ["transactions", household, month, kind, search, offset],
    queryFn: () =>
      api<{ items: Transaction[]; has_more: boolean }>(
        `/households/${household}/transactions?month=${month}&kind=${kind}&search=${encodeURIComponent(search)}&offset=${offset}`,
      ),
  });
  if (editId)
    return (
      <>
        <PageHeading
          title="Popraw transakcję."
          description="Po zapisie zaktualizujemy salda i budżet."
        />
        {focused.isPending ? (
          <Skeleton />
        ) : focused.isError ? (
          <ErrorMessage error={focused.error.message} />
        ) : (
          focused.data && (
            <ManualTransaction
              key={focused.data.id}
              kind={focused.data.kind as MovementKind}
              memberId=""
              goalId=""
              initial={focused.data}
            />
          )
        )}
      </>
    );
  if (focusedId)
    return (
      <>
        <Link className="back-link" href="/inbox">
          Wróć do spraw do sprawdzenia
        </Link>
        <PageHeading
          title="Daj temu wydatkowi miejsce."
          description="Wybierz kategorię. Kwota jest już uwzględniona w miesiącu zakupu."
        />
        <Card>
          {focused.isPending ? (
            <Skeleton />
          ) : focused.isError ? (
            <ErrorMessage error={focused.error.message} />
          ) : (
            focused.data && (
              <TransactionRows transactions={[focused.data]} expanded />
            )
          )}
        </Card>
      </>
    );
  return (
    <>
      <PageHeading
        title="Wasza historia."
        description="Każdy wpływ, zakup i mały krok do celu w jednym miejscu."
        action={
          <Link className="button primary desktop-add" href="/dodaj">
            <Plus size={18} />
            Dodaj
          </Link>
        }
      />
      <Card className="timeline-card">
        <div className="timeline-filters">
          <div className="search-field">
            <Search size={18} />
            <input
              aria-label="Szukaj transakcji"
              placeholder="Szukaj po nazwie…"
              value={search}
              maxLength={160}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </div>
          <Select
            label="Rodzaj"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Wszystkie transakcje</option>
            <option value="expense">Wydatki</option>
            <option value="income">Wpływy</option>
            <option value="pocket">Kieszonkowe</option>
            <option value="saving">Oszczędności</option>
            <option value="transfer">Przelewy</option>
          </Select>
        </div>
        {result.isPending ? (
          <Skeleton />
        ) : result.isError ? (
          <>
            <ErrorMessage error={result.error.message} />
            <button
              className="button secondary"
              onClick={() => result.refetch()}
            >
              Spróbuj ponownie
            </button>
          </>
        ) : result.data.items.length ? (
          <>
            <TransactionRows transactions={result.data.items} />
            <div className="pagination">
              <button
                className="button secondary"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 30))}
              >
                Poprzednie
              </button>
              <span>Strona {offset / 30 + 1}</span>
              <button
                className="button secondary"
                disabled={!result.data.has_more}
                onClick={() => setOffset(offset + 30)}
              >
                Następne
              </button>
            </div>
          </>
        ) : (
          <Empty
            title={
              search || kind
                ? "Brak pasujących transakcji"
                : "Tutaj pojawi się Wasza historia"
            }
            description={
              search || kind
                ? "Zmień nazwę lub filtr, aby zobaczyć więcej."
                : "Dodaj pierwszy wpływ lub wydatek w tym miesiącu."
            }
            action={search || kind ? undefined : "Dodaj transakcję"}
            href="/dodaj"
          />
        )}
      </Card>
    </>
  );
}
export function MoreScreen() {
  const { data } = useApp();
  return (
    <>
      <PageHeading
        title="Trochę więcej możliwości."
        description="Wszystko, co pomaga Wam planować spokojniej."
      />
      <Card className="more-list">
        {[
          {
            href: "/cele",
            label: "Cele oszczędnościowe",
            desc: "Na przyszłość i marzenia",
            icon: Flag,
          },
          {
            href: "/analiza",
            label: "Analiza",
            desc: "Zobacz, dokąd idą pieniądze",
            icon: ChartNoAxesCombined,
          },
          {
            href: "/inbox",
            label: "Do sprawdzenia",
            desc: data.tasks.length
              ? pendingText(data.tasks.length)
              : "Wszystko na bieżąco",
            icon: Inbox,
          },
          {
            href: "/cykliczne",
            label: "Stałe wydatki",
            desc: "Powtarzalne płatności bez niespodzianek",
            icon: Repeat2,
          },
          {
            href: "/konta",
            label: "Konta",
            desc: "Wspólne pieniądze w jednym miejscu",
            icon: Landmark,
          },
          {
            href: "/ustawienia",
            label: "Ustawienia",
            desc: "Wasz dom, kategorie i prywatność",
            icon: Settings,
          },
        ].map(({ href, label, desc, icon: Icon }) => (
          <Link key={href} href={href}>
            <span className="icon-box">
              <Icon size={21} />
            </span>
            <div>
              <strong>{label}</strong>
              <small>{desc}</small>
            </div>
            <ArrowRight size={18} />
          </Link>
        ))}
      </Card>
    </>
  );
}
