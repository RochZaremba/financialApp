"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { money, monthName, shiftMonth } from "@/lib/money";
import type { BudgetCopyPreview } from "@/lib/types";
import { useApp, useCommand } from "./context";
import { Card, ErrorMessage, Field } from "./ui";

export function MonthCopy({
  apply,
}: {
  apply: (proposal: BudgetCopyPreview) => void;
}) {
  const { household, month } = useApp();
  const command = useCommand();
  const [source, setSource] = useState(shiftMonth(month, -1));
  const [proposal, setProposal] = useState<BudgetCopyPreview | null>(null);
  async function preview() {
    setProposal(null);
    await command.run(
      () =>
        api<BudgetCopyPreview>(
          `/households/${household}/budget/${month}/copy-preview?source_month=${encodeURIComponent(source)}`,
        ),
      "Plan wczytany do podglądu",
      setProposal,
    );
  }
  return (
    <Card>
      <details className="planning-tool">
        <summary>Skopiuj plan innego miesiąca</summary>
        <p className="muted small">
          Wczytasz dochody i przydziały do szkicu. Transakcje i salda pozostają
          w swoich miesiącach.
        </p>
        <div className="form-grid">
          <Field
            label="Miesiąc do skopiowania"
            type="month"
            min="2000-01"
            max="2100-12"
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setProposal(null);
            }}
          />
          <div className="form-actions">
            <button
              type="button"
              className="button secondary"
              disabled={command.busy || !source || source === month}
              onClick={preview}
            >
              {command.busy ? "Wczytuję plan…" : "Pokaż plan do skopiowania"}
            </button>
          </div>
        </div>
        <ErrorMessage error={command.error} />
        {proposal && (
          <div className="copy-preview">
            <h3>Plan z {monthName(proposal.source_month)}</h3>
            <p>
              Planowany dochód:{" "}
              <strong>{money(proposal.planned_income)}</strong>
            </p>
            {proposal.income_sources.map((s, i) => (
              <p key={i} className="muted small">
                {s.name} · {money(s.amount)}
              </p>
            ))}
            {proposal.allocations.map((a) => (
              <div
                className="income-source-summary"
                key={`${a.kind}:${a.reference_id}`}
              >
                <span>{a.label}</span>
                <strong>{money(a.amount)}</strong>
              </div>
            ))}
            {!!proposal.omitted.length && (
              <p className="notice warning">
                Pominięte nieaktywne pozycje: {proposal.omitted.join(", ")}.
              </p>
            )}
            <p className="muted small">
              Zastąpisz dochody i przydziały w tym szkicu. Sprawdź kwoty, a
              potem zapisz plan.
            </p>
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                apply(proposal);
                setProposal(null);
              }}
            >
              Zastosuj do szkicu
            </button>
          </div>
        )}
      </details>
    </Card>
  );
}
