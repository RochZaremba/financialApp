"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2, Unplug } from "lucide-react";
import { api, json } from "@/lib/api";
import { useApp, useCommand } from "./context";
import { Card, ErrorMessage, Field, Select, Submit } from "./ui";

type Connection = {
  id: string;
  name: string;
  access: "read" | "write";
  expires_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
};

function date(value: string) {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeZone: "Europe/Warsaw",
  }).format(new Date(value));
}

export function ConnectionsPanel() {
  const { household, notify } = useApp();
  const command = useCommand();
  const query = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState("");
  const [revoking, setRevoking] = useState<Connection | null>(null);
  const base = `/households/${household}/connections`;
  const connections = useQuery({
    queryKey: ["connections", household],
    queryFn: () => api<Connection[]>(base),
  });
  const endpoint =
    typeof window === "undefined"
      ? "/api/mcp"
      : `${window.location.origin}/api/mcp`;
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      notify("Skopiowano");
    } catch {
      command.setError("Skopiuj wartość ręcznie z pola.");
    }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await command.run(
      () =>
        api<{ token: string }>(
          base,
          json("POST", {
            name: values.get("name"),
            access: values.get("access"),
            days: Number(values.get("days")),
            password: values.get("password"),
          }),
        ),
      "Połączenie jest gotowe",
      (result) => {
        form.reset();
        setSecret(result.token);
        setCreating(false);
        void query.invalidateQueries({ queryKey: ["connections", household] });
      },
    );
  }
  async function revoke() {
    if (!revoking) return;
    await command.run(
      () => api(`${base}/${revoking.id}`, { method: "DELETE" }),
      "Połączenie odłączone",
      () => {
        setRevoking(null);
        setSecret("");
        void query.invalidateQueries({ queryKey: ["connections", household] });
      },
    );
  }
  return (
    <Card className="connections-panel" key={household}>
      <div className="section-title">
        <h2>Połączenia z AI</h2>
        <Link2 size={20} aria-hidden="true" />
      </div>
      <p className="muted">
        Połącz swój program AI przez MCP. Może przeglądać dom, a za Twoją zgodą
        także zapisywać odczyty, wydatki i pozostałe dane.
      </p>
      <ErrorMessage
        error={
          connections.error?.message ||
          (!creating && !revoking ? command.error : "")
        }
      />
      <Field
        label="Adres serwera MCP"
        value={endpoint}
        readOnly
        onFocus={(event) => event.target.select()}
      />
      <button className="button secondary" onClick={() => copy(endpoint)}>
        <Copy size={16} /> Kopiuj adres MCP
      </button>
      <p className="muted small">
        Transport Streamable HTTP, klucz w nagłówku Authorization: Bearer.
        Współpracuje z Codex i klientami obsługującymi własny nagłówek.
        Połączenie ChatGPT lub Claude wymagające logowania OAuth nie jest
        jeszcze dostępne.
      </p>
      {secret && (
        <div className="notice">
          <strong>Zapisz klucz — pokazujemy go tylko teraz.</strong>
          <p>
            Wklej go w ustawienia połączenia swojego AI. Daje dostęp do danych
            tego domu.
          </p>
          <Field
            label="Nowy klucz połączenia AI"
            value={secret}
            readOnly
            onFocus={(event) => event.target.select()}
          />
          <div className="button-row">
            <button className="button secondary" onClick={() => copy(secret)}>
              <Copy size={16} /> Kopiuj klucz
            </button>
            <button className="button secondary" onClick={() => setSecret("")}>
              Zapisane, ukryj klucz
            </button>
          </div>
        </div>
      )}
      {!creating && !secret && (
        <button className="button primary" onClick={() => setCreating(true)}>
          Dodaj połączenie AI
        </button>
      )}
      {creating && (
        <form onSubmit={create}>
          <fieldset disabled={command.busy}>
            <Field
              label="Nazwa połączenia"
              name="name"
              placeholder="Np. mój Codex"
              required
              maxLength={80}
            />
            <Select label="Dostęp AI" name="access" defaultValue="read">
              <option value="read">Tylko odczyt</option>
              <option value="write">Odczyt i zapis</option>
            </Select>
            <Select label="Ważność klucza" name="days" defaultValue="30">
              <option value="7">7 dni</option>
              <option value="30">30 dni</option>
              <option value="90">90 dni</option>
            </Select>
            <p className="muted small">
              Zapis pozwala również poprawiać i usuwać wpisy. Wywołania OCR mogą
              korzystać z płatnego AI. Połączenie działa jako Ty w tym domu.
            </p>
            <Field
              label="Potwierdź swoim hasłem"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              minLength={10}
              maxLength={128}
            />
            <ErrorMessage error={command.error} />
            <div className="button-row">
              <Submit busy={command.busy}>Utwórz klucz AI</Submit>
              <button
                className="button secondary"
                type="button"
                onClick={() => setCreating(false)}
              >
                Anuluj
              </button>
            </div>
          </fieldset>
        </form>
      )}
      <div className="connection-list">
        {connections.isPending && <p role="status">Wczytuję połączenia…</p>}
        {connections.data?.length === 0 && (
          <p className="muted">Nie masz jeszcze połączeń z AI w tym domu.</p>
        )}
        {connections.data?.map((item) => {
          const active =
            !item.revoked_at && new Date(item.expires_at) > new Date();
          return (
            <div className="connection-row" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <small>
                  {item.access === "write" ? "Odczyt i zapis" : "Tylko odczyt"}{" "}
                  ·{" "}
                  {item.revoked_at
                    ? "Odłączone"
                    : active
                      ? `Ważne do ${date(item.expires_at)}`
                      : "Wygasło"}
                </small>
                <small>
                  {item.last_used_at
                    ? `Ostatnio użyte: ${date(item.last_used_at)}`
                    : "Jeszcze nieużywane"}
                </small>
              </div>
              {active && (
                <button
                  className="button secondary"
                  onClick={() => setRevoking(item)}
                  aria-label={`Odłącz ${item.name}`}
                >
                  <Unplug size={16} /> Odłącz
                </button>
              )}
            </div>
          );
        })}
      </div>
      {revoking && (
        <div className="notice" role="alert">
          <strong>Odłączyć „{revoking.name}”?</strong>
          <ErrorMessage error={command.error} />
          <p>
            AI od razu straci dostęp. Zapisane wcześniej dane zostaną w
            aplikacji.
          </p>
          <div className="button-row">
            <button
              className="button danger-button"
              disabled={command.busy}
              onClick={revoke}
            >
              Odłącz połączenie
            </button>
            <button
              className="button secondary"
              disabled={command.busy}
              onClick={() => setRevoking(null)}
            >
              Anuluj
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
