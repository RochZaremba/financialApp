"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, json } from "@/lib/api";
import { money, warsawDate } from "@/lib/money";
import { useApp, useCommand } from "./context";
import { Card, ErrorMessage, Field, Select, Skeleton, Submit } from "./ui";
import { PageHeading } from "./budget-screens";

type Tx = {
  id: string;
  kind: string;
  amount: number;
  date: string;
  description: string;
  updated_at: string;
};
type Entry = {
  id: string;
  bank_account_id: string;
  date: string;
  amount: number;
  description: string;
  reliable: boolean;
  reviewed: boolean;
  updated_at: string;
  transaction: Tx | null;
  candidates: Tx[];
};
type BankAccount = {
  id: string;
  last4: string;
  currency: string;
  account_id: string | null;
  start_date: string | null;
  bank_balance: number | null;
  app_balance: number | null;
  difference: number | null;
  balance_at: string | null;
};
type Connection = {
  id: string;
  status: string;
  valid_until: string | null;
  last_sync: string | null;
  next_sync: string | null;
  error_code: string | null;
  sync_available: boolean;
  sync_diagnostic: {
    stage: string;
    exception_type: string;
    code: string;
    http_status: number | null;
    occurred_at: string;
    duration_ms: number;
  } | null;
};
type BankState =
  | { enabled: false; can_activate?: boolean }
  | {
      enabled: true;
      background_enabled: boolean;
      owner: boolean;
      vapid_public_key: string;
      connections: Connection[];
      accounts: BankAccount[];
      entries: Entry[];
      truncated: boolean;
      subscriptions: { id: string; created_at: string }[];
    };
function useBank(live = false) {
  const { household } = useApp();
  return useQuery({
    queryKey: ["bank", household],
    queryFn: () => api<BankState>(`/households/${household}/bank`),
    staleTime: 15000,
    refetchInterval: live ? 30000 : false,
  });
}

const syncStages: Record<string, string> = {
  load_accounts: "Przygotowanie synchronizacji",
  decrypt_account: "Odczyt zapisanego połączenia",
  fetch_transactions: "Pobieranie operacji",
  parse_transactions: "Sprawdzanie operacji",
  fetch_balances: "Pobieranie salda",
  parse_balances: "Sprawdzanie salda",
  authorize_write: "Sprawdzanie dostępu przed zapisem",
  save_entries: "Zapisywanie operacji",
  save_balances: "Zapisywanie salda",
  commit: "Zatwierdzanie zapisu",
};

function SyncFailure({ connection }: { connection: Connection }) {
  const code = connection.error_code;
  if (!code) return null;
  const diagnostic = connection.sync_diagnostic;
  const message = ["BANK_TIMEOUT", "ASPSP_TIMEOUT"].includes(code)
    ? "Bank nie odpowiedział w wymaganym czasie."
    : [
          "EXPIRED_SESSION",
          "SESSION_EXPIRED",
          "REVOKED_SESSION",
          "CLOSED_SESSION",
        ].includes(code)
      ? "Zgoda bankowa wygasła lub została cofnięta. Odnów połączenie."
      : code === "ASPSP_RATE_LIMIT_EXCEEDED"
        ? "Bank ograniczył liczbę prób pobierania."
        : [
              "INVALID_BANK_RESPONSE",
              "INVALID_BANK_MOVEMENT",
              "INVALID_BANK_AMOUNT",
              "INVALID_BANK_DATE",
            ].includes(code)
          ? "Nie udało się odczytać danych otrzymanych z banku."
          : "Synchronizacja nie powiodła się.";
  return (
    <div className="bank-sync-failure">
      <p role="alert">{message} Poprzednie dane zachowano.</p>
      <details className="bank-diagnostic">
        <summary>Szczegóły błędu synchronizacji</summary>
        {diagnostic ? (
          <dl>
            <div>
              <dt>Etap</dt>
              <dd>{syncStages[diagnostic.stage] || "Synchronizacja"}</dd>
            </div>
            <div>
              <dt>Rodzaj błędu</dt>
              <dd>{diagnostic.exception_type}</dd>
            </div>
            <div>
              <dt>Kod</dt>
              <dd>{diagnostic.code}</dd>
            </div>
            {diagnostic.http_status !== null && (
              <div>
                <dt>Odpowiedź HTTP</dt>
                <dd>{diagnostic.http_status}</dd>
              </div>
            )}
            <div>
              <dt>Czas próby</dt>
              <dd>{stamp(diagnostic.occurred_at)}</dd>
            </div>
            <div>
              <dt>Czas trwania</dt>
              <dd>
                {new Intl.NumberFormat("pl-PL", {
                  maximumFractionDigits: 1,
                }).format(diagnostic.duration_ms / 1000)}{" "}
                s
              </dd>
            </div>
          </dl>
        ) : (
          <>
            <p>Kod: {code}.</p>
            <p>
              Ta starsza próba nie ma zapisanych szczegółów. Pojawią się po
              kolejnej nieudanej próbie.
            </p>
          </>
        )}
      </details>
    </div>
  );
}
function stamp(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("pl-PL", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Europe/Warsaw",
      }).format(new Date(value))
    : "Jeszcze nie pobrano";
}

