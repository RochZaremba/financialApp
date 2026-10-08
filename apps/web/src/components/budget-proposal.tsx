"use client";
import { useRef, useState } from "react";
import { api, json } from "@/lib/api";
import { money } from "@/lib/money";
import { useApp } from "./context";
import { Card, ErrorMessage, Field } from "./ui";

type Draft = {
  income_sources: { name: string; member_id: string | null; amount: number }[];
  allocations: {
    kind: "category" | "pocket" | "goal";
    reference_id: string;
    amount: number;
  }[];
};
type Proposal = {
  mode: "ai" | "history";
  summary: string;
  assumptions: string[];
  category_pool: number;
  reserved: number;
  allocations: {
    category_id: string;
    amount: number;
    label: string;
    reason: string;
  }[];
};
export function BudgetProposal({
  draft,
  apply,
  onOpen,
}: {
  draft: () => Draft;
  apply: (rows: Proposal["allocations"]) => void;
  onOpen: (open: boolean) => void;
}) {
  const { household, month, me } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preferences, setPreferences] = useState("");
  const [result, setResult] = useState<{
    proposal: Proposal;
    signature: string;
  } | null>(null);
  const details = useRef<HTMLDetailsElement>(null);
  async function propose(mode: Proposal["mode"]) {
    if (busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const current = draft();
      const proposal = await api<Proposal>(
        `/households/${household}/budget/${month}/proposal`,
        json("POST", { mode, draft: current, preferences }),
      );
      setResult({ proposal, signature: JSON.stringify(current) });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Nie udało się przygotować propozycji.",
      );
    } finally {
      setBusy(false);
    }
  }
  function useProposal() {
    if (!result) return;
    try {
      if (JSON.stringify(draft()) !== result.signature) {
        setError("Szkic zmienił się. Przygotuj nową propozycję.");
        return;
      }
      apply(result.proposal.allocations);
      if (details.current) details.current.open = false;
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sprawdź kwoty w szkicu.");
    }
  }
  return (
    <Card>
      <details
        ref={details}
        className="planning-tool"
        onToggle={(e) => onOpen(e.currentTarget.open)}
      >
        <summary>Pomóż mi rozdzielić budżet</summary>
        <p className="muted small">
          Propozycja obejmie wszystkie aktywne kategorie. Dochód, kieszonkowe i
          cele pozostają zgodne ze szkicem. Kwoty sprawdzisz przed zapisem.
        </p>
        <Field
          label="Co uwzględnić w propozycji?"
          placeholder="Np. mniej jedzenia na mieście, większa pula na dom"
          value={preferences}
          maxLength={1000}
          onChange={(e) => {
            setPreferences(e.target.value);
            setResult(null);
          }}
        />
        {me.budget_ai_available ? (
          <p className="muted small">
            Po wybraniu AI wyślemy dostawcy nazwy kategorii, kwoty w szkicu,
            zbiorczą historię wydatków z 6 miesięcy i wpisane preferencje.
          </p>
        ) : (
          <p className="muted small">
            AI nie jest skonfigurowane. Propozycja z historii jest dostępna.
          </p>
        )}
        <div className="form-actions">
          <button
            type="button"
            className="button primary"
            disabled={busy || !me.budget_ai_available}
            onClick={() => propose("ai")}
          >
            Zaproponuj z AI
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => propose("history")}
          >
            Na podstawie historii
          </button>
        </div>
        {busy && <p role="status">Przygotowuję propozycję…</p>}
        <ErrorMessage error={error} />
        {result && (
          <div className="budget-proposal">
            <h3>
              {result.proposal.mode === "ai"
                ? "Propozycja AI"
                : "Propozycja z historii"}
            </h3>
            <p>{result.proposal.summary}</p>
            <p>
              Na kategorie:{" "}
              <strong>{money(result.proposal.category_pool)}</strong>.
              Kieszonkowe i cele: {money(result.proposal.reserved)}.
            </p>
            {result.proposal.allocations.map((row) => (
              <div className="proposal-row" key={row.category_id}>
                <div>
                  <strong>{row.label}</strong>
                  <p className="muted small">{row.reason}</p>
                </div>
                <strong>{money(row.amount)}</strong>
              </div>
            ))}
            <ul className="muted small">
              {result.proposal.assumptions.map((text, index) => (
                <li key={index}>{text}</li>
              ))}
            </ul>
            <button
              type="button"
              className="button primary"
              onClick={useProposal}
            >
              Zastosuj propozycję do szkicu
            </button>
            <p className="muted small">
              Następnie możesz poprawić kwoty i zapisać plan miesiąca.
            </p>
          </div>
        )}
      </details>
    </Card>
  );
}
