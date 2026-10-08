"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ShoppingBasket,
  Refrigerator,
  History,
  Plus,
  Pencil,
  Trash2,
  Check,
  Search,
  ReceiptText,
  ArrowRight,
} from "lucide-react";
import { api, json } from "@/lib/api";
import { dateLabel, money, moneyInput, parseMoney } from "@/lib/money";
import {
  locations,
  units,
  parseQuantity,
  quantityInput,
  quantityLabel,
  type Product,
  type ShoppingItem,
  type StockItem,
  type ShoppingOverview,
  type PurchaseHistory,
  type ShoppingReceipt,
  type StockLocation,
  type StockUnit,
} from "@/lib/shopping";
import { useApp, useCommand } from "./context";
import {
  Card,
  Empty,
  ErrorMessage,
  Field,
  MoneyField,
  Select,
  Skeleton,
  Submit,
} from "./ui";

type Editor =
  | {
      kind: "list" | "stock";
      item?: ShoppingItem | StockItem;
      initial?: Product &
        Partial<Pick<ShoppingItem, "category_id" | "actual_amount">>;
    }
  | { kind: "purchase"; item: ShoppingItem }
  | { kind: "consume"; item: StockItem }
  | { kind: "delete-list" | "delete-stock"; item: ShoppingItem | StockItem }
  | {
      kind: "import";
      item: ShoppingReceipt["items"][number];
      merchant: string;
    };
const tabs = [
  { id: "list", label: "Lista zakupów", icon: ShoppingBasket },
  { id: "stock", label: "Zapasy", icon: Refrigerator },
  { id: "history", label: "Historia", icon: History },
];