export function BankShortcut() {
  const state = useBank();
  if (!state.data?.enabled)
    return state.data && !state.data.enabled && state.data.can_activate ? (
      <Card className="bank-shortcut">
        <h2>Połączenie z bankiem</h2>
        <p>Możesz jednorazowo włączyć prywatny bank dla tego domu.</p>
        <Link href="/bank" className="button primary">
          Skonfiguruj bank
        </Link>
      </Card>
    ) : null;
  const count = state.data.entries.filter((e) => !e.reviewed).length;
  return (
    <Card className="bank-shortcut">
      <h2>Wasz bank</h2>
      <p>
        {count
          ? `${count} operacji do opisania lub dopasowania.`
          : "Sprawdź synchronizację i zgodność salda."}
      </p>
      <Link className="button primary" href="/bank">
        Otwórz bank
      </Link>
    </Card>
  );
}

export function BankCallback({
  code,
  state,
  error,
  onComplete,
}: {
  code: string | null;
  state: string | null;
  error: string | null;
  onComplete: (household: string) => void;
}) {
  const started = useRef(false);
  const [message, setMessage] = useState(
    error
      ? "Połączenie zostało przerwane w banku. Możesz rozpocząć je ponownie."
      : "",
  );
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    window.history.replaceState({}, "", window.location.pathname);
    if (error || !code || !state) return;
    api<{ household_id: string }>(
      "/bank/complete",
      json("POST", { code, state }),
    )
      .then((result) => onComplete(result.household_id))
      .catch(() =>
        setMessage(
          "Nie udało się ukończyć połączenia. Rozpocznij je ponownie w ekranie banku.",
        ),
      );
  }, [code, state, error, onComplete]);
  return (
    <Card>
      <h1>Połączenie z bankiem</h1>
      {message ? (
        <>
          <ErrorMessage error={message} />
          <Link
            href="/bank"
            className="button secondary"
            onClick={() => window.location.assign("/bank")}
          >
            Wróć do banku
          </Link>
        </>
      ) : (
        <p role="status">Kończę bezpieczne połączenie…</p>
      )}
    </Card>
  );
}

