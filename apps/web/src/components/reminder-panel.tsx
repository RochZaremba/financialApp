"use client";
import { useApp, useCommand } from "./context";
import { api } from "@/lib/api";
import { dateLabel, money } from "@/lib/money";
import { Card, ErrorMessage } from "./ui";
export function ReminderPanel() {
  const { data, household } = useApp();
  const command = useCommand();
  if (!data.reminders.length) return null;
  return (
    <Card className="reminder-panel">
      <h2>Przypomnienia na dziś</h2>
      <p className="muted small">
        Zbliżające się terminy i płatności bez potwierdzenia. Wydatek zapisujemy
        dopiero po zapłacie.
      </p>
      {data.reminders.map((row) => (
        <div className="reminder-row" key={`${row.id}:${row.due_date}`}>
          <div>
            <strong>{row.name}</strong>
            <p className="muted small">
              {dateLabel(row.due_date)} · {money(row.amount)}
            </p>
            <span
              className={`pill ${row.reminder_status === "overdue" ? "warning" : "neutral"}`}
            >
              {row.reminder_status === "overdue"
                ? "Termin minął"
                : "Zbliża się termin"}
            </span>
          </div>
          <button
            type="button"
            className="button secondary"
            disabled={command.busy}
            onClick={() =>
              command.run(
                () =>
                  api(
                    `/households/${household}/recurring/${row.id}/pay/${row.due_date}`,
                    { method: "POST" },
                  ),
                "Płatność zapisana",
              )
            }
          >
            Potwierdź zapłatę
          </button>
        </div>
      ))}
      <ErrorMessage error={command.error} />
    </Card>
  );
}
