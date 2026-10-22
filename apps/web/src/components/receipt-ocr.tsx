"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { api, json } from "@/lib/api";
import { money } from "@/lib/money";
import type { OCRAttempt, Receipt } from "@/lib/types";
import { useApp, useCommand } from "./context";
import { Card, ErrorMessage } from "./ui";

const statusName = {
  succeeded: "Odczytano",
  partial: "Niepełny odczyt",
  failed: "Błąd odczytu",
};
const providerName = (name: string) =>
  ({
    gemini: "Gemini",
    openai: "OpenAI",
    fixture: "Tryb demonstracyjny",
    manual: "Tryb ręczny",
  })[name] || name;

export function ReceiptOCR({
  receipt,
  onApply,
}: {
  receipt: Receipt;
  onApply: (receipt: Receipt) => void;
}) {
  const { household, me } = useApp();
  const command = useCommand();
  const [confirm, setConfirm] = useState(false);
  const [attempt, setAttempt] = useState<OCRAttempt | null>(
    receipt.ocr_attempts?.[0] || null,
  );
  const [preview, setPreview] = useState(
    !!attempt?.result && !attempt.applied_at,
  );
  const base = `/households/${household}/receipts/${receipt.id}`;
  const enabled = me.receipt_provider !== "manual";
  const diagnostics = attempt?.diagnostics;

  async function retry() {
    await command.run(
      (key) => api<OCRAttempt>(`${base}/ocr`, json("POST", {}, key)),
      "Próba odczytu zakończona",
      (value) => {
        setAttempt(value);
        setPreview(true);
        setConfirm(false);
      },
    );
  }
  async function apply() {
    if (!attempt) return;
    await command.run(
      () =>
        api<Receipt>(
          `${base}/ocr/${attempt.id}/apply`,
          json("POST", { expected_updated_at: attempt.receipt_updated_at }),
        ),
      "Nowy odczyt zastosowany do szkicu",
      (value) => {
        onApply(value);
        setAttempt(
          value.ocr_attempts?.find((a) => a.id === attempt.id) || null,
        );
        setPreview(false);
      },
    );
  }
  async function inspect(id: string) {
    await command.run(
      () => api<OCRAttempt>(`${base}/ocr/${id}`),
      "Wczytano szczegóły próby",
      (value) => {
        setAttempt(value);
        setPreview(true);
      },
    );
  }

  return (
    <Card className="receipt-ocr">
      <div className="section-title">
        <h2>Odczyt ze zdjęcia</h2>
        <button
          className="button secondary"
          disabled={command.busy || !enabled}
          onClick={() => {
            setConfirm(!confirm);
            command.setError("");
          }}
        >
          <RotateCcw size={17} /> Odczytaj ponownie
        </button>
      </div>
      <p className="muted">
        Możesz ponowić odczyt zapisanego zdjęcia bez ponownego przesyłania
        pliku. Dostawca: {providerName(me.receipt_provider)}.
      </p>
      {!enabled && (
        <p>
          Włącz Gemini lub OpenAI w konfiguracji aplikacji, aby odczytać zdjęcie
          ponownie.
        </p>
      )}
      {confirm && (
        <div className="notice soft ocr-confirm">
          <p>
            Wyślemy zdjęcie ponownie do {providerName(me.receipt_provider)}.
            Wywołanie może być płatne. Najpierw pokażemy wynik; obecne dane
            pozostaną zapisane.
          </p>
          <div className="form-actions">
            <button
              className="button primary"
              onClick={retry}
              disabled={command.busy}
            >
              {command.busy ? "Odczytuję zdjęcie…" : "Ponów odczyt zdjęcia"}
            </button>
            <button
              className="button secondary"
              onClick={() => setConfirm(false)}
              disabled={command.busy}
            >
              Anuluj
            </button>
          </div>
        </div>
      )}
      {command.busy && (
        <p role="status">
          Trwa pobieranie odczytu. Może to potrwać ponad minutę.
        </p>
      )}
      <ErrorMessage error={command.error} />
      {diagnostics?.message && (
        <div
          className="notice warning ocr-diagnostics"
          role={attempt?.status === "failed" ? "alert" : "note"}
        >
          <strong>
            {providerName(attempt?.provider || "")} —{" "}
            {attempt && statusName[attempt.status]}
          </strong>
          <p>{diagnostics.message}</p>
          <p className="small">
            Kod: <code>{diagnostics.code}</code>
            {diagnostics.http_status != null &&
              ` · HTTP ${diagnostics.http_status}`}
            {diagnostics.reason && ` · ${diagnostics.reason}`}
            {attempt?.model && ` · Model: ${attempt.model}`}
          </p>
          {diagnostics.fields?.length ? (
            <p className="small">
              Pola wymagające sprawdzenia: {diagnostics.fields.join(", ")}
            </p>
          ) : null}
          {diagnostics.retry_after_seconds != null && (
            <p>Spróbuj najwcześniej za {diagnostics.retry_after_seconds} s.</p>
          )}
        </div>
      )}
      {preview && attempt?.result && (
        <div className="ocr-preview">
          <h3>Wynik ponownego odczytu</h3>
          <p>
            {attempt.result.merchant || "Brak nazwy sklepu"} ·{" "}
            {attempt.result.date || "Brak daty"} ·{" "}
            {attempt.result.total == null
              ? "Brak sumy"
              : money(attempt.result.total)}
          </p>
          <ul aria-label="Pozycje odczytane ze zdjęcia">
            {attempt.result.items.map((item, index) => (
              <li key={index}>
                <span>
                  {item.name}
                  {item.quantity ? ` · ${item.quantity}` : ""}
                </span>
                <strong>
                  {item.amount == null ? "Brak kwoty" : money(item.amount)}
                </strong>
              </li>
            ))}
          </ul>
          {receipt.status === "confirmed" ? (
            <p>
              Paragon jest zatwierdzony. Ten wynik służy do porównania —
              zapisany wydatek i budżet pozostają bez zmian.
            </p>
          ) : !attempt.applied_at ? (
            <>
              <p>
                Zastosowanie zastąpi dane i pozycje szkicu, również ręczne i
                niezapisane poprawki. Wydatek zapiszesz osobno, zatwierdzając
                paragon.
              </p>
              <button
                className="button primary"
                onClick={apply}
                disabled={command.busy}
              >
                Zastosuj odczyt do szkicu
              </button>
            </>
          ) : (
            <p>Ten wynik był już zastosowany do paragonu.</p>
          )}
        </div>
      )}
      {!!receipt.ocr_attempts?.length && (
        <details>
          <summary>
            Historia odczytów ({receipt.ocr_attempts.length} ostatnich)
          </summary>
          <ul className="ocr-history">
            {receipt.ocr_attempts.map((row) => (
              <li key={row.id}>
                <div>
                  <strong>
                    {providerName(row.provider)} · {statusName[row.status]}
                  </strong>
                  <small>
                    {new Date(row.created_at).toLocaleString("pl-PL", {
                      timeZone: "Europe/Warsaw",
                    })}{" "}
                    · {(row.duration_ms / 1000).toFixed(1)} s
                    {row.diagnostics.code && ` · ${row.diagnostics.code}`}
                    {row.diagnostics.http_status &&
                      ` · HTTP ${row.diagnostics.http_status}`}
                  </small>
                </div>
                <button
                  className="text-button"
                  disabled={command.busy}
                  onClick={() => inspect(row.id)}
                >
                  Szczegóły próby
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
