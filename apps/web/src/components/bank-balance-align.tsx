"use client";
import { useState } from "react";
import { api, json } from "@/lib/api";
import { money } from "@/lib/money";
import { useApp, useCommand } from "./context";
import { ErrorMessage, Submit } from "./ui";

type Snapshot = {
  id: string;
  bank_balance: number | null;
  app_balance: number | null;
  balance_at: string | null;
  adjustments?: {
    id: string;
    amount: number;
    balance_before: number;
    balance_after: number;
    created_at: string;
    created_by_name: string | null;
  }[];
};
export function BankBalanceAlign({
  bank,
  owner,
}: {
  bank: Snapshot;
  owner: boolean;
}) {
  const { household } = useApp();
  const [open, setOpen] = useState(false);
  const command = useCommand();
  const valid =
    bank.bank_balance !== null &&
    bank.app_balance !== null &&
    !!bank.balance_at;
  const difference = valid ? bank.bank_balance! - bank.app_balance! : 0;
  return (
    <div className="bank-align">
      {owner && valid && difference !== 0 && (
        <button
          className="button secondary"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          Wyrównaj saldo aplikacji do banku
        </button>
      )}
      {open && difference !== 0 && (
        <form
          className="balance-confirm"
          onSubmit={async (e) => {
            e.preventDefault();
            await command.run(
              (key) =>
                api(
                  `/households/${household}/bank/accounts/${bank.id}/align`,
                  json(
                    "POST",
                    {
                      expected_app_balance: bank.app_balance,
                      expected_bank_balance: bank.bank_balance,
                      expected_bank_balance_at: bank.balance_at,
                    },
                    key,
                  ),
                ),
              "Saldo aplikacji wyrównane do banku",
              () => setOpen(false),
            );
          }}
        >
          <h3>Potwierdź korektę salda</h3>
          <p>
            Z {money(bank.app_balance!)} na{" "}
            <strong>{money(bank.bank_balance!)}</strong>.
          </p>
          <p>
            Korekta:{" "}
            <strong>
              {difference > 0 ? "+" : ""}
              {money(difference)}
            </strong>
            .
          </p>
          <p className="muted small">
            To zapis w historii salda, bez nowego wydatku lub dochodu. Najpierw
            sprawdź nieuzupełnione operacje. Późniejsze dopisanie historii znowu
            zmieni saldo. Korzystamy z salda banku pobranego{" "}
            {new Date(bank.balance_at!).toLocaleString("pl-PL", {
              timeZone: "Europe/Warsaw",
            })}
            .
          </p>
          <ErrorMessage error={command.error} />
          <div className="bank-actions">
            <Submit busy={command.busy}>Potwierdź wyrównanie</Submit>
            <button
              type="button"
              className="button secondary"
              onClick={() => setOpen(false)}
            >
              Anuluj
            </button>
          </div>
        </form>
      )}
      {!!bank.adjustments?.length && (
        <details>
          <summary>Historia korekt salda ({bank.adjustments.length})</summary>
          <ul className="balance-history">
            {bank.adjustments.map((a) => (
              <li key={a.id}>
                <strong>
                  {a.amount > 0 ? "+" : ""}
                  {money(a.amount)}
                </strong>
                <span>
                  {money(a.balance_before)} → {money(a.balance_after)}
                </span>
                <small>
                  {a.created_by_name || "Nieznany autor"} ·{" "}
                  {new Date(a.created_at).toLocaleString("pl-PL", {
                    timeZone: "Europe/Warsaw",
                  })}
                </small>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