export function BankScreen() {
  const { household } = useApp();
  const state = useBank(true);
  const command = useCommand();
  const [history, setHistory] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  if (state.isPending) return <Skeleton />;
  if (state.isError)
    return (
      <Card>
        <ErrorMessage error={state.error.message} />
        <button className="button secondary" onClick={() => state.refetch()}>
          Spróbuj ponownie
        </button>
      </Card>
    );
  if (!state.data.enabled && state.data.can_activate) return <BankActivation />;
  if (!state.data.enabled)
    return (
      <Card>
        <h1>Bank nie jest włączony dla tego domu.</h1>
        <p>
          Integrację uruchamia właściciel wdrożenia dla wskazanego domostwa.
        </p>
        <Link href="/konta">Wróć do kont</Link>
      </Card>
    );
  const data = state.data,
    base = `/households/${household}/bank`;
  const current = data.connections.find((c) => c.status === "active");
  const latest =
    current || data.connections.find((c) => c.status === "expired");
  const unreviewed = data.entries.filter((e) => !e.reviewed);
  async function connect() {
    await command.run(
      () => api<{ url: string }>(base + "/connect", { method: "POST" }),
      "Przechodzę do banku",
      (result) => window.location.assign(result.url),
    );
  }
  async function refresh() {
    setSyncMessage("");
    const result = await command.run(
      () =>
        api<{ message: string; failed: number }>(base + "/sync", {
          method: "POST",
        }),
      null,
    );
    if (result && !result.failed) setSyncMessage(result.message);
  }
  async function disconnect(connection: Connection) {
    if (
      !window.confirm(
        "Odłączyć bank? Pobieranie ustanie, zapisane operacje pozostaną w aplikacji.",
      )
    )
      return;
    await command.run(
      () => api(`${base}/connections/${connection.id}`, { method: "DELETE" }),
      "Zlecono odłączenie banku",
    );
  }
  return (
    <>
      <PageHeading
        title="Bank i zgodność salda."
        description="Operacje z banku, ich opisy i paragony — bez ponownego księgowania tego samego zakupu."
      />
      <ErrorMessage error={command.error} />
      <Card className="bank-status">
        <h2>Połączenie mBank</h2>
        <p>
          Dostęp do informacji o rachunkach. Ta integracja nie zleca przelewów
          bankowych.
        </p>
        {latest ? (
          <>
            <p>
              Ostatnia synchronizacja:{" "}
              <strong>{stamp(latest.last_sync)}</strong>
            </p>
            {current?.next_sync && (
              <p>Następna próba: {stamp(current.next_sync)}</p>
            )}
            <p>Zgoda ważna do: {stamp(latest.valid_until)}</p>
            <SyncFailure connection={latest} />
          </>
        ) : (
          <p>
            Połącz bank i zatwierdź udostępnienie rachunku w oficjalnym
            formularzu.
          </p>
        )}
        {!data.background_enabled && (
          <p className="notice warning">
            To środowisko testowe — synchronizacja w tle nie jest uruchomiona. W
            produkcji działa automatycznie.
          </p>
        )}
        <p className="muted small">
          Próby pobierania dzieli co najmniej 6 godzin, także po błędzie. W
          produkcji kolejna próba ruszy automatycznie. Powiadomienie przyjdzie
          po udostępnieniu operacji przez bank. Blokady kartowe nie są
          księgowane jako wydatki.
        </p>
        {data.owner && (
          <div className="bank-actions">
            <button
              className={current ? "button secondary" : "button primary"}
              disabled={command.busy}
              onClick={connect}
            >
              {current ? "Odnów zgodę / dodaj rachunek" : "Połącz mBank"}
            </button>
            {current && (
              <button
                className="button primary"
                disabled={command.busy || !current.sync_available}
                onClick={refresh}
              >
                Synchronizuj teraz
              </button>
            )}
          </div>
        )}
        {syncMessage && <p role="status">{syncMessage}</p>}
        {current && data.accounts.every((account) => !account.account_id) && (
          <p className="muted">
            Przypisz rachunek poniżej, aby rozpocząć pobieranie.
          </p>
        )}
        {data.owner &&
          data.connections
            .filter((c) =>
              [
                "active",
                "expired",
                "revoke_pending",
                "pending",
                "exchanging",
              ].includes(c.status),
            )
            .map((c) => (
              <div className="bank-connection" key={c.id}>
                <span>
                  {c.status === "revoke_pending"
                    ? "Cofanie dostępu — poczekaj na potwierdzenie"
                    : c.status === "expired"
                      ? "Zgoda wygasła"
                      : c.status === "active"
                        ? "Połączono"
                        : "Rozpoczęte połączenie"}
                </span>
                <button
                  className="button secondary"
                  disabled={command.busy}
                  onClick={() => disconnect(c)}
                >
                  Odłącz
                </button>
              </div>
            ))}
        <button className="text-button" onClick={() => state.refetch()}>
          Odśwież listę i status
        </button>
      </Card>
      {data.accounts.map((account) => (
        <AccountMapping key={account.id} bank={account} owner={data.owner} />
      ))}
      <PushSettings data={data} />
      <Card className="bank-inbox">
        <div className="section-title">
          <h2>Do uzupełnienia ({unreviewed.length})</h2>
          <button
            className="button secondary"
            aria-pressed={history}
            onClick={() => setHistory(!history)}
          >
            {history ? "Tylko do uzupełnienia" : "Pokaż historię"}
          </button>
        </div>
        <p className="muted small">
          Pierwszy import, starsze wpisy i możliwe duplikaty wymagają
          sprawdzenia. Nowe, jednoznaczne wydatki trafiają automatycznie do
          budżetu bez kategorii. Wpływ może być dochodem, zwrotem lub przelewem
          własnym — najpierw go opisz. Salda nie są automatycznie korygowane.
        </p>
        {data.truncated && (
          <p>
            Pokazujemy do 500 operacji, najpierw nieuzupełnione. Cała historia
            jest w eksporcie domu.
          </p>
        )}
        {(history ? data.entries : unreviewed).length === 0 ? (
          <p>Nie ma nowych operacji do uzupełnienia.</p>
        ) : (
          (history ? data.entries : unreviewed).map((entry) => (
            <EntryCard
              key={`${entry.id}:${entry.updated_at}`}
              entry={entry}
              bank={data.accounts.find((a) => a.id === entry.bank_account_id)!}
            />
          ))
        )}
      </Card>
    </>
  );
}

