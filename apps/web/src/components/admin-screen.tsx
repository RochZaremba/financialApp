"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import type { Me } from "@/lib/types";
import { api, json } from "@/lib/api";
import { Card, ErrorMessage, Field, Submit } from "./ui";
import { OCRDiagnostics } from "./ocr-diagnostics";

export function AdminScreen({
  me,
  logout,
  logoutError,
}: {
  me: Me;
  logout: () => Promise<void>;
  logoutError: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setError("");
    setSuccess("");
    if (fields.get("password") !== fields.get("confirmation")) {
      setError("Nowe hasła muszą być takie same.");
      return;
    }
    setBusy(true);
    try {
      await api(
        "/admin/password-reset",
        json("POST", {
          email: String(fields.get("email")),
          password: String(fields.get("password")),
          admin_password: String(fields.get("admin_password")),
        }),
      );
      form.reset();
      setSuccess(
        "Hasło zostało zmienione. Poprzednie sesje użytkownika są wylogowane. Przekaż nowe hasło tej osobie bezpiecznym kanałem.",
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Nie udało się zmienić hasła.",
      );
    } finally {
      // Do not retain the administrator password after a failed request.
      const input = form.elements.namedItem("admin_password");
      if (input instanceof HTMLInputElement) input.value = "";
      setBusy(false);
    }
  }

  return (
    <main className="admin-page">
      <div className="section-title">
        <Link
          className="button secondary"
          href={me.households.length ? "/" : "/dolacz"}
        >
          {me.households.length ? "Wróć do aplikacji" : "Utwórz dom"}
        </Link>
        <button className="button secondary" onClick={logout}>
          Wyloguj
        </button>
      </div>
      <ErrorMessage error={logoutError} />
      <Card>
        <h1>Panel administratora</h1>
        {me.user.is_admin ? (
          <>
            <p>
              Pomóż odzyskać dostęp do konta. Najpierw potwierdź tożsamość
              osoby, która prosi o zmianę hasła.
            </p>
            <form onSubmit={submit}>
              <Field
                label="E-mail użytkownika"
                name="email"
                type="email"
                autoComplete="off"
                maxLength={254}
                required
              />
              <Field
                label="Nowe hasło użytkownika"
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={10}
                maxLength={128}
                hint="Od 10 do 128 znaków. Zmiana wyloguje użytkownika na wszystkich urządzeniach."
                required
              />
              <Field
                label="Powtórz nowe hasło"
                name="confirmation"
                type="password"
                autoComplete="new-password"
                minLength={10}
                maxLength={128}
                required
              />
              <Field
                label="Twoje hasło administratora"
                name="admin_password"
                type="password"
                autoComplete="current-password"
                minLength={10}
                maxLength={128}
                required
              />
              <ErrorMessage error={error} />
              {success && (
                <p className="notice" role="status">
                  {success}
                </p>
              )}
              <Submit busy={busy}>Zmień hasło użytkownika</Submit>
            </form>
          </>
        ) : (
          <p role="alert">Ta strona jest dostępna tylko dla administratora.</p>
        )}
      </Card>
      {me.user.is_admin && <OCRDiagnostics />}
    </main>
  );
}
