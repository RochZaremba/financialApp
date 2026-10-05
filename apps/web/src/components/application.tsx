"use client";
import {
  useEffect,
  useState,
  useRef,
  useSyncExternalStore,
  Suspense,
  type ReactNode,
} from "react";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  House,
  Wallet,
  Plus,
  ArrowLeftRight,
  Ellipsis,
  Flag,
  ChartNoAxesCombined,
  Inbox,
  Landmark,
  Settings,
  Repeat2,
  ChevronLeft,
  ChevronRight,
  ArrowUpRight,
  LogOut,
  Check,
  WifiOff,
  ShieldCheck,
  Leaf,
  ArrowRight,
} from "lucide-react";
import { api, ApiError, json } from "@/lib/api";
import { monthName, shiftMonth, warsawDate } from "@/lib/money";
import type { Me, Overview } from "@/lib/types";
import { AppContext } from "./context";
import { Card, ErrorMessage, Field, Skeleton, Submit } from "./ui";
import {
  Home,
  BudgetScreen,
  TransactionsScreen,
  MoreScreen,
} from "./budget-screens";
import { AddScreen, ReceiptScreen, InboxScreen } from "./receipt-screens";
import {
  GoalsScreen,
  AnalyticsScreen,
  AccountsScreen,
  SettingsScreen,
  RecurringScreen,
} from "./future-screens";