function AccountMapping({
  bank,
  owner,
}: {
  bank: BankAccount;
  owner: boolean;
}) {
  const { data, household } = useApp();
  const command = useCommand();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    await command.run(
      () =>
        api(
          `/households/${household}/bank/accounts/${bank.id}`,
          json("PUT", {
            account_id: f.get("account"),
            start_date: f.get("date"),
          }),
        ),
      "Przypisano rachunek",
    );
  }
  return (
    <Card className="bank-account">
      <h2>
        Rachunek kończący się na {bank.last4 || "••••"} · {bank.currency}
      </h2>
      {bank.account_id ? (
        <>
          <p>
            Konto aplikacji:{" "}
            {data.accounts.find((a) => a.id === bank.account_id)?.name ||
              "Konto"}
          </p>
          <div className="bank-balances">
            <div>
              <span>Saldo księgowe banku</span>
              <strong>
                {bank.bank_balance == null
                  ? "Brak danych"
                  : money(bank.bank_balance)}
              </strong>
            </div>
            <div>
              <span>Saldo aplikacji</span>
              <strong>
                {bank.app_balance == null ? "—" : money(bank.app_balance)}
              </strong>
            </div>
            <div>
              <span>Różnica do wyjaśnienia</span>
              <strong>
                {bank.difference == null ? "—" : money(bank.difference)}
              </strong>
            </div>
          </div>
          <p className="muted small">
            Dane banku: {stamp(bank.balance_at)}. Sprawdź nieuzupełnione
            operacje i saldo początkowe. Różnicy nie zerujemy automatycznie.
          </p>
        </>
      ) : owner ? (
        <form onSubmit={submit}>
          <p>
            Wybierz odpowiadające konto w aplikacji. Pierwszy import historii
            nie wysyła powiadomień i nie zakłada, że każda operacja jest nowym
            wydatkiem.
          </p>
          <Select label="Konto aplikacji dla rachunku" name="account" required>
            <option value="">Wybierz konto</option>
            {data.accounts
              .filter(
                (a) => a.currency === bank.currency && a.currency === "PLN",
              )
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
          </Select>
          <Field
            label="Pobierz historię od"
            name="date"
            type="date"
            defaultValue={warsawDate()}
            max={warsawDate()}
            required
          />
          <p className="muted small">
            Maksymalnie 90 dni wstecz, zależnie od banku. Dla drugiego rachunku
            dodaj najpierw osobne konto w aplikacji. Obecnie księgowanie bankowe
            obsługuje PLN.
          </p>
          <ErrorMessage error={command.error} />
          <Submit busy={command.busy}>Przypisz rachunek</Submit>
        </form>
      ) : (
        <p>Właściciel domu musi przypisać rachunek do konta aplikacji.</p>
      )}
    </Card>
  );
}

