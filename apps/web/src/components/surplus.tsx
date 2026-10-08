"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, json } from "@/lib/api";
import {
  money,
  moneyInput,
  monthName,
  parseMoney,
  shiftMonth,
} from "@/lib/money";
import { useApp, useCommand } from "./context";
import { Card, ErrorMessage, Field, MoneyField, Select } from "./ui";

type Target = {
  account_id: string;
  goal_id: string | null;
  basis_points: number;
};
type Policy = { account_id: string; targets: Target[] };
export type Settlement = {
  source_month: string;
  target_month: string;
  mode: "carry" | "distribute";
  total: number;
  available: number;
  preview_token: string;
  envelopes: {
    category_id: string;
    label: string;
    group: string;
    amount: number;
  }[];
  targets: (Target & { amount: number; label: string })[];
};
export function Surplus() {
  const { data, household, month } = useApp();
  const b = data.budget;
  const [open, setOpen] = useState(false);
  const policy = useQuery({
    queryKey: ["surplus-policy", household],
    queryFn: () =>
      api<Policy | null>(`/households/${household}/surplus-policy`),
    enabled: open && !b.settlement,
  });
  if (b.settlement)
    return (
      <Card className="settlement-summary">
        <h2>Miesiąc rozliczony</h2>
        <p>
          {b.settlement.mode === "carry"
            ? "Przeniesiono do kopert"
            : "Odłożono na oszczędności"}
          : <strong>{money(b.settlement.total)}</strong>.
        </p>
        <p className="muted small">
          Plan i transakcje tego miesiąca są zamknięte, żeby przeniesione
          pieniądze pozostały zgodne z rozliczeniem.
        </p>
        <p>Miesiąc docelowy: {monthName(b.settlement.target_month)}.</p>
      </Card>
    );
  if (
    month >=
    new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Europe/Warsaw",
      year: "numeric",
      month: "2-digit",
    })
      .format(new Date())
      .slice(0, 7)
  )
    return null;
  return (
    <Card>
      <details
        className="planning-tool"
        onToggle={(e) => setOpen(e.currentTarget.open)}
      >
        <summary>Rozlicz nadwyżkę miesiąca</summary>
        <p className="muted small">
          Przenieś niewykorzystane kwoty kopert do kolejnego miesiąca lub
          podziel je na oszczędności. Podgląd pokaże kwoty przed zamknięciem
          miesiąca.
        </p>
        {open &&
          (policy.isPending ? (
            <p role="status">Wczytuję proporcje…</p>
          ) : policy.isError ? (
            <>
              <ErrorMessage error={policy.error.message} />
              <button
                type="button"
                className="button secondary"
                onClick={() => policy.refetch()}
              >
                Spróbuj ponownie
              </button>
            </>
          ) : (
            <SurplusForm key={month} policy={policy.data || null} />
          ))}
      </details>
    </Card>
  );
}
function SurplusForm({ policy }: { policy: Policy | null }) {
  const { data, household, month } = useApp();
  const b = data.budget;
  const command = useCommand();
  const [mode, setMode] = useState<"carry" | "distribute">("carry");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      b.allocations
        .filter(
          (a) =>
            a.kind === "category" &&
            a.remaining > 0 &&
            data.categories.some((c) => c.id === a.reference_id && !c.archived),
        )
        .map((a) => [a.reference_id, moneyInput(a.remaining)]),
    ),
  );
  const sourceAccounts = data.accounts.filter((a) => a.currency === "PLN");
  const savings = sourceAccounts.filter((a) => a.kind === "savings");
  const [account, setAccount] = useState(
    policy?.account_id ||
      sourceAccounts.find((a) => a.kind === "checking")?.id ||
      "",
  );
  const [targets, setTargets] = useState(
    () =>
      policy?.targets.map((t) => ({
        ...t,
        percentage: moneyInput(t.basis_points),
      })) || [
        {
          account_id: savings[0]?.id || "",
          goal_id: null as string | null,
          basis_points: 10000,
          percentage: "100",
        },
      ],
  );
  const next = shiftMonth(month, 1);
  const today = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Warsaw",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const [date, setDate] = useState(
    today.startsWith(next) ? today : `${next}-01`,
  );
  const [performed, setPerformed] = useState(false);
  const [preview, setPreview] = useState<{
    result: Settlement;
    signature: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const available = Math.max(
    0,
    Math.min(b.remaining, b.income + b.carry_in - b.spent),
  );
  function payload() {
    return {
      mode,
      envelopes: Object.entries(values).map(([category_id, amount]) => ({
        category_id,
        amount: parseMoney(amount),
      })),
      ...(mode === "distribute"
        ? {
            account_id: account,
            transfer_date: date,
            targets: targets.map((t) => ({
              account_id: t.account_id,
              goal_id: t.goal_id || null,
              basis_points: parseMoney(t.percentage),
            })),
          }
        : {}),
    };
  }
  function change() {
    setPreview(null);
    setPerformed(false);
    setError("");
  }
  async function prepare() {
    if (busy) return;
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const input = payload();
      const result = await api<Settlement>(
        `/households/${household}/budget/${month}/settlement-preview`,
        json("POST", input),
      );
      setPreview({ result, signature: JSON.stringify(input) });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Nie udało się przygotować rozliczenia.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!preview) return;
    await command.run(() => {
      const input = payload();
      if (JSON.stringify(input) !== preview.signature)
        throw new Error("Wybór zmienił się. Przygotuj nowy podgląd.");
      return api(
        `/households/${household}/budget/${month}/settle`,
        json("POST", {
          ...input,
          preview_token: preview.result.preview_token,
          transfers_performed: performed,
        }),
      );
    }, "Nadwyżka rozliczona");
  }
  return (
    <div className="surplus-form">
      <p>
        Pokryte rzeczywistymi wpływami: <strong>{money(available)}</strong>.
      </p>
      <p className="muted small">
        Dodatnie koperty mogą przekraczać wspólną nadwyżkę. Kwoty muszą zmieścić
        się w pozostałych pieniądzach po wszystkich wydatkach.
      </p>
      <Select
        label="Co zrobić z nadwyżką?"
        value={mode}
        onChange={(e) => {
          setMode(e.target.value as typeof mode);
          change();
        }}
      >
        <option value="carry">Przenieś salda kopert</option>
        <option value="distribute">Podziel na oszczędności i cele</option>
      </Select>
      {!Object.keys(values).length && (
        <p className="muted">
          Brak dodatnich sald aktywnych kopert do rozliczenia.
        </p>
      )}
      <div className="form-grid">
        {Object.entries(values).map(([id, value]) => (
          <MoneyField
            key={id}
            label={`${data.categories.find((c) => c.id === id)?.name} — nadwyżka (zł)`}
            value={value}
            onChange={(e) => {
              setValues((current) => ({ ...current, [id]: e.target.value }));
              change();
            }}
          />
        ))}
      </div>
      {mode === "distribute" && (
        <>
          <div className="form-grid">
            <Select
              label="Z którego konta?"
              value={account}
              onChange={(e) => {
                setAccount(e.target.value);
                change();
              }}
            >
              {sourceAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} · {money(a.balance)}
                </option>
              ))}
            </Select>
            <Field
              label="Data wykonanych przelewów"
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                change();
              }}
            />
          </div>
          {!savings.length && (
            <p className="notice warning">
              Dodaj konto oszczędnościowe PLN w widoku Konta.
            </p>
          )}
          {targets.map((t, index) => (
            <div className="surplus-target" key={index}>
              <div className="form-grid">
                <Select
                  label={`Konto oszczędnościowe ${index + 1}`}
                  value={t.account_id}
                  onChange={(e) => {
                    setTargets((rows) =>
                      rows.map((r, i) =>
                        i === index ? { ...r, account_id: e.target.value } : r,
                      ),
                    );
                    change();
                  }}
                >
                  {savings.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </Select>
                <Select
                  label={`Cel nadwyżki ${index + 1}`}
                  value={t.goal_id || ""}
                  onChange={(e) => {
                    setTargets((rows) =>
                      rows.map((r, i) =>
                        i === index
                          ? { ...r, goal_id: e.target.value || null }
                          : r,
                      ),
                    );
                    change();
                  }}
                >
                  <option value="">Oszczędności bez celu</option>
                  {data.goals.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </Select>
                <Field
                  label={`Udział nadwyżki ${index + 1} (%)`}
                  inputMode="decimal"
                  value={t.percentage}
                  onChange={(e) => {
                    setTargets((rows) =>
                      rows.map((r, i) =>
                        i === index ? { ...r, percentage: e.target.value } : r,
                      ),
                    );
                    change();
                  }}
                />
              </div>
              {targets.length > 1 && (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => {
                    setTargets((rows) => rows.filter((_, i) => i !== index));
                    change();
                  }}
                >
                  Usuń udział {index + 1}
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            className="button secondary"
            disabled={targets.length >= 30}
            onClick={() => {
              setTargets((rows) => [
                ...rows,
                {
                  account_id: savings[0]?.id || "",
                  goal_id: null,
                  basis_points: 0,
                  percentage: "0",
                },
              ]);
              change();
            }}
          >
            Dodaj udział nadwyżki
          </button>
          <p className="muted small">
            Udziały muszą dawać 100%. Zapamiętamy konta i proporcje do
            następnego rozliczenia. Aplikacja zapisuje wykonane przelewy.
          </p>
        </>
      )}
      <ErrorMessage error={error || command.error} />
      <div className="form-actions">
        <button
          type="button"
          className="button secondary"
          disabled={busy || !Object.keys(values).length}
          onClick={prepare}
        >
          {busy ? "Przygotowuję…" : "Pokaż podział nadwyżki"}
        </button>
      </div>
      {preview && (
        <div className="surplus-preview">
          <h3>Do rozliczenia {money(preview.result.total)}</h3>
          <p>
            {preview.result.mode === "carry"
              ? "Do kopert w"
              : "Na oszczędności z nadwyżki; przelewy w"}{" "}
            {monthName(preview.result.target_month)}.
          </p>
          {(preview.result.mode === "carry"
            ? preview.result.envelopes
            : preview.result.targets
          ).map((row, index) => (
            <p className="surplus-preview-row" key={index}>
              <span>{row.label}</span>
              <strong>{money(row.amount)}</strong>
            </p>
          ))}
          <p className="notice warning">
            Zamkniesz plan i transakcje {monthName(month)}. Sprawdź wszystkie
            wpisy przed rozliczeniem. Przeniesione kwoty nie są nowym dochodem.
          </p>
          {mode === "distribute" && (
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={performed}
                onChange={(e) => setPerformed(e.target.checked)}
              />
              Przelewy zostały wykonane
            </label>
          )}
          <div className="form-actions">
            <button
              type="button"
              className="button primary"
              disabled={command.busy || (mode === "distribute" && !performed)}
              onClick={confirm}
            >
              {command.busy
                ? "Zapisuję…"
                : "Zamknij miesiąc i zapisz rozliczenie"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