const nav = [
  { href: "/", label: "Pulpit", icon: House },
  { href: "/budzet", label: "Budżet", icon: Wallet },
  { href: "/transakcje", label: "Transakcje", icon: ArrowLeftRight },
  { href: "/cele", label: "Cele", icon: Flag },
  { href: "/analiza", label: "Analiza", icon: ChartNoAxesCombined },
  { href: "/inbox", label: "Do sprawdzenia", icon: Inbox },
];
const secondary = [
  { href: "/cykliczne", label: "Stałe wydatki", icon: Repeat2 },
  { href: "/konta", label: "Konta", icon: Landmark },
  { href: "/ustawienia", label: "Ustawienia", icon: Settings },
];
function subscribeOnline(callback: () => void) {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}
function Offline() {
  const online = useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
  return online ? null : (
    <div className="offline" role="alert">
      <WifiOff size={18} />
      Sprawdź połączenie. Zapis może się nie udać.
    </div>
  );
}
export function Application({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            // Connectivity hints can be false while our API stays reachable.
            // Actual fetch results select the data/error state.
            networkMode: "always",
            retry: (count, error) =>
              !(
                error instanceof ApiError &&
                [401, 403, 404].includes(error.status)
              ) && count < 1,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Offline />
      <Suspense fallback={<Skeleton />}>
        <Authenticated />
        {children}
      </Suspense>
    </QueryClientProvider>
  );
}
function Authenticated() {
  const query = useQueryClient();
  const path = usePathname();
  const router = useRouter();
  const params = useSearchParams();
  const [selected, setSelected] = useState("");
  const [month, setMonth] = useState(() => warsawDate().slice(0, 7));
  const [toast, setToast] = useState("");
  const [logoutError, setLogoutError] = useState("");
  const auth = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api<Me>("/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });
  const household =
    auth.data?.households.find((h) => h.id === selected)?.id ||
    auth.data?.households[0]?.id;
  const overview = useQuery({
    queryKey: ["overview", household, month],
    queryFn: () =>
      api<Overview>(`/households/${household}/overview?month=${month}`),
    enabled: !!household && !!auth.data,
  });
  useEffect(() => {
    const expired = () => {
      query.setQueryData(["me"], null);
      query.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    };
    window.addEventListener("session-expired", expired);
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    return () => window.removeEventListener("session-expired", expired);
  }, [query]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(timer);
  }, [toast]);
  async function logout() {
    setLogoutError("");
    try {
      await api("/auth/logout", { method: "POST" });
      query.clear();
      router.replace("/");
    } catch (error) {
      setLogoutError(
        error instanceof Error
          ? error.message
          : "Nie udało się wylogować. Spróbuj ponownie.",
      );
    }
  }
  if (auth.isPending)
    return (
      <main className="standalone-loading">
        <Skeleton />
      </main>
    );
  if (auth.isError)
    return (
      <main className="auth-wrap">
        <Card>
          <h1>Nie możemy wczytać aplikacji</h1>
          <ErrorMessage error={auth.error.message} />
          <button className="button primary" onClick={() => auth.refetch()}>
            Spróbuj ponownie
          </button>
        </Card>
      </main>
    );
  if (!auth.data)
    return (
      <AuthScreen
        onSuccess={() => {
          query.invalidateQueries({ queryKey: ["me"] });
        }}
        invited={!!params.get("token")}
      />
    );
  if (!household || path === "/dolacz")
    return (
      <Onboarding
        token={params.get("token") || ""}
        name={auth.data.user.name}
        onSuccess={() => {
          query.invalidateQueries({ queryKey: ["me"] });
          router.replace("/");
        }}
        logout={logout}
        logoutError={logoutError}
      />
    );
  const data = overview.data;
  const context = data
    ? { me: auth.data, data, household, month, notify: setToast }
    : null;
  const memberName = auth.data.user.name;
  const content =
    path === "/" ? (
      <Home />
    ) : path === "/budzet" ? (
      <BudgetScreen />
    ) : path === "/dodaj" ? (
      <AddScreen key={params.toString()} />
    ) : path === "/transakcje" ? (
      <TransactionsScreen />
    ) : path === "/cele" ? (
      <GoalsScreen />
    ) : path === "/analiza" ? (
      <AnalyticsScreen />
    ) : path === "/inbox" ? (
      <InboxScreen />
    ) : path === "/konta" ? (
      <AccountsScreen />
    ) : path === "/ustawienia" ? (
      <SettingsScreen logout={logout} />
    ) : path === "/cykliczne" ? (
      <RecurringScreen />
    ) : path === "/wiecej" ? (
      <MoreScreen />
    ) : path.startsWith("/paragony/") ? (
      <ReceiptScreen id={path.split("/")[2]} />
    ) : (
      <div className="empty">
        <h1>Nie ma tu takiej strony</h1>
        <Link className="button primary" href="/">
          Wróć do pulpitu
        </Link>
      </div>
    );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Przejdź do treści
      </a>
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Razem. Pulpit">
          <span className="brand-mark">
            <House size={23} strokeWidth={1.7} />
          </span>
          razem<span className="brand-dot">.</span>
        </Link>
        <div className="sidebar-label">TWÓJ DOM, TWÓJ PLAN</div>
        <nav aria-label="Nawigacja główna">
          {nav.map(({ href, label, icon: Icon }) => (
            <Link
              href={href}
              key={href}
              className={path === href ? "nav-item active" : "nav-item"}
              aria-current={path === href ? "page" : undefined}
            >
              <Icon size={20} strokeWidth={1.7} />
              {label}
              {href === "/inbox" && !!data?.tasks.length && (
                <span className="nav-count">{data.tasks.length}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="nav-separator" />
        <nav aria-label="Pozostałe obszary">
          {secondary.map(({ href, label, icon: Icon }) => (
            <Link
              href={href}
              key={href}
              className={path === href ? "nav-item active" : "nav-item"}
              aria-current={path === href ? "page" : undefined}
            >
              <Icon size={20} strokeWidth={1.7} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="shared-note">
            <Leaf size={19} />
            <div>
              Małe kroki.
              <br />
              <strong>Spokojna przyszłość.</strong>
            </div>
          </div>
          <div className="profile">
            <span className="avatar">{memberName.slice(0, 1)}</span>
            <div>
              <strong>{memberName}</strong>
              <small>{data?.household.name || "Twój dom"}</small>
            </div>
            <button
              className="icon-button"
              aria-label="Wyloguj"
              onClick={logout}
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="household-select">
            <House size={17} />
            {auth.data.households.length > 1 ? (
              <select
                aria-label="Gospodarstwo"
                value={household}
                onChange={(e) => setSelected(e.target.value)}
              >
                {auth.data.households.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </select>
            ) : (
              <span>{data?.household.name || "Twój dom"}</span>
            )}
            <span className="shared-tag">WSPÓLNY BUDŻET</span>
          </div>
          <div className="topbar-actions">
            <Link
              className="icon-button inbox-button"
              href="/inbox"
              aria-label={`Do sprawdzenia: ${data?.tasks.length || 0}`}
            >
              <Inbox size={20} />
              {!!data?.tasks.length && <span className="notification-dot" />}
            </Link>
            <div className="avatar-stack">
              {(data?.members || []).slice(0, 3).map((m, i) => (
                <span
                  key={m.id}
                  title={m.name}
                  className={`avatar ${i ? "peach" : ""}`}
                >
                  {m.name.slice(0, 1)}
                </span>
              ))}
            </div>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="main-content">
          <ErrorMessage error={logoutError} />
          <div className="month-row">
            <span className="eyebrow">
              {path === "/" ? "DOMOWE FINANSE" : "WSPÓLNY PLAN"}
            </span>
            <div className="month-picker">
              <button
                className="icon-button"
                aria-label="Poprzedni miesiąc"
                disabled={month === "2000-01"}
                onClick={() => setMonth(shiftMonth(month, -1))}
              >
                <ChevronLeft size={17} />
              </button>
              <label>
                <span className="sr-only">Miesiąc budżetu</span>
                <input
                  type="month"
                  value={month}
                  min="2000-01"
                  max="2100-12"
                  onChange={(e) => {
                    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(e.target.value))
                      setMonth(e.target.value);
                  }}
                />
                <span aria-hidden="true">{monthName(month)}</span>
              </label>
              <button
                className="icon-button"
                aria-label="Następny miesiąc"
                disabled={month === "2100-12"}
                onClick={() => setMonth(shiftMonth(month, 1))}
              >
                <ChevronRight size={17} />
              </button>
            </div>
          </div>
          {overview.isPending ? (
            <Skeleton />
          ) : overview.isError ? (
            <Card>
              <h1>Nie udało się wczytać danych</h1>
              <ErrorMessage error={overview.error.message} />
              <button
                className="button primary"
                onClick={() => overview.refetch()}
              >
                Spróbuj ponownie
              </button>
            </Card>
          ) : (
            context && (
              <AppContext.Provider key={household} value={context}>
                {content}
              </AppContext.Provider>
            )
          )}
          <footer className="page-footer">
            <span>
              <ShieldCheck size={14} />
              Prywatnie. Bezpiecznie. Razem.
            </span>
            <span>Każdy złoty ma swoje miejsce.</span>
          </footer>
        </main>
      </div>
      <nav className="mobile-nav" aria-label="Nawigacja mobilna">
        {[
          { href: "/", label: "Home", icon: House },
          { href: "/budzet", label: "Budżet", icon: Wallet },
          { href: "/dodaj", label: "Dodaj", icon: Plus },
          { href: "/transakcje", label: "Transakcje", icon: ArrowLeftRight },
          { href: "/wiecej", label: "Więcej", icon: Ellipsis },
        ].map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`${path === href ? "active" : ""} ${href === "/dodaj" ? "central-add" : ""}`}
            aria-current={path === href ? "page" : undefined}
          >
            <span>
              <Icon size={22} strokeWidth={1.8} />
            </span>
            {label}
          </Link>
        ))}
      </nav>
      {toast && (
        <div className="toast" role="status">
          <Check size={18} />
          {toast}
        </div>
      )}
    </div>
  );
}
function AuthScreen({
  onSuccess,
  invited,
}: {
  onSuccess: () => void;
  invited: boolean;
}) {
  const config = useQuery({
    queryKey: ["config"],
    queryFn: () => api<{ demo_enabled: boolean }>("/config"),
  });
  const [register, setRegister] = useState(invited);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api(
        register ? "/auth/register" : "/auth/login",
        json("POST", {
          email: String(f.get("email")),
          password: String(f.get("password")),
          name: String(f.get("name") || "Domownik"),
        }),
      );
      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się zalogować.");
    } finally {
      setBusy(false);
    }
  }
  async function demo() {
    setBusy(true);
    setError("");
    try {
      await api("/auth/demo", { method: "POST" });
      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Demo niedostępne.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <House size={24} />
          </span>
          razem<span className="brand-dot">.</span>
        </Link>
        <div className="story-content">
          <span className="eyebrow">MNIEJ LICZENIA. WIĘCEJ ŻYCIA.</span>
          <h1>
            Wspólny dom.
            <br />
            Spokojny budżet.
          </h1>
          <p>
            Jeden prosty plan dla Waszych pieniędzy.
            <br />
            Na codzienność i to, o czym marzycie.
          </p>
          <div className="story-example">
            <span>
              <Leaf size={20} />
              Każdy złoty ma swoje miejsce
            </span>
            <div>
              <i className="example-dot" />
              Na dziś<strong>7 000 zł</strong>
            </div>
            <div>
              <i className="example-dot light" />
              Dla siebie<strong>1 200 zł</strong>
            </div>
            <div>
              <i className="example-dot pale" />
              Na przyszłość<strong>1 800 zł</strong>
            </div>
            <small>Przykładowy wspólny plan</small>
          </div>
        </div>
        <span className="auth-footer">
          <ShieldCheck size={17} />
          Wasze finanse zostają między Wami.
        </span>
      </section>
      <section className="auth-form-side">
        <div className="auth-form">
          <span className="eyebrow">DOBRZE BYĆ U SIEBIE</span>
          <h2>{register ? "Zacznijmy razem." : "Witaj z powrotem."}</h2>
          <p>
            {invited
              ? "Ktoś zaprasza Cię do wspólnego budżetu."
              : register
                ? "Załóż konto i stwórz miejsce dla Waszych planów."
                : "Zaloguj się i zobacz, jak ma się Wasz plan."}
          </p>
          <form onSubmit={submit}>
            {register && (
              <Field
                label="Jak masz na imię?"
                name="name"
                autoComplete="given-name"
                required
                maxLength={80}
              />
            )}
            <Field
              label="Adres e-mail"
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
            />
            <Field
              label="Hasło"
              name="password"
              type="password"
              minLength={10}
              maxLength={128}
              required
              autoComplete={register ? "new-password" : "current-password"}
              hint={register ? "Co najmniej 10 znaków." : ""}
            />
            <ErrorMessage error={error} />
            <Submit busy={busy}>
              {register ? "Utwórz konto" : "Zaloguj się"}
            </Submit>
          </form>
          <button
            className="text-button auth-toggle"
            onClick={() => {
              setRegister(!register);
              setError("");
            }}
          >
            {register
              ? "Masz już konto? Zaloguj się"
              : "Pierwszy raz tutaj? Utwórz konto"}
            <ArrowRight size={16} />
          </button>
          {config.data?.demo_enabled && (
            <div className="demo-entry">
              <span>Chcesz najpierw się rozejrzeć?</span>
              <button
                className="button secondary"
                onClick={demo}
                disabled={busy}
              >
                Zobacz wersję demo
                <ArrowUpRight size={17} />
              </button>
              <small>
                Przykładowy dom Rocha i Kai. Dane demo można zmieniać.
              </small>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
function Onboarding({
  token,
  name,
  onSuccess,
  logout,
  logoutError,
}: {
  token: string;
  name: string;
  onSuccess: () => void;
  logout: () => void;
  logoutError: string;
}) {
  const [joining, setJoining] = useState(!!token);
  const writeKey = useRef("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (!writeKey.current) writeKey.current = crypto.randomUUID();
    setBusy(true);
    setError("");
    try {
      await api(
        joining ? "/households/join" : "/households",
        json(
          "POST",
          joining ? { token: f.get("token") } : { name: f.get("name") },
          writeKey.current,
        ),
      );
      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się zapisać.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="onboarding">
      <Link className="brand" href="/">
        <span className="brand-mark">
          <House size={24} />
        </span>
        razem.
      </Link>
      <Card>
        <span className="eyebrow">ZACZNIJMY OD DOMU</span>
        <ErrorMessage error={logoutError} />
        <h1>Cześć, {name}.</h1>
        <p className="muted">
          {joining
            ? "Dołącz do wspólnego planu."
            : "Stwórz Waszą przestrzeń. Drugą osobę zaprosisz za chwilę."}
        </p>
        <form onSubmit={submit}>
          {joining ? (
            <Field
              key="join"
              label="Kod zaproszenia"
              name="token"
              defaultValue={token}
              required
              minLength={20}
            />
          ) : (
            <Field
              key="create"
              label="Nazwa gospodarstwa"
              name="name"
              placeholder="Nasz dom"
              maxLength={80}
              required
            />
          )}
          <ErrorMessage error={error} />
          <Submit busy={busy}>
            {joining ? "Dołącz do domu" : "Utwórz nasz dom"}
          </Submit>
        </form>
        <button className="text-button" onClick={() => setJoining(!joining)}>
          {joining ? "Wolę utworzyć własny dom" : "Mam kod zaproszenia"}
          <ArrowRight size={16} />
        </button>
      </Card>
      <button className="text-button" onClick={logout}>
        Wyloguj się
      </button>
    </main>
  );
}