function EntryCard({ entry, bank }: { entry: Entry; bank: BankAccount }) {
  const { household, data } = useApp();
  const command = useCommand();
  const [description, setDescription] = useState(
    entry.transaction?.description || entry.description,
  );
  const [action, setAction] = useState(
    entry.transaction ? "describe" : entry.candidates.length ? "match" : "new",
  );
  const [category, setCategory] = useState("");
  const [target, setTarget] = useState(entry.candidates[0]?.id || "");
  const [destination, setDestination] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !window.confirm(
        "Potwierdzasz opis i wybrany sposób rozliczenia operacji?",
      )
    )
      return;
    await command.run(
      () =>
        api(
          `/households/${household}/bank/entries/${entry.id}/resolve`,
          json("POST", {
            action,
            description,
            expected_updated_at: entry.updated_at,
            expected_transaction_updated_at:
              entry.transaction?.updated_at || null,
            transaction_id: target || null,
            destination_id: destination || null,
            allocations:
              category && entry.amount < 0
                ? [{ category_id: category, amount: -entry.amount }]
                : [],
          }),
        ),
      "Operacja uzupełniona",
    );
  }
  return (
    <article className="bank-entry">
      <div className="section-title">
        <h3>
          {entry.amount < 0 ? "Wydatek" : "Wpływ"} · {entry.date}
        </h3>
        <strong>{money(entry.amount)}</strong>
      </div>
      <p>{entry.description}</p>
      <small>
        Rachunek …{bank.last4}
        {entry.reviewed ? " · Uzupełniono" : " · Do uzupełnienia"}
      </small>
      {!entry.reliable && (
        <p className="notice warning">
          Bank nie podał stałego identyfikatora. Sprawdź historię i możliwe
          duplikaty przed księgowaniem.
        </p>
      )}
      {entry.transaction && (
        <p>Jest już w aplikacji. Opis lub paragon uzupełnią istniejący wpis.</p>
      )}
      <details>
        <summary>Opisz lub dopasuj operację</summary>
        <form onSubmit={save}>
          <Field
            label="Opis operacji bankowej"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={160}
            required
          />
          <Select
            label="Sposób rozliczenia"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          >
            {!entry.transaction && (
              <option value="new">
                {entry.amount < 0
                  ? "Nowy wydatek — osobny zakup"
                  : "Nowy dochód — potwierdzam źródło"}
              </option>
            )}
            {entry.transaction && (
              <option value="describe">Uzupełnij istniejący wpis</option>
            )}
            {!entry.transaction && entry.candidates.length > 0 && (
              <option value="match">To istniejący wpis / paragon</option>
            )}
            <option value="transfer">Przelew pomiędzy własnymi kontami</option>
          </Select>
          {action === "match" && (
            <Select
              label="Dopasowana transakcja"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              required
            >
              {entry.candidates.map((tx) => (
                <option key={tx.id} value={tx.id}>
                  {tx.date} · {tx.description} · {money(tx.amount)}
                </option>
              ))}
            </Select>
          )}
          {action === "transfer" && (
            <Select
              label="Drugie własne konto"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              required
            >
              <option value="">Wybierz konto</option>
              {data.accounts
                .filter((a) => a.id !== bank.account_id && a.currency === "PLN")
                .map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
            </Select>
          )}
          {action !== "transfer" && action !== "match" && entry.amount < 0 && (
            <Select
              label="Kategoria wydatku bankowego"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">
                Uzupełnię kategorię lub dodam paragon później
              </option>
              {data.categories
                .filter((c) => !c.archived)
                .map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.name}
                  </option>
                ))}
            </Select>
          )}
          <ErrorMessage error={command.error} />
          <Submit busy={command.busy}>Potwierdź operację</Submit>
        </form>
      </details>
      {entry.transaction?.kind === "expense" && (
        <div className="bank-actions">
          <Link className="button secondary" href="/dodaj">
            Dodaj paragon do tego wydatku
          </Link>
          <Link
            className="text-button"
            href={`/transakcje?item=${entry.transaction.id}`}
          >
            Zobacz wpis / podział kategorii
          </Link>
        </div>
      )}
    </article>
  );
}

