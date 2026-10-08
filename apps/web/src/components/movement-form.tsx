"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Wallet, Trash2, Plus } from "lucide-react";
import { api, json } from "@/lib/api";
import { moneyInput, parseMoney, warsawDate } from "@/lib/money";
import type { Transaction } from "@/lib/types";
import { useApp, useCommand } from "./context";
import {
  Card,
  Empty,
  ErrorMessage,
  Field,
  Icon,
  MoneyField,
  Select,
  Submit,
} from "./ui";
export type MovementKind =
  "expense" | "income" | "transfer" | "pocket" | "saving";
export function ManualTransaction({
  kind,
  memberId,
  goalId,
  initial,
}: {
  kind: MovementKind;
  memberId: string;
  goalId: string;
  initial?: Transaction;
}) {
  const { data, household, month } = useApp();
  const command = useCommand();
  const router = useRouter();
  const documentary = initial?.source === "receipt";
  const [selectedMember, setSelectedMember] = useState(
    initial?.member_id || memberId || data.members[0]?.id || "",
  );
  const [selectedGoal, setSelectedGoal] = useState(
    initial?.goal_id || goalId || data.goals[0]?.id || "",
  );
  const budgetAllocation = data.budget.allocations.find(
    (a) =>
      a.reference_id === (kind === "pocket" ? selectedMember : selectedGoal),
  );
  const [sourceAccount, setSourceAccount] = useState(
    initial?.account_id ||
      data.accounts.find((a) => a.currency === "PLN" && a.kind === "checking")
        ?.id ||
      data.accounts.find((a) => a.currency === "PLN")?.id ||
      "",
  );
  const [destinationAccount, setDestinationAccount] = useState(
    initial?.destination_id ||
      data.accounts.find(
        (a) =>
          a.currency === "PLN" &&
          a.kind === "savings" &&
          a.id !== sourceAccount,
      )?.id ||
      data.accounts.find((a) => a.currency === "PLN" && a.id !== sourceAccount)
        ?.id ||
      "",
  );
  const [splits, setSplits] = useState(
    initial?.allocations.length
      ? initial.allocations.map((a) => ({
          category_id: a.category_id,
          amount: moneyInput(a.amount),
        }))
      : [{ category_id: "", amount: "" }],
  );
  const [amount, setAmount] = useState(
    moneyInput(
      initial
        ? initial.amount
        : kind === "pocket" || kind === "saving"
          ? Math.max(
              0,
              (budgetAllocation?.amount || 0) - (budgetAllocation?.spent || 0),
            )
          : 0,
    ),
  );
  const [splitMode, setSplitMode] = useState(
    (initial?.allocations.length || 0) > 1,
  );
  function chooseRecipient(reference: string) {
    const allocation = data.budget.allocations.find(
      (a) => a.reference_id === reference,
    );
    if (!initial)
      setAmount(
        moneyInput(
          Math.max(0, (allocation?.amount || 0) - (allocation?.spent || 0)),
        ),
      );
    if (kind === "pocket") setSelectedMember(reference);
    else setSelectedGoal(reference);
  }
  const titles = {
    expense: "Szybki wydatek",
    income: "Wspólny wpływ",
    transfer: "Przelew między kontami",
    pocket: "Coś dla siebie",
    saving: "Krok bliżej celu",
  };
  const date =
    initial?.date ||
    (month === warsawDate().slice(0, 7) ? warsawDate() : `${month}-01`);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      async (key) => {
        const total = parseMoney(amount);
        if (total <= 0)
          throw new Error("Kwota transakcji musi być większa od zera.");
        const allocations =
          kind === "expense"
            ? splitMode
              ? splits.map((s) => ({
                  category_id: s.category_id,
                  amount: parseMoney(s.amount),
                }))
              : documentary
                ? initial.allocations
                : f.get("category")
                  ? [{ category_id: String(f.get("category")), amount: total }]
                  : []
            : [];
        if (
          splitMode &&
          allocations.reduce((sum, a) => sum + a.amount, 0) !== total
        )
          throw new Error("Suma kategorii musi być równa kwocie wydatku.");
        return api(
          `/households/${household}/transactions${initial ? "/" + initial.id : ""}`,
          json(
            initial ? "PUT" : "POST",
            {
              ...(initial ? { expected_updated_at: initial.updated_at } : {}),
              kind,
              amount: total,
              date: f.get("date"),
              description: f.get("description"),
              account_id: f.get("account"),
              destination_id:
                kind === "transfer" || kind === "saving"
                  ? f.get("destination")
                  : null,
              member_id: kind === "pocket" ? f.get("member") : null,
              goal_id: kind === "saving" ? f.get("goal") : null,
              allocations,
            },
            key,
          ),
        );
      },
      initial
        ? "Transakcja zaktualizowana"
        : kind === "pocket"
          ? "Kieszonkowe wypłacone"
          : kind === "saving"
            ? "Pieniądze odłożone"
            : "Transakcja zapisana",
      () => router.push(initial ? "/transakcje" : "/"),
    );
  }
  if (kind === "saving" && !data.goals.length)
    return (
      <Card>
        <Empty
          icon="flag"
          title="Najpierw wybierz, na co odkładacie"
          description="Stwórz pierwszy cel. Każda wpłata będzie przybliżać Was do niego."
          action="Dodaj cel"
          href="/cele"
        />
      </Card>
    );
  if (
    (kind === "transfer" || kind === "saving") &&
    data.accounts.filter((a) => a.currency === "PLN").length < 2
  )
    return (
      <Card>
        <Empty
          icon="account"
          title="Potrzebujesz drugiego konta"
          description="Dodaj konto docelowe, aby zrobić przelew."
          action="Dodaj konto"
          href="/konta"
        />
      </Card>
    );
  return (
    <Card className="form-card">
      <div className="form-card-heading">
        <Icon
          name={
            kind === "pocket"
              ? "pocket"
              : kind === "saving"
                ? "flag"
                : "receipt"
          }
        />
        <h2>{initial ? "Edytuj transakcję" : titles[kind]}</h2>
      </div>
      {documentary && (
        <p className="muted small">
          Kwota, data i kategorie pochodzą z zatwierdzonego paragonu. Tutaj
          zmienisz opis i konto.
        </p>
      )}
      {kind === "pocket" && (
        <div className="notice soft">
          <Wallet size={19} />
          <span>
            Po wypłacie to prywatne pieniądze. Nie trzeba dodawać paragonów ani
            kategorii.
          </span>
        </div>
      )}
      {kind === "saving" && (
        <p className="muted">
          Przelew między Waszymi kontami zwiększy kwotę odłożoną na wybrany cel.
        </p>
      )}
      <form onSubmit={submit}>
        <div className="form-grid">
          <MoneyField
            label="Kwota (zł)"
            readOnly={documentary}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
          <Field
            label="Data"
            readOnly={documentary}
            name="date"
            type="date"
            defaultValue={date}
            min="2000-01-01"
            max="2100-12-31"
            required
          />
        </div>
        <Field
          label={
            kind === "income" ? "Skąd te pieniądze?" : "Nazwa lub krótki opis"
          }
          name="description"
          defaultValue={initial?.description}
          required
          maxLength={160}
          placeholder={
            kind === "expense"
              ? "np. Zakupy w Biedronce"
              : kind === "income"
                ? "np. Wynagrodzenie"
                : kind === "pocket"
                  ? "np. Kieszonkowe na ten miesiąc"
                  : "np. Odkładamy na wakacje"
          }
        />
        <div className="form-grid">
          <Select
            name="account"
            label={kind === "income" ? "Konto docelowe" : "Z konta"}
            value={sourceAccount}
            onChange={(e) => {
              setSourceAccount(e.target.value);
              if (destinationAccount === e.target.value)
                setDestinationAccount(
                  data.accounts.find(
                    (a) => a.currency === "PLN" && a.id !== e.target.value,
                  )?.id || "",
                );
            }}
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
          {(kind === "saving" || kind === "transfer") && (
            <Select
              name="destination"
              label="Na konto"
              value={destinationAccount}
              onChange={(e) => setDestinationAccount(e.target.value)}
              required
            >
              {data.accounts
                .filter((a) => a.currency === "PLN" && a.id !== sourceAccount)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </Select>
          )}
          {kind === "pocket" && (
            <Select
              name="member"
              label="Dla kogo?"
              value={selectedMember}
              onChange={(e) => chooseRecipient(e.target.value)}
              required
            >
              {data.members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          )}
          {kind === "saving" && (
            <Select
              name="goal"
              label="Na jaki cel?"
              value={selectedGoal}
              onChange={(e) => chooseRecipient(e.target.value)}
              required
            >
              {data.goals.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </Select>
          )}
          {kind === "expense" && !splitMode && (
            <Select
              name="category"
              label="Kategoria"
              defaultValue={initial?.allocations[0]?.category_id || ""}
              disabled={documentary}
            >
              <option value="">Przypiszę później</option>
              {data.categories
                .filter(
                  (c) =>
                    !c.archived ||
                    initial?.allocations.some((a) => a.category_id === c.id),
                )
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </Select>
          )}
        </div>
        {kind === "expense" && !documentary && (
          <>
            <button
              type="button"
              className="text-button"
              onClick={() => setSplitMode(!splitMode)}
            >
              {splitMode ? "Jedna kategoria" : "Podziel między kategorie"}
              <ArrowRight size={15} />
            </button>
            {splitMode && (
              <div className="split-editor">
                {splits.map((s, index) => (
                  <div key={index} className="split-row">
                    <Select
                      label={`Kategoria ${index + 1}`}
                      value={s.category_id}
                      required
                      onChange={(e) =>
                        setSplits(
                          splits.map((x, i) =>
                            i === index
                              ? { ...x, category_id: e.target.value }
                              : x,
                          ),
                        )
                      }
                    >
                      <option value="">Wybierz</option>
                      {data.categories
                        .filter(
                          (c) =>
                            !c.archived ||
                            initial?.allocations.some(
                              (a) => a.category_id === c.id,
                            ),
                        )
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                    </Select>
                    <MoneyField
                      label={`Kwota ${index + 1} (zł)`}
                      value={s.amount}
                      required
                      onChange={(e) =>
                        setSplits(
                          splits.map((x, i) =>
                            i === index ? { ...x, amount: e.target.value } : x,
                          ),
                        )
                      }
                    />
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Usuń kategorię ${index + 1}`}
                      disabled={splits.length === 1}
                      onClick={() =>
                        setSplits(splits.filter((_, i) => i !== index))
                      }
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="button secondary"
                  onClick={() =>
                    setSplits([...splits, { category_id: "", amount: "" }])
                  }
                >
                  <Plus size={17} />
                  Dodaj kategorię
                </button>
              </div>
            )}
          </>
        )}
        <ErrorMessage error={command.error} />
        <div className="form-actions">
          <Link
            href={initial ? "/transakcje" : "/"}
            className="button secondary"
          >
            Anuluj
          </Link>
          <Submit busy={command.busy}>
            {initial
              ? "Zapisz zmiany"
              : kind === "pocket"
                ? "Wypłać kieszonkowe"
                : kind === "saving"
                  ? "Odłóż na cel"
                  : "Zapisz transakcję"}
          </Submit>
        </div>
      </form>
    </Card>
  );
}
