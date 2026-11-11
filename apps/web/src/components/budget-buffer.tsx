"use client";
import { money } from "@/lib/money";
import type { Budget } from "@/lib/types";
import { Card } from "./ui";

export function BudgetBuffer({ buffer }: { buffer: Budget["buffer"] }) {
  if (!buffer) return null;
  return (
    <Card className="budget-buffer">
      <div className="section-title">
        <h2>{buffer.label} · rezerwa budżetu</h2>
        <strong>{money(buffer.remaining)}</strong>
      </div>
      <p>
        Plan: {money(buffer.planned)} · Na przekroczenia:{" "}
        {money(buffer.covered)}.
      </p>
      <p className="muted small">
        Bufor dostaje środki pozostałe po innych przydziałach. Pokrycie koperty
        nie jest drugim wydatkiem. Zwrot za zakup automatycznie uwalnia
        odpowiednią część rezerwy.
      </p>
      <details>
        <summary>Zobacz, które koperty skorzystały z bufora</summary>
        {buffer.recipients.length ? (
          <ul className="buffer-recipients">
            {buffer.recipients.map((r) => (
              <li key={`${r.kind}:${r.reference_id}`}>
                <div>
                  <strong>{r.label}</strong>
                  <small>Przekroczenie planu: {money(r.overrun)}</small>
                  {r.uncovered > 0 && (
                    <small className="negative">
                      Bez pokrycia: {money(r.uncovered)}
                    </small>
                  )}
                </div>
                <strong>{money(r.covered)} z bufora</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p>Żadna koperta nie potrzebuje teraz rezerwy.</p>
        )}
      </details>
      {buffer.uncovered > 0 && (
        <p className="notice warning">
          Brakuje {money(buffer.uncovered)} do pokrycia wszystkich przekroczeń.
          Bufor nie zadłuża innych kopert.
        </p>
      )}
    </Card>
  );
}