function PushSettings({
  data,
}: {
  data: Extract<BankState, { enabled: true }>;
}) {
  const { household } = useApp();
  const command = useCommand();
  async function enable() {
    await command.run(async () => {
      if (
        !("Notification" in window) ||
        !("serviceWorker" in navigator) ||
        !("PushManager" in window)
      )
        throw new Error(
          "Ta przeglądarka nie obsługuje powiadomień. Na iPhonie dodaj Razem do ekranu początkowego i otwórz z ikony.",
        );
      const permission = await Notification.requestPermission();
      if (permission !== "granted")
        throw new Error(
          "Powiadomienia nie zostały włączone. Zgodę możesz zmienić w ustawieniach telefonu.",
        );
      await navigator.serviceWorker.register("/sw.js");
      const reg = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise<never>((_, reject) =>
          setTimeout(
            () =>
              reject(
                new Error(
                  "Nie udało się uruchomić powiadomień. Odśwież aplikację.",
                ),
              ),
            10000,
          ),
        ),
      ]);
      const key = Uint8Array.from(
        atob(data.vapid_public_key.replace(/-/g, "+").replace(/_/g, "/")),
        (c) => c.charCodeAt(0),
      );
      const sub =
        (await reg.pushManager.getSubscription()) ||
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: key,
        }));
      const payload = sub.toJSON();
      await api(
        `/households/${household}/bank/subscriptions`,
        json("POST", { endpoint: sub.endpoint, keys: payload.keys }),
      );
    }, "Powiadomienia bankowe włączone");
  }
  return (
    <Card className="bank-push">
      <h2>Powiadomienia na telefon</h2>
      <p>
        Nowy wpis z banku przypomni o opisie lub paragonie. Na ekranie blokady
        nie pokazujemy kwot ani nazw odbiorców.
      </p>
      <p className="muted small">
        Android: zezwól przeglądarce na powiadomienia. iPhone (iOS 16.4+):
        udostępnij → Do ekranu początkowego, otwórz z ikony i włącz tutaj.
        Synchronizacja działa na serwerze, także przy zamkniętej aplikacji.
      </p>
      <ErrorMessage error={command.error} />
      <button
        className="button primary"
        disabled={command.busy}
        onClick={enable}
      >
        Włącz na tym urządzeniu
      </button>
      {data.subscriptions.map((sub, index) => (
        <div className="bank-connection" key={sub.id}>
          <span>
            Urządzenie {index + 1} · {stamp(sub.created_at)}
          </span>
          <button
            className="button secondary"
            disabled={command.busy}
            onClick={() =>
              command.run(
                () =>
                  api(`/households/${household}/bank/subscriptions/${sub.id}`, {
                    method: "DELETE",
                  }),
                "Odłączono urządzenie",
              )
            }
          >
            Odłącz urządzenie
          </button>
        </div>
      ))}
    </Card>
  );
}

export function BankReceiptMatch({
  amount,
  accountId,
  date,
  selected,
  onSeparate,
  onSelect,
}: {
  amount: number;
  accountId: string;
  date: string;
  selected: string;
  onSeparate: (value: boolean) => void;
  onSelect: (target: Tx | null) => void;
}) {
  const { household } = useApp();
  const bank = useBank();
  const choices = useQuery({
    queryKey: ["bank-receipt", household, amount, accountId, date],
    queryFn: () =>
      api<Tx[]>(
        `/households/${household}/bank/receipt-matches?amount=${amount}&account_id=${encodeURIComponent(accountId)}&receipt_date=${date}`,
      ),
    enabled:
      !!bank.data?.enabled &&
      amount > 0 &&
      !!accountId &&
      /^\d{4}-\d{2}-\d{2}$/.test(date),
  });
  if (!bank.data?.enabled || !choices.data?.length) return null;
  return (
    <div className="bank-receipt-match">
      <Select
        label="Czy to płatność już pobrana z banku?"
        value={selected}
        onChange={(event) => {
          onSeparate(event.target.value === "new");
          onSelect(
            choices.data?.find((tx) => tx.id === event.target.value) || null,
          );
        }}
      >
        <option value="">Wybierz dopasowanie</option>
        <option value="new">To osobny zakup — zapisz drugi wydatek</option>
        {choices.data.map((tx) => (
          <option key={tx.id} value={tx.id}>
            {tx.date} · {tx.description} · {money(tx.amount)}
          </option>
        ))}
      </Select>
      <p className="notice warning">
        Wybierz płatność bankową, jeśli to ten sam zakup. Paragon uzupełni jej
        kategorie bez drugiego wydatku.
      </p>
    </div>
  );
}