export function ShoppingScreen() {
  const { household, data: financial } = useApp();
  const params = useSearchParams();
  const router = useRouter();
  const tab = ["stock", "history"].includes(params.get("tab") || "")
    ? params.get("tab")!
    : "list";
  const [editor, setEditor] = useState<Editor | null>(() =>
    params.get("add") === "1" ? { kind: "list" } : null,
  );
  const [search, setSearch] = useState("");
  const [location, setLocation] = useState("all");
  const base = `/households/${household}/shopping`;
  const data = useQuery({
    queryKey: ["shopping", household],
    queryFn: () => api<ShoppingOverview>(base),
    refetchInterval: 15_000,
  });
  function changeTab(next: string) {
    setEditor(null);
    setSearch("");
    router.push(`/zakupy${next === "list" ? "" : `?tab=${next}`}`);
  }
  const stock =
    data.data?.stock.filter(
      (item) =>
        (location === "all" || item.location === location) &&
        item.name
          .toLocaleLowerCase("pl")
          .includes(search.toLocaleLowerCase("pl")),
    ) || [];
  return (
    <>
      <div className="page-heading shopping-heading">
        <div>
          <h1>Zakupy i domowe zapasy</h1>
          <p>Wspólna lista. Wiesz, co kupić i co już masz.</p>
        </div>
        {tab !== "history" && !editor && (
          <button
            className="button primary"
            onClick={() =>
              setEditor({ kind: tab === "stock" ? "stock" : "list" })
            }
          >
            <Plus size={18} />
            {tab === "stock" ? "Dodaj zapas" : "Dodaj produkt"}
          </button>
        )}
      </div>
      <nav className="shopping-tabs" aria-label="Obszary zakupów">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            aria-current={tab === id ? "page" : undefined}
            className={tab === id ? "active" : ""}
            onClick={() => changeTab(id)}
          >
            <Icon size={19} />
            {label}
          </button>
        ))}
      </nav>
      {data.isPending ? (
        <Skeleton />
      ) : data.isError ? (
        <Card>
          <h2>Nie udało się wczytać zakupów</h2>
          <ErrorMessage error={data.error.message} />
          <button className="button secondary" onClick={() => data.refetch()}>
            Spróbuj ponownie
          </button>
        </Card>
      ) : (
        data.data && (
          <>
            {editor && (
              <EditorForm
                key={`${editor.kind}-${"item" in editor ? editor.item?.id || "new" : "new"}-${JSON.stringify("initial" in editor ? editor.initial : null)}`}
                editor={editor}
                base={base}
                today={data.data.today}
                onClose={() =>
                  setEditor((current) => (current === editor ? null : current))
                }
              />
            )}
            {tab === "list" && (
              <>
                <Card className="shopping-summary">
                  <div>
                    <span>Szacowany koszt listy</span>
                    <strong>{money(data.data.estimated_total)}</strong>
                    <small>
                      {data.data.unpriced_count
                        ? `${data.data.unpriced_count} bez wyceny · suma znanych cen`
                        : "Na podstawie wpisanych cen"}
                    </small>
                  </div>
                  <div>
                    <span>Do kupienia</span>
                    <strong>{data.data.items.length}</strong>
                    <small>produkty na wspólnej liście</small>
                  </div>
                </Card>
                {data.data.suggestions.length > 0 && (
                  <Card className="shopping-suggestions">
                    <h2>Kończące się zapasy</h2>
                    <p>
                      Do ustawionego minimum. Produkty z listy są już pominięte.
                    </p>
                    <div>
                      {data.data.suggestions.map((item, index) => (
                        <button
                          key={index}
                          className="button secondary"
                          onClick={() =>
                            setEditor({ kind: "list", initial: item })
                          }
                        >
                          <Plus size={16} />
                          {item.name} ·{" "}
                          {quantityLabel(item.quantity, item.unit)}
                        </button>
                      ))}
                    </div>
                  </Card>
                )}
                <Card className="shopping-products">
                  <div className="shopping-section-title">
                    <h2>Wasza lista</h2>
                    <span>{data.data.items.length} pozycji</span>
                  </div>
                  {data.data.items.length === 0 ? (
                    <Empty
                      title="Lista jest pusta"
                      description="Dodaj pierwszy produkt. Druga osoba zobaczy go na tej samej liście."
                    />
                  ) : (
                    data.data.items.map((item) => (
                      <article className="shopping-row" key={item.id}>
                        <div className="shopping-product">
                          <strong>{item.name}</strong>
                          <span>
                            {quantityLabel(item.quantity, item.unit)} ·{" "}
                            {locations[item.location]}
                            {item.category_id &&
                              ` · ${financial.categories.find((c) => c.id === item.category_id)?.name || "Kategoria zakupu"}`}
                          </span>
                        </div>
                        <span className="shopping-price">
                          {item.estimated_amount === null
                            ? "Bez wyceny"
                            : money(item.estimated_amount)}
                        </span>
                        <div className="shopping-row-actions">
                          <button
                            className="button secondary"
                            aria-label={`Kupione: ${item.name}`}
                            onClick={() =>
                              setEditor({ kind: "purchase", item })
                            }
                          >
                            <Check size={17} />
                            Kupione
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Edytuj produkt: ${item.name}`}
                            onClick={() => setEditor({ kind: "list", item })}
                          >
                            <Pencil size={17} />
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Usuń z listy: ${item.name}`}
                            onClick={() =>
                              setEditor({ kind: "delete-list", item })
                            }
                          >
                            <Trash2 size={17} />
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </Card>
                <div className="notice">
                  <ReceiptText size={20} />
                  <div>
                    <strong>Wydatek zapisz osobno</strong>
                    <p>
                      „Kupione” aktualizuje historię i zapasy.{" "}
                      <Link href="/dodaj">
                        Zeskanuj paragon lub dodaj wydatek
                      </Link>
                      , żeby uwzględnić zakup w budżecie.
                    </p>
                  </div>
                </div>
              </>
            )}
            {tab === "stock" && (
              <>
                <Card className="stock-tools">
                  <div className="shopping-section-title">
                    <div>
                      <h2>Co macie w domu</h2>
                      <p>
                        {data.data.expiring_count
                          ? `Terminy wymagają uwagi: ${data.data.expiring_count}. Do 3 dni lub po terminie.`
                          : "Aktualizuj ilości po zużyciu produktów."}
                      </p>
                    </div>
                  </div>
                  <div className="form-grid">
                    <Field
                      label="Szukaj w zapasach"
                      placeholder="Nazwa produktu"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                    <Select
                      label="Miejsce przechowywania"
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                    >
                      <option value="all">Wszystkie miejsca</option>
                      {Object.entries(locations).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </Select>
                  </div>
                </Card>
                <Card className="shopping-products">
                  {stock.length === 0 ? (
                    <Empty
                      title={
                        data.data.stock.length
                          ? "Brak pasujących produktów"
                          : "Zajrzyj do lodówki i szafek"
                      }
                      description={
                        data.data.stock.length
                          ? "Zmień nazwę lub miejsce wyszukiwania."
                          : "Dodaj to, co już macie. Kolejne zakupy mogą uzupełniać zapasy."
                      }
                    />
                  ) : (
                    stock.map((item) => (
                      <article
                        className={`shopping-row ${item.expires_on && item.expires_on < data.data.today && item.quantity > 0 ? "stock-expired" : ""}`}
                        key={item.id}
                      >
                        <div className="shopping-product">
                          <strong>{item.name}</strong>
                          <span>
                            {locations[item.location]}
                            {item.minimum > 0 &&
                              ` · minimum ${quantityLabel(item.minimum, item.unit)}`}
                          </span>
                          {item.expires_on && (
                            <small
                              className={
                                item.quantity > 0 &&
                                item.expires_on <= data.data.today
                                  ? "stock-expiry"
                                  : ""
                              }
                            >
                              {item.expires_on < data.data.today
                                ? "Po terminie:"
                                : "Termin:"}{" "}
                              {dateLabel(item.expires_on)}{" "}
                              {item.expires_on.slice(0, 4)}
                            </small>
                          )}
                        </div>
                        <strong className="stock-quantity">
                          {quantityLabel(item.quantity, item.unit)}
                          {item.quantity === 0 && <small>Brak zapasu</small>}
                        </strong>
                        <div className="shopping-row-actions">
                          <button
                            className="button secondary"
                            disabled={item.quantity === 0}
                            aria-label={`Zużyj: ${item.name}`}
                            onClick={() => setEditor({ kind: "consume", item })}
                          >
                            Zużyj
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Dodaj do listy: ${item.name}`}
                            onClick={() =>
                              setEditor({
                                kind: "list",
                                initial: {
                                  name: item.name,
                                  unit: item.unit,
                                  location: item.location,
                                  quantity: Math.max(
                                    item.minimum - item.quantity,
                                    1000,
                                  ),
                                },
                              })
                            }
                          >
                            <Plus size={17} />
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Edytuj zapas: ${item.name}`}
                            onClick={() => setEditor({ kind: "stock", item })}
                          >
                            <Pencil size={17} />
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Usuń zapas: ${item.name}`}
                            onClick={() =>
                              setEditor({ kind: "delete-stock", item })
                            }
                          >
                            <Trash2 size={17} />
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </Card>
                <ReceiptStock
                  base={base}
                  onImport={(item, merchant) =>
                    setEditor({ kind: "import", item, merchant })
                  }
                />
              </>
            )}
            {tab === "history" && (
              <HistoryPanel
                base={base}
                onRepeat={(item) => setEditor({ kind: "list", initial: item })}
              />
            )}
          </>
        )
      )}
    </>
  );
}

function EditorForm({
  editor,
  base,
  today,
  onClose,
}: {
  editor: Editor;
  base: string;
  today: string;
  onClose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "instant", block: "center" });
    ref.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, []);
  return (
    <section
      ref={ref}
      className="card shopping-editor"
      aria-label="Edycja zakupów"
    >
      {editor.kind === "purchase" ? (
        <PurchaseForm
          item={editor.item}
          base={base}
          today={today}
          onClose={onClose}
        />
      ) : editor.kind === "consume" ? (
        <ConsumeForm item={editor.item} base={base} onClose={onClose} />
      ) : editor.kind.startsWith("delete-") &&
        "item" in editor &&
        editor.item ? (
        <DeleteForm
          item={editor.item as ShoppingItem | StockItem}
          kind={editor.kind}
          base={base}
          onClose={onClose}
        />
      ) : (
        <ProductForm
          editor={
            editor as
              | Extract<Editor, { kind: "list" | "stock" }>
              | Extract<Editor, { kind: "import" }>
          }
          base={base}
          onClose={onClose}
        />
      )}
    </section>
  );
}
function ProductForm({
  editor,
  base,
  onClose,
}: {
  editor:
    | Extract<Editor, { kind: "list" | "stock" }>
    | Extract<Editor, { kind: "import" }>;
  base: string;
  onClose: () => void;
}) {
  const { data, household } = useApp();
  const cmd = useCommand();
  const isImport = editor.kind === "import";
  const pendingList = useQuery({
    queryKey: ["shopping", household],
    queryFn: () => api<ShoppingOverview>(base),
    enabled: isImport,
  });
  const [matching, setMatching] = useState("");
  const item = editor.item;
  const initial = "initial" in editor ? editor.initial : undefined;
  const product = initial || item;
  const [name, setName] = useState(product?.name || "");
  const [quantity, setQuantity] = useState(
    product && "unit" in product
      ? quantityInput(product.quantity)
      : isImport
        ? ""
        : "1",
  );
  const [unit, setUnit] = useState<StockUnit>(
    product && "unit" in product ? product.unit : "szt",
  );
  const [location, setLocation] = useState<StockLocation>(
    product && "location" in product ? product.location : "pantry",
  );
  const [estimated, setEstimated] = useState(
    item && "estimated_amount" in item && item.estimated_amount !== null
      ? moneyInput(item.estimated_amount)
      : initial &&
          "actual_amount" in initial &&
          typeof initial.actual_amount === "number"
        ? moneyInput(initial.actual_amount)
        : "",
  );
  const [category, setCategory] = useState(() => {
    const candidate =
      item && "category_id" in item ? item.category_id : initial?.category_id;
    return data.categories.some((row) => row.id === candidate && !row.archived)
      ? candidate || ""
      : "";
  });
  const [expires, setExpires] = useState(
    item && "expires_on" in item ? item.expires_on || "" : "",
  );
  const [minimum, setMinimum] = useState(
    item && "minimum" in item ? quantityInput(item.minimum) : "0",
  );
  const editing = !!item && !isImport;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        try {
          const payload = {
            name,
            quantity: parseQuantity(quantity, editor.kind === "stock"),
            unit,
            location,
          };
          const body =
            editor.kind === "list"
              ? {
                  ...payload,
                  estimated_amount: estimated ? parseMoney(estimated) : null,
                  category_id: category || null,
                }
              : editor.kind === "stock"
                ? {
                    ...payload,
                    minimum: parseQuantity(minimum, true),
                    expires_on: expires || null,
                  }
                : {
                    ...payload,
                    expires_on: expires || null,
                    shopping_item_id: matching || null,
                    shopping_updated_at:
                      pendingList.data?.items.find((row) => row.id === matching)
                        ?.updated_at || null,
                  };
          const path = isImport
            ? `${base}/receipt-items/${item!.id}`
            : `${base}/${editor.kind === "stock" ? "stock" : "items"}${editing ? `/${item!.id}` : ""}`;
          cmd.run(
            (key) =>
              api(
                path,
                json(
                  editing ? "PUT" : "POST",
                  editing
                    ? {
                        ...body,
                        expected_updated_at: (item as StockItem).updated_at,
                      }
                    : body,
                  key,
                ),
              ),
            isImport
              ? "Produkt z paragonu dodany do zapasów"
              : "Produkt zapisany",
            onClose,
          );
        } catch (error) {
          cmd.setError((error as Error).message);
        }
      }}
    >
      <h2>
        {isImport
          ? "Dodaj produkt z paragonu"
          : editing
            ? "Edytuj produkt"
            : editor.kind === "stock"
              ? "Dodaj domowy zapas"
              : "Dodaj do listy"}
      </h2>
      {isImport && (
        <p>
          {editor.merchant} · {money(editor.item.amount)}. Sprawdź ilość i
          jednostkę na opakowaniu. Dane paragonu:{" "}
          {editor.item.quantity || "ilość nieodczytana"}. Dodaj tylko produkty,
          których nie masz jeszcze w zapasach.
        </p>
      )}
      <ErrorMessage error={cmd.error} />
      <StaleRecovery error={cmd.error} onClose={onClose} />
      <fieldset disabled={cmd.busy} className="shopping-fields">
        {isImport && (
          <Select
            label="Połącz z listą zakupów"
            value={matching}
            onChange={(e) => setMatching(e.target.value)}
          >
            <option value="">Osobny zakup — bez pozycji z listy</option>
            {pendingList.data?.items.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name} · {quantityLabel(row.quantity, row.unit)}
              </option>
            ))}
          </Select>
        )}
        <Field
          label="Nazwa produktu"
          value={name}
          maxLength={120}
          required
          onChange={(e) => setName(e.target.value)}
        />
        <div className="form-grid shopping-quantity-fields">
          <Field
            label="Ilość"
            inputMode="decimal"
            required
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            hint="Możesz wpisać np. 0,5."
          />
          <Select
            label="Jednostka"
            value={unit}
            onChange={(e) => setUnit(e.target.value as StockUnit)}
          >
            {Object.entries(units).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <Select
          label="Gdzie przechowywać"
          value={location}
          onChange={(e) => setLocation(e.target.value as StockLocation)}
        >
          {Object.entries(locations).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
        {editor.kind === "list" ? (
          <div className="form-grid">
            <MoneyField
              label="Szacowany koszt całości (zł)"
              value={estimated}
              onChange={(e) => setEstimated(e.target.value)}
              hint="Opcjonalnie · za całą wpisaną ilość"
            />
            <Select
              label="Kategoria zakupu"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">Bez kategorii</option>
              {data.categories
                .filter((c) => !c.archived)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </Select>
          </div>
        ) : (
          <div className="form-grid">
            <Field
              label="Termin ważności"
              type="date"
              min="2000-01-01"
              max="2100-12-31"
              value={expires}
              onChange={(e) => setExpires(e.target.value)}
              hint="Opcjonalnie · z opakowania"
            />
            {editor.kind === "stock" && (
              <Field
                label="Minimalny zapas"
                inputMode="decimal"
                value={minimum}
                onChange={(e) => setMinimum(e.target.value)}
                hint={`W ${units[unit]} · 0 wyłącza podpowiedź zakupów`}
              />
            )}
          </div>
        )}
      </fieldset>
      <FormActions
        busy={cmd.busy}
        onClose={onClose}
        label={isImport ? "Dodaj do zapasów" : "Zapisz produkt"}
      />
    </form>
  );
}
function StaleRecovery({
  error,
  onClose,
}: {
  error: string;
  onClose: () => void;
}) {
  const query = useQueryClient();
  return error.startsWith("Ktoś") ? (
    <button
      type="button"
      className="button secondary"
      onClick={async () => {
        await query.invalidateQueries({ queryKey: ["shopping"] });
        onClose();
      }}
    >
      Wczytaj aktualne dane
    </button>
  ) : null;
}
function FormActions({
  busy,
  onClose,
  label,
}: {
  busy: boolean;
  onClose: () => void;
  label: string;
}) {
  return (
    <div className="shopping-form-actions">
      <Submit busy={busy}>{label}</Submit>
      <button
        className="button secondary"
        type="button"
        disabled={busy}
        onClick={onClose}
      >
        Anuluj
      </button>
    </div>
  );
}
function PurchaseForm({
  item,
  base,
  today,
  onClose,
}: {
  item: ShoppingItem;
  base: string;
  today: string;
  onClose: () => void;
}) {
  const cmd = useCommand();
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [date, setDate] = useState(today);
  const [add, setAdd] = useState(true);
  const [expires, setExpires] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        try {
          cmd.run(
            (key) =>
              api(
                `${base}/items/${item.id}/purchase`,
                json(
                  "POST",
                  {
                    expected_updated_at: item.updated_at,
                    purchased_on: date,
                    actual_amount: amount ? parseMoney(amount) : null,
                    merchant,
                    add_to_stock: add,
                    expires_on: add && expires ? expires : null,
                  },
                  key,
                ),
              ),
            "Zakup zapisany w historii",
            onClose,
          );
        } catch (error) {
          cmd.setError((error as Error).message);
        }
      }}
    >
      <h2>Potwierdź zakup</h2>
      <p>
        <strong>{item.name}</strong> · {quantityLabel(item.quantity, item.unit)}
        {item.estimated_amount !== null &&
          ` · plan ${money(item.estimated_amount)}`}
      </p>
      <ErrorMessage error={cmd.error} />
      <fieldset disabled={cmd.busy} className="shopping-fields">
        <div className="form-grid">
          <MoneyField
            label="Zapłacono za produkt (zł)"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            hint="Opcjonalnie · nie księguje wydatku"
          />
          <Field
            label="Data zakupu"
            type="date"
            required
            min="2000-01-01"
            max={today}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <Field
          label="Sklep"
          maxLength={120}
          value={merchant}
          onChange={(e) => setMerchant(e.target.value)}
          placeholder="Opcjonalnie"
        />
        <label className="shopping-check">
          <input
            type="checkbox"
            checked={add}
            onChange={(e) => setAdd(e.target.checked)}
          />
          Dodaj do zapasów: {locations[item.location]}
        </label>
        {add && (
          <Field
            label="Termin ważności"
            type="date"
            min="2000-01-01"
            max="2100-12-31"
            value={expires}
            onChange={(e) => setExpires(e.target.value)}
            hint="Opcjonalnie · z opakowania"
          />
        )}
      </fieldset>
      <FormActions busy={cmd.busy} onClose={onClose} label="Potwierdź zakup" />
    </form>
  );
}
function ConsumeForm({
  item,
  base,
  onClose,
}: {
  item: StockItem;
  base: string;
  onClose: () => void;
}) {
  const cmd = useCommand();
  const [quantity, setQuantity] = useState(
    quantityInput(Math.min(item.quantity, 1000)),
  );
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        try {
          cmd.run(
            (key) =>
              api(
                `${base}/stock/${item.id}/consume`,
                json(
                  "POST",
                  {
                    quantity: parseQuantity(quantity),
                    expected_updated_at: item.updated_at,
                  },
                  key,
                ),
              ),
            "Zapas zaktualizowany",
            onClose,
          );
        } catch (error) {
          cmd.setError((error as Error).message);
        }
      }}
    >
      <h2>Zużycie produktu</h2>
      <p>
        {item.name} · masz {quantityLabel(item.quantity, item.unit)}
      </p>
      <ErrorMessage error={cmd.error} />
      <Field
        label={`Zużyta ilość (${units[item.unit]})`}
        inputMode="decimal"
        required
        disabled={cmd.busy}
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
      />
      <FormActions busy={cmd.busy} onClose={onClose} label="Zapisz zużycie" />
    </form>
  );
}
function DeleteForm({
  item,
  kind,
  base,
  onClose,
}: {
  item: ShoppingItem | StockItem;
  kind: string;
  base: string;
  onClose: () => void;
}) {
  const cmd = useCommand();
  return (
    <>
      <h2>{kind === "delete-stock" ? "Usuń zapas" : "Usuń z listy"}</h2>
      <p>
        {item.name}.{" "}
        {kind === "delete-stock"
          ? "Historia zakupów pozostanie. Ten produkt przestanie pojawiać się w zapasach."
          : "Produkt zniknie ze wspólnej listy."}
      </p>
      <ErrorMessage error={cmd.error} />
      <div className="shopping-form-actions">
        <button
          className="button danger-button"
          disabled={cmd.busy}
          onClick={() =>
            cmd.run(
              (key) =>
                api(
                  `${base}/${kind === "delete-stock" ? "stock" : "items"}/${item.id}`,
                  json("DELETE", { expected_updated_at: item.updated_at }, key),
                ),
              "Produkt usunięty",
              onClose,
            )
          }
        >
          Usuń produkt
        </button>
        <button
          className="button secondary"
          disabled={cmd.busy}
          onClick={onClose}
        >
          Anuluj
        </button>
      </div>
    </>
  );
}
function ReceiptStock({
  base,
  onImport,
}: {
  base: string;
  onImport: (item: ShoppingReceipt["items"][number], merchant: string) => void;
}) {
  const receiptId = useSearchParams().get("receipt") || "";
  const [open, setOpen] = useState(!!receiptId);
  const [selected, setSelected] = useState(receiptId);
  const query = useQuery({
    queryKey: ["shopping-receipts", base],
    queryFn: () => api<ShoppingReceipt[]>(`${base}/receipts`),
    enabled: open,
  });
  const receipt = query.data?.find((row) => row.id === selected);
  return (
    <details
      className="card receipt-stock"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        <ReceiptText size={19} />
        Dodaj zapasy z paragonu
      </summary>
      <p>
        Wybierz produkty z ostatnich 20 zatwierdzonych paragonów. Wpisz ich
        ilość i miejsce. Nie powstanie nowy wydatek.
      </p>
      {query.isPending && open ? (
        <Skeleton />
      ) : query.isError ? (
        <>
          <ErrorMessage error={query.error.message} />
          <button className="button secondary" onClick={() => query.refetch()}>
            Spróbuj ponownie
          </button>
        </>
      ) : query.data?.length === 0 ? (
        <p>
          Najpierw <Link href="/dodaj">zeskanuj i zatwierdź paragon</Link>.
        </p>
      ) : (
        <>
          <Select
            label="Paragon do uzupełnienia zapasów"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Wybierz paragon</option>
            {query.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {row.merchant} · {row.date}
              </option>
            ))}
          </Select>
          {receipt?.items.map((item) => (
            <div className="receipt-stock-row" key={item.id}>
              <span>
                {item.name} · {money(item.amount)}
              </span>
              {item.imported ? (
                <span className="tag">Dodano do zapasów</span>
              ) : (
                <button
                  className="button secondary"
                  aria-label={`Dodaj z paragonu: ${item.name}`}
                  onClick={() => onImport(item, receipt.merchant)}
                >
                  <Plus size={16} />
                  Dodaj
                </button>
              )}
            </div>
          ))}
        </>
      )}
    </details>
  );
}
function HistoryPanel({
  base,
  onRepeat,
}: {
  base: string;
  onRepeat: (item: ShoppingItem) => void;
}) {
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["shopping-history", base, filters, offset],
    queryFn: () =>
      api<PurchaseHistory>(`${base}/history?offset=${offset}&${filters}`),
  });
  return (
    <>
      <Card className="shopping-history-filter">
        <h2>Historia wspólnych zakupów</h2>
        <p>Zakupy potwierdzone na liście i produkty dodane z paragonów.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const params = new URLSearchParams();
            if (q) params.set("q", q);
            if (from) params.set("date_from", from);
            if (to) params.set("date_to", to);
            setOffset(0);
            setFilters(params.toString());
          }}
        >
          <Field
            label="Szukaj w historii zakupów"
            placeholder="Produkt lub sklep"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="form-grid">
            <Field
              label="Zakupy od"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
            <Field
              label="Zakupy do"
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
          <button className="button secondary" type="submit">
            <Search size={17} />
            Szukaj
          </button>
        </form>
      </Card>
      {query.isPending ? (
        <Skeleton />
      ) : query.isError ? (
        <Card>
          <ErrorMessage error={query.error.message} />
          <button className="button secondary" onClick={() => query.refetch()}>
            Spróbuj ponownie
          </button>
        </Card>
      ) : (
        query.data && (
          <Card className="shopping-products">
            {query.data.items.length === 0 ? (
              <Empty
                title="Brak zakupów w tym widoku"
                description="Potwierdź zakup na liście lub zmień filtry historii."
              />
            ) : (
              query.data.items.map((item) => (
                <article className="shopping-row" key={item.id}>
                  <div className="shopping-product">
                    <strong>{item.name}</strong>
                    <span>
                      {quantityLabel(item.quantity, item.unit)} ·{" "}
                      {item.purchased_on}{" "}
                      {item.merchant && `· ${item.merchant}`}
                    </span>
                  </div>
                  <span className="shopping-price">
                    {item.actual_amount === null
                      ? "Cena niepodana"
                      : money(item.actual_amount)}
                  </span>
                  <button
                    className="button secondary"
                    aria-label={`Kup ponownie: ${item.name}`}
                    onClick={() => onRepeat(item)}
                  >
                    <Plus size={16} />
                    Na listę
                  </button>
                </article>
              ))
            )}
            {query.data.total > 30 && (
              <div className="shopping-form-actions">
                <button
                  className="button secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 30))}
                >
                  Poprzednie
                </button>
                <span>
                  {offset + 1}–{Math.min(offset + 30, query.data.total)} z{" "}
                  {query.data.total}
                </span>
                <button
                  className="button secondary"
                  disabled={offset + 30 >= query.data.total}
                  onClick={() => setOffset(offset + 30)}
                >
                  Następne
                </button>
              </div>
            )}
          </Card>
        )
      )}
      <Link href="/transakcje" className="text-button">
        Zobacz wydatki w budżecie <ArrowRight size={16} />
      </Link>
    </>
  );
}
