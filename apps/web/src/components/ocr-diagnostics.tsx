"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, ErrorMessage } from "./ui";

type Summary = {
  days: number;
  total: number;
  truncated: boolean;
  groups: {
    provider: string;
    model: string;
    status: string;
    kind: string;
    code: string;
    http_status: number | null;
    count: number;
  }[];
};

export function OCRDiagnostics() {
  const query = useQuery({
    queryKey: ["admin-ocr-summary"],
    queryFn: () => api<Summary>("/admin/ocr-summary"),
  });
  const failures =
    query.data?.groups
      .filter((g) => g.status === "failed")
      .reduce((sum, g) => sum + g.count, 0) || 0;
  const partial =
    query.data?.groups
      .filter((g) => g.status === "partial")
      .reduce((sum, g) => sum + g.count, 0) || 0;
  return (
    <Card className="receipt-ocr">
      <div className="section-title">
        <h2>Diagnostyka OCR</h2>
        <button
          className="button secondary"
          onClick={() => query.refetch()}
          disabled={query.isFetching}
        >
          Odśwież statystyki
        </button>
      </div>
      <p>
        Zestawienie Gemini i OpenAI z ostatnich 7 dni, bez zdjęć ani danych
        finansowych. Historia zaczyna się od wdrożenia tej funkcji.
      </p>
      {query.isPending && <p role="status">Wczytuję statystyki…</p>}
      <ErrorMessage error={query.isError ? query.error.message : ""} />
      {query.data && (
        <>
          <p>
            Próby: <strong>{query.data.total}</strong> · Błędy:{" "}
            <strong>{failures}</strong>
            {query.data.total > 0 &&
              ` (${Math.round((failures * 100) / query.data.total)}%)`}{" "}
            · Niepełne odczyty: <strong>{partial}</strong>
          </p>
          {query.data.truncated && (
            <p>Zestawienie obejmuje ostatnie 10 000 prób z tego okresu.</p>
          )}
          {!query.data.total ? (
            <p>Nie ma jeszcze zarejestrowanych prób Gemini ani OpenAI.</p>
          ) : (
            <ul className="ocr-history">
              {query.data.groups.map((group, index) => (
                <li key={index}>
                  <div>
                    <strong>
                      {group.provider === "gemini" ? "Gemini" : "OpenAI"} ·{" "}
                      {group.model}
                    </strong>
                    <small>
                      {group.status === "succeeded"
                        ? "Odczytano"
                        : group.status === "partial"
                          ? "Niepełny odczyt"
                          : "Błąd"}{" "}
                      · {group.code}
                      {group.http_status != null &&
                        ` · HTTP ${group.http_status}`}
                    </small>
                  </div>
                  <strong>{group.count}</strong>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}