function BankActivation() {
  const { data, household } = useApp();
  const command = useCommand();
  const [file, setFile] = useState<File | null>(null);
  const [appId, setAppId] = useState("");
  async function activate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await command.run(async () => {
      if (!file || file.size > 16384)
        throw new Error("Wybierz plik PEM do 16 KB.");
      return api(
        `/households/${household}/bank/activate`,
        json("POST", {
          app_id: appId,
          household_name: values.get("household"),
          password: values.get("password"),
          private_key: await file.text(),
          confirm_share: values.get("consent") === "on",
        }),
      );
    }, "Prywatny bank przypisano do tego domu");
    const password = form.elements.namedItem(
      "password",
    ) as HTMLInputElement | null;
    if (password) password.value = "";
  }
  return (
    <>
      <PageHeading
        title="Prywatne połączenie bankowe."
        description={`Jednorazowe przypisanie do domu: ${data.household.name}.`}
      />
      <Card className="bank-activation">
        <p>
          Dostęp otrzymają wyłącznie obecni domownicy:{" "}
          <strong>{data.members.map((m) => m.name).join(", ")}</strong>.
          Wymagane są dokładnie dwie osoby.
        </p>
        <p>
          Klucz jest przesyłany bezpośrednio do tej aplikacji przez HTTPS i
          zapisany w prywatnym magazynie serwera. Panel nie pozwoli później
          zmienić przypisanego domu ani nadpisać klucza.
        </p>
        <form onSubmit={activate}>
          <fieldset disabled={command.busy}>
            <label className="field meter-file-field">
              <span>Plik prywatnego klucza Enable Banking</span>
              <input
                aria-label="Plik prywatnego klucza Enable Banking"
                className="meter-file-input"
                type="file"
                accept=".pem,.key,.txt"
                onChange={(event) => {
                  const selected = event.target.files?.[0] || null;
                  setFile(selected);
                  const match = selected?.name.match(
                    /[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}/i,
                  );
                  if (match) setAppId(match[0]);
                }}
                required
              />
              <span className="button secondary">Wybierz plik klucza</span>
              <small>{file?.name || "Nie wybrano pliku"}</small>
            </label>
            <Field
              label="Identyfikator aplikacji Enable Banking"
              value={appId}
              onChange={(event) => setAppId(event.target.value)}
              maxLength={36}
              required
            />
            <Field
              label="Potwierdź pełną nazwę tego domu"
              name="household"
              placeholder={data.household.name}
              maxLength={80}
              required
            />
            <Field
              label="Hasło administratora będącego właścicielem domu"
              name="password"
              type="password"
              autoComplete="current-password"
              minLength={10}
              maxLength={128}
              required
            />
            <label className="checkbox-field">
              <input name="consent" type="checkbox" required />
              Udostępniam informacje z rachunku dwóm wymienionym domownikom w
              tym domu.
            </label>
            <ErrorMessage error={command.error} />
            <Submit busy={command.busy}>Aktywuj tylko dla tego domu</Submit>
          </fieldset>
        </form>
        <p className="muted small">
          Po aktywacji wybierzesz „Połącz mBank” i zatwierdzisz dostęp w banku.
          Pierwszy krok sprawdza aplikację AIS, nie importuje transakcji.
        </p>
      </Card>
    </>
  );
}
