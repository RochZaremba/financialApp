"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Card, ErrorMessage, Field, Submit } from "./ui";
import { api, json } from "@/lib/api";

export function RecoveryScreen() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("password") || "");
    const confirmation = String(data.get("confirmation") || "");
    setError("");
    if (password !== confirmation) {
      setError("Hasła muszą być takie same.");
      return;
    }
    setBusy(true);
    try {
      await api(
        "/auth/recover",
        json("POST", {
          email: data.get("email"),
          key: String(data.get("key") || "").trim(),
          password,
          password_confirmation: confirmation,
        }),
      );
      form.reset();
      setDone(true);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Nie udało się zmienić hasła. Spróbuj ponownie.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-wrap">
      <Card>
        <h1>{done ? "Hasło zmienione" : "Odzyskaj dostęp"}</h1>
        {done ? (
          <>
            <p role="status">
              Zaloguj się nowym hasłem. Klucz został wykorzystany, a poprzednie
              sesje wylogowane.
            </p>
            <Link className="button primary" href="/">
              Przejdź do logowania
            </Link>
          </>
        ) : (
          <>
            <p>
              Wpisz jednorazowy klucz otrzymany od właściciela aplikacji i ustaw
              nowe hasło. Klucz działa tylko dla wskazanego konta i przez
              ograniczony czas.
            </p>
            <form onSubmit={submit}>
              <Field
                label="Adres e-mail"
                name="email"
                type="email"
                autoComplete="username"
                required
                maxLength={254}
                disabled={busy}
              />
              <Field
                label="Klucz odzyskiwania"
                name="key"
                type="password"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                required
                minLength={40}
                maxLength={160}
                disabled={busy}
              />
              <Field
                label="Nowe hasło"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={10}
                maxLength={128}
                hint="Co najmniej 10 znaków."
                disabled={busy}
              />
              <Field
                label="Powtórz nowe hasło"
                name="confirmation"
                type="password"
                autoComplete="new-password"
                required
                minLength={10}
                maxLength={128}
                disabled={busy}
              />
              <ErrorMessage error={error} />
              <Submit busy={busy}>Ustaw nowe hasło</Submit>
            </form>
            <Link className="text-button" href="/">
              Wróć do logowania
            </Link>
          </>
        )}
      </Card>
    </main>
  );
}
