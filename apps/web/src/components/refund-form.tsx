"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { api, json } from "@/lib/api";
import { money, moneyInput, parseMoney, warsawDate } from "@/lib/money";
import type { Transaction } from "@/lib/types";
import { useApp, useCommand } from "./context";
import { ErrorMessage, Field, MoneyField, Select, Submit } from "./ui";

export function RefundForm({ transaction }: { transaction: Transaction }) {
  const { data, household } = useApp();
  const command = useCommand();
  const [done, setDone] = useState(false);
  const details = useRef<HTMLDetailsElement>(null);
  if (transaction.is_refund)
    return (
      <p className="notice">
        Zwrot za:{" "}
        <Link href={`/transakcje?item=${transaction.refund_of_id}`}>
          {transaction.refund_of_description || "oryginalny zakup"}
        </Link>
        . Pomniejsza wydatki, nie zwiększa dochodu.
      </p>
    );
  if (transaction.kind !== "expense") return null;
  return (
    <div className="refund-panel">
      {transaction.refunded_amount > 0 && (
        <p>
          Oddano już {money(transaction.refunded_amount)} · Pozostało do zwrotu{" "}
          {money(transaction.refundable_amount)}.
        </p>
      )}
      {transaction.refundable_amount > 0 && (
        <details ref={details}>
          <summary>Zarejestruj zwrot</summary>
          <form
            key={transaction.updated_at}
            onSubmit={async (event) => {
              event.preventDefault();
              const f = new FormData(event.currentTarget);
              await command.run(
                (key) =>
                  api(
                    `/households/${household}/transactions/${transaction.id}/refund`,
                    json(
                      "POST",
                      {
                        amount: parseMoney(String(f.get("amount"))),
                        date: f.get("date"),
                        account_id: f.get("account"),
                        description: f.get("description"),
                        expected_updated_at: transaction.updated_at,
                      },
                      key,
                    ),
                  ),
                "Zwrot zapisany",
                () => {
                  setDone(true);
                  if (details.current) details.current.open = false;
                },
              );
            }}
          >
            <p className="muted small">
              Zapisz faktycznie otrzymany zwrot. Częściowy zwrot dzielimy
              proporcjonalnie według kategorii zakupu.
            </p>
            <MoneyField
              label="Kwota zwrotu (zł)"
              name="amount"
              defaultValue={moneyInput(transaction.refundable_amount)}
              required
            />
            <Field
              label="Data otrzymania zwrotu"
              name="date"
              type="date"
              min={transaction.date}
              max={warsawDate()}
              defaultValue={warsawDate()}
              required
            />
            <Select
              label="Konto otrzymujące zwrot"
              name="account"
              defaultValue={transaction.account_id}
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
            <Field
              label="Opis zwrotu"
              name="description"
              maxLength={160}
              defaultValue={`Zwrot: ${transaction.description}`.slice(0, 160)}
              required
            />
            <ErrorMessage error={command.error} />
            {done && (
              <p role="status">
                Zapisano zwrot. Lista i budżet zostały odświeżone.
              </p>
            )}
            <Submit busy={command.busy}>Zapisz zwrot</Submit>
          </form>
        </details>
      )}
    </div>
  );
}
