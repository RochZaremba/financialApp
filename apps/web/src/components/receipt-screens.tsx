"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ScanLine,
  Camera,
  Upload,
  Plus,
  ArrowLeft,
  ArrowRight,
  ArrowDownLeft,
  ArrowUpRight,
  ArrowLeftRight,
  Wallet,
  Flag,
  Check,
  CircleHelp,
  Trash2,
  Pencil,
  ImageIcon,
  CheckCheck,
  FilePenLine,
  AlertTriangle,
} from "lucide-react";
import { api, ApiError, json } from "@/lib/api";
import {
  money,
  moneyInput,
  parseMoney,
  parseSignedMoney,
} from "@/lib/money";
import type { Receipt, ReceiptItem } from "@/lib/types";
import { useApp, useCommand } from "./context";
import {
  Amount,
  Card,
  Empty,
  ErrorMessage,
  Field,
  Icon,
  MoneyField,
  Select,
  Skeleton,
  Submit,
} from "./ui";
import { PageHeading } from "./budget-screens";

import { ManualTransaction, type MovementKind } from "./movement-form";
export function AddScreen() {
  const { month } = useApp();
  const params = useSearchParams();
  const [kind, setKind] = useState(params.get("type") || "scan");
  const choices = [
    { kind: "scan", name: "Paragon", icon: ScanLine },
    { kind: "expense", name: "Wydatek", icon: ArrowUpRight },
    { kind: "income", name: "Wpływ", icon: ArrowDownLeft },
    { kind: "transfer", name: "Przelew", icon: ArrowLeftRight },
  ];
  return (
    <>
      <PageHeading
        title="Dodaj do Waszego planu."
        description="Zdjęcie paragonu lub szybki wpis. Tak, jak Ci wygodniej."
      />
      <div className="add-types" role="group" aria-label="Co chcesz dodać?">
        {choices.map(({ kind: choice, name, icon: Icon }) => (
          <button
            key={choice}
            className={kind === choice ? "selected" : ""}
            onClick={() => setKind(choice)}
            aria-pressed={kind === choice}
          >
            <Icon size={22} strokeWidth={1.7} />
            <span>{name}</span>
          </button>
        ))}
      </div>
      {kind === "scan" ? (
        <UploadReceipt />
      ) : (
        <ManualTransaction
          key={`${kind}:${month}`}
          kind={kind as MovementKind}
          memberId={params.get("member") || ""}
          goalId={params.get("goal") || ""}
        />
      )}
      <div className="add-more">
        <span>Chcesz zrobić coś jeszcze?</span>
        {kind !== "pocket" && (
          <button className="text-button" onClick={() => setKind("pocket")}>
            <Wallet size={17} />
            Wypłać kieszonkowe
          </button>
        )}
        {kind !== "saving" && (
          <button className="text-button" onClick={() => setKind("saving")}>
            <Flag size={17} />
            Odłóż na cel
          </button>
        )}
      </div>
    </>
  );
}
function UploadReceipt() {
  const { household, me } = useApp();
  const command = useCommand();
  const router = useRouter();
  async function upload(file?: File) {
    if (!file) return;
    await command.run(
      async (key) => {
        if (file.size > 10 * 1024 * 1024)
          throw new Error("Zdjęcie może mieć najwyżej 10 MB.");
        const form = new FormData();
        form.append("file", file);
        return api<Receipt>(`/households/${household}/receipts`, {
          method: "POST",
          headers: { "Idempotency-Key": key },
          body: form,
        });
      },
      "Paragon gotowy do sprawdzenia",
      (receipt) => router.push(`/paragony/${receipt.id}`),
    );
  }
  async function fixture() {
    const blob = await fetch("/demo/lidl.png").then((r) => r.blob());
    await upload(new File([blob], "lidl.png", { type: "image/png" }));
  }
  return (
    <Card className="upload-card">
      <div className="scan-symbol">
        <ScanLine size={38} strokeWidth={1.4} />
      </div>
      <h2>
        {command.busy
          ? "Odczytujemy Wasz paragon…"
          : "Małe zdjęcie. Mniej wpisywania."}
      </h2>
      <p>
        {command.busy
          ? "Zdjęcie jest przesyłane i przetwarzane. Zwykle zajmuje to kilkanaście sekund. Zostań chwilę na tej stronie."
          : "Zadbaj, żeby cały paragon był widoczny, a tekst ostry. Resztą zajmiemy się razem."}
      </p>
      {command.busy ? (
        <div className="processing-indicator" role="status">
          <span className="spinner" />
          <span>Przesyłanie i odczyt</span>
        </div>
      ) : (
        <div className="upload-actions">
          <label className="button primary">
            <Camera size={18} />
            Zrób zdjęcie
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              onChange={(e) => {
                upload(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
          <label className="button secondary">
            <Upload size={18} />
            Wybierz plik
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => {
                upload(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      )}
      <ErrorMessage error={command.error} />
      <div className="upload-note">
        <Check size={15} />
        <span>JPG, PNG lub WebP · do 10 MB · zdjęcie pozostaje prywatne</span>
      </div>
      {!me.receipt_ai_available && (
        <div className="manual-provider-note">
          <FilePenLine size={18} />
          <p>
            Automatyczny odczyt zdjęć wymaga skonfigurowania OCR. Zdjęcie
            zapiszemy prywatnie, a dane możesz uzupełnić ręcznie.
            {me.receipt_provider === "fixture"
              ? " Przykładowy paragon poniżej pokaże pełną ścieżkę odczytu."
              : ""}
          </p>
        </div>
      )}
      {me.receipt_provider === "fixture" && (
        <button
          className="text-button"
          disabled={command.busy}
          onClick={fixture}
        >
          Użyj przykładowego paragonu Lidl
          <ArrowRight size={16} />
        </button>
      )}
    </Card>
  );
}
export function ReceiptScreen({ id }: { id: string }) {
  const { household } = useApp();
  const receipt = useQuery({
    queryKey: ["receipt", household, id],
    queryFn: () => api<Receipt>(`/households/${household}/receipts/${id}`),
  });
  if (receipt.isPending) return <Skeleton />;
  if (receipt.isError)
    return (
      <Card>
        <ErrorMessage error={receipt.error.message} />
        <button className="button secondary" onClick={() => receipt.refetch()}>
          Spróbuj ponownie
        </button>
        <Link className="text-button" href="/inbox">
          Wróć do spraw do sprawdzenia
        </Link>
      </Card>
    );
  return <ReceiptEditor key={receipt.data.id} receipt={receipt.data} />;
}
type EditableItem = Omit<ReceiptItem, "id" | "amount"> & {
  localId: string;
  amountText: string;
};
function itemIncomplete(item: EditableItem) {
  return !item.name.trim() || !item.amountText.trim();
}
function ReceiptEditor({ receipt }: { receipt: Receipt }) {
  const { data, household, me } = useApp();
  const command = useCommand();
  const router = useRouter();
  const [merchant, setMerchant] = useState(receipt.merchant);
  const [date, setDate] = useState(receipt.date || "");
  const [total, setTotal] = useState(
    receipt.total ? moneyInput(receipt.total) : "",
  );
  const [items, setItems] = useState<EditableItem[]>(() =>
    receipt.items.map((i, index) => ({
      name: i.name,
      quantity: i.quantity,
      category_id: i.category_id,
      confidence: i.confidence,
      reviewed: i.reviewed,
      amountText: i.amount === null ? "" : moneyInput(i.amount),
      localId: i.id || String(index),
    })),
  );
  const [acknowledge, setAcknowledge] = useState(false);
  const [duplicateDetected, setDuplicateDetected] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [imageVisible, setImageVisible] = useState(false);
  const [editingItems, setEditingItems] = useState<Set<string>>(
    () => new Set(),
  );
  const duplicateSuspected = data.tasks.some(
    (t) => t.receipt_id === receipt.id && t.kind === "duplicate",
  );
  const possibleDuplicate = duplicateSuspected || duplicateDetected;
  const readOnly = receipt.status === "confirmed";
  const safe = (s: string) => {
    try {
      return parseSignedMoney(s);
    } catch {
      return 0;
    }
  };
  const categoryTotals = new Map<string, number>();
  for (const item of items) {
    if (item.category_id)
      categoryTotals.set(
        item.category_id,
        (categoryTotals.get(item.category_id) || 0) + safe(item.amountText),
      );
  }
  const invalidCategories = new Set(
    [...categoryTotals].filter(([, total]) => total < 0).map(([id]) => id),
  );
  const ambiguous = items.filter(
    (i) =>
      !i.category_id ||
      invalidCategories.has(i.category_id) ||
      (i.confidence < me.thresholds.auto && !i.reviewed),
  ).length;
  const sum = items.reduce((n, i) => n + safe(i.amountText), 0);
  const difference = safe(total) - sum;
  const incomplete =
    !merchant.trim() ||
    !date ||
    !items.length ||
    safe(total) <= 0 ||
    items.some(itemIncomplete);
  const itemWord =
    ambiguous % 10 >= 2 &&
    ambiguous % 10 <= 4 &&
    !(ambiguous % 100 >= 12 && ambiguous % 100 <= 14)
      ? "pozycje"
      : "pozycji";
  function change(id: string, update: Partial<EditableItem>) {
    setItems(items.map((i) => (i.localId === id ? { ...i, ...update } : i)));
  }
  function payload(draft = false) {
    return {
      merchant,
      date: draft && !date ? null : date,
      total: draft && !total.trim() ? null : parseMoney(total),
      items: items.map((i) => ({
        name: i.name,
        quantity: i.quantity,
        amount:
          draft && !i.amountText.trim() ? null : parseSignedMoney(i.amountText),
        category_id: i.category_id,
        confidence: i.confidence,
        reviewed: i.reviewed,
      })),
    };
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await command.run(
      async () => {
        try {
          return await api(
            `/households/${household}/receipts/${receipt.id}/finalize`,
            json("POST", {
              ...payload(),
              account_id: f.get("account"),
              acknowledge_duplicate: acknowledge,
            }),
          );
        } catch (error) {
          // Corrected OCR can reveal a match that was unknown at upload.
          // Finalization's 409 requires an explicit separate-purchase decision.
          if (error instanceof ApiError && error.status === 409)
            setDuplicateDetected(true);
          throw error;
        }
      },
      "Paragon zapisany. Budżet zaktualizowany.",
      () => router.push("/"),
    );
  }
  async function saveDraft() {
    await command.run(
      () =>
        api(
          `/households/${household}/receipts/${receipt.id}`,
          json("PUT", payload(true)),
        ),
      "Szkic paragonu zapisany",
      () => {
        setDuplicateDetected(false);
        setAcknowledge(false);
      },
    );
  }
  async function discard() {
    await command.run(
      () =>
        api(`/households/${household}/receipts/${receipt.id}`, {
          method: "DELETE",
        }),
      "Szkic usunięty",
      () => router.push("/inbox"),
    );
  }
  return (
    <>
      <Link className="back-link" href={readOnly ? "/transakcje" : "/inbox"}>
        <ArrowLeft size={16} />
        {readOnly ? "Wróć do historii" : "Do sprawdzenia"}
      </Link>
      <PageHeading
        title={
          readOnly
            ? "Paragon zapisany."
            : incomplete
              ? "Uzupełnij paragon."
              : possibleDuplicate && !acknowledge
                ? "Sprawdź możliwy duplikat."
                : difference !== 0
                  ? "Popraw kwoty paragonu."
                  : ambiguous
                    ? `Jeszcze ${ambiguous === 1 ? "jedna chwila" : `${ambiguous} ${itemWord}`}.`
                    : "Wszystko wygląda dobrze."
        }
        description={
          readOnly
            ? "Zapisane pozycje i ich podział między koperty."
            : incomplete
              ? "Zdjęcie jest bezpiecznie zapisane. Wpisz brakujące dane i pozycje ze zdjęcia."
              : possibleDuplicate && !acknowledge
                ? "Sklep, data lub zdjęcie pasują do wcześniejszego paragonu. Potwierdź poniżej tylko wtedy, gdy to osobny zakup."
                : difference !== 0
                  ? "Suma pozycji różni się od sumy paragonu. Porównaj kwoty ze zdjęciem."
                  : ambiguous
                    ? "Sprawdź wyróżnione pozycje. Reszta jest już przypisana."
                    : "Sprawdź kwoty i zatwierdź. Wasz budżet od razu się zaktualizuje."
        }
        action={
          <button
            className="button secondary"
            onClick={() => setImageVisible(!imageVisible)}
          >
            <ImageIcon size={17} />
            {imageVisible ? "Ukryj zdjęcie" : "Zobacz zdjęcie"}
          </button>
        }
      />
      {receipt.provider === "fixture" && (
        <div className="notice soft">
          <ScanLine size={17} />
          To przykładowy paragon demonstracyjny. Kwoty są testowe.
        </div>
      )}
      {invalidCategories.size > 0 && !readOnly && (
        <div className="notice warning" role="alert">
          <AlertTriangle size={18} />
          Przypisz rabat do kategorii zakupów, których dotyczy. Rabat nie może
          przekraczać ich kwoty.
        </div>
      )}
      {receipt.error && incomplete && !readOnly && (
        <div className="notice warning">
          <FilePenLine size={18} />
          {receipt.error}
        </div>
      )}
      {imageVisible && (
        <Card className="receipt-image-card">
          {/* Private authenticated URL, bypass Next public image caching. */}
          <img
            src={`/api/households/${household}/receipts/${receipt.id}/image`}
            alt="Zdjęcie przesłanego paragonu"
          />
          <a
            className="button secondary"
            href={`/api/households/${household}/receipts/${receipt.id}/image`}
            download="paragon.png"
          >
            Pobierz zdjęcie
          </a>
        </Card>
      )}
      <form onSubmit={submit} className="receipt-form">
        <Card>
          <div className="receipt-header">
            <Icon name="receipt" />
            <div>
              <h2>Dane paragonu</h2>
              <p className="muted small">
                {readOnly
                  ? "Potwierdzone dane"
                  : "Możesz poprawić każdy odczyt."}
              </p>
            </div>
            {readOnly && (
              <span className="pill positive">
                <Check size={13} />
                Zatwierdzony
              </span>
            )}
          </div>
          <div className="form-grid three">
            <Field
              label="Sklep"
              value={merchant}
              onChange={(e) => setMerchant(e.target.value)}
              required
              maxLength={120}
              disabled={readOnly}
            />
            <Field
              label="Data zakupu"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              min="2000-01-01"
              max="2100-12-31"
              required
              disabled={readOnly}
            />
            <MoneyField
              label="Suma paragonu (zł)"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
              required
              disabled={readOnly}
            />
          </div>
        </Card>
        <Card className="receipt-items">
          <div className="section-title">
            <h2>Co znalazło się w koszyku?</h2>
            <span className="muted small">Pozycje: {items.length}</span>
          </div>
          {items.length === 0 && (
            <Empty
              title="Uzupełnij koszyk"
              description="Dodaj pozycje ze zdjęcia. Kwoty pozycji muszą dać sumę paragonu."
            />
          )}
          {items.map((item, index) => {
            const uncertain =
              !readOnly &&
              (itemIncomplete(item) ||
                !item.category_id ||
                invalidCategories.has(item.category_id) ||
                (item.confidence < me.thresholds.auto && !item.reviewed));
            return (
              <div
                className={`receipt-item ${uncertain ? "uncertain" : ""}`}
                key={item.localId}
              >
                <div className="item-status">
                  {uncertain ? <CircleHelp size={18} /> : <Check size={18} />}
                  <span>
                    {uncertain
                      ? "Do sprawdzenia"
                      : readOnly
                        ? "Zapisane"
                        : item.reviewed
                          ? "Sprawdzone"
                          : "Przypisane"}
                  </span>
                  {uncertain && item.confidence > 0 && (
                    <small>{item.confidence}% pewności</small>
                  )}
                </div>
                {!uncertain && !editingItems.has(item.localId) ? (
                  <div className="receipt-item-summary">
                    <div>
                      <strong>{item.name}</strong>
                      <small>
                        {item.quantity ? `${item.quantity} · ` : ""}
                        {data.categories.find((c) => c.id === item.category_id)
                          ?.name || "Bez kategorii"}
                      </small>
                    </div>
                    <Amount value={safe(item.amountText)} />
                    {!readOnly && (
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Edytuj pozycję ${index + 1}`}
                        onClick={() =>
                          setEditingItems(
                            new Set([...editingItems, item.localId]),
                          )
                        }
                      >
                        <Pencil size={16} />
                      </button>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="receipt-item-fields">
                      <Field
                        label={`Pozycja ${index + 1}`}
                        value={item.name}
                        required
                        maxLength={160}
                        onChange={(e) =>
                          change(item.localId, {
                            name: e.target.value,
                            confidence: 0,
                            reviewed: false,
                          })
                        }
                        disabled={readOnly}
                      />
                      <Field
                        label="Ilość"
                        hint="Jeśli jest na paragonie."
                        value={item.quantity}
                        maxLength={30}
                        onChange={(e) =>
                          change(item.localId, { quantity: e.target.value })
                        }
                        disabled={readOnly}
                      />
                      <MoneyField
                        label="Kwota pozycji (zł)"
                        hint="Rabat wpisz ze znakiem minus."
                        value={item.amountText}
                        required
                        onChange={(e) =>
                          change(item.localId, { amountText: e.target.value })
                        }
                        disabled={readOnly}
                      />
                      <Select
                        label="Kategoria"
                        value={item.category_id || ""}
                        required={!readOnly}
                        onChange={(e) =>
                          change(item.localId, {
                            category_id: e.target.value || null,
                            reviewed: true,
                          })
                        }
                        disabled={readOnly}
                      >
                        <option value="">Wybierz kategorię</option>
                        {data.categories
                          .filter(
                            (c) => !c.archived || c.id === item.category_id,
                          )
                          .map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                      </Select>
                      {!readOnly && (
                        <button
                          className="icon-button"
                          type="button"
                          aria-label={`Usuń pozycję ${index + 1}`}
                          onClick={() =>
                            setItems(
                              items.filter((i) => i.localId !== item.localId),
                            )
                          }
                        >
                          <Trash2 size={17} />
                        </button>
                      )}
                    </div>
                    {!uncertain && !readOnly && (
                      <button
                        type="button"
                        className="text-button compact-done"
                        onClick={() =>
                          setEditingItems(
                            new Set(
                              [...editingItems].filter(
                                (id) => id !== item.localId,
                              ),
                            ),
                          )
                        }
                      >
                        <Check size={14} />
                        Gotowe
                      </button>
                    )}
                  </>
                )}
                {uncertain && (
                  <div className="category-chips">
                    <span>Pasuje do:</span>
                    {data.categories
                      .filter((c) => !c.archived)
                      .slice(0, 6)
                      .map((c) => (
                        <button
                          type="button"
                          key={c.id}
                          onClick={() =>
                            change(item.localId, {
                              category_id: c.id,
                              reviewed: true,
                            })
                          }
                        >
                          {c.name}
                        </button>
                      ))}
                    {item.category_id && (
                      <button
                        type="button"
                        className="confirm-chip"
                        onClick={() => change(item.localId, { reviewed: true })}
                      >
                        <Check size={13} />
                        Kategoria jest poprawna
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          {!readOnly && (
            <button
              className="button secondary"
              type="button"
              onClick={() =>
                setItems([
                  ...items,
                  {
                    localId: crypto.randomUUID(),
                    name: "",
                    quantity: "",
                    amountText: "",
                    category_id: null,
                    confidence: 0,
                    reviewed: false,
                  },
                ])
              }
            >
              <Plus size={17} />
              Dodaj pozycję
            </button>
          )}
          <div
            className={`receipt-total ${difference !== 0 || incomplete ? "mismatch" : ""}`}
          >
            <div>
              <span>Suma pozycji</span>
              <strong>{money(sum)}</strong>
            </div>
            <div>
              <span>
                {incomplete
                  ? "Uzupełnij kwoty"
                  : difference === 0
                    ? "Kwoty się zgadzają"
                    : "Różnica do poprawienia"}
              </span>
              <strong>
                {difference === 0 && !incomplete ? (
                  <>
                    <Check size={17} />
                    {money(safe(total))}
                  </>
                ) : (
                  money(difference)
                )}
              </strong>
            </div>
          </div>
        </Card>
        {!readOnly && (
          <Card className="receipt-confirm">
            <Select label="Z którego konta zapłacono?" name="account" required>
              {data.accounts
                .filter((a) => a.currency === "PLN")
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </Select>
            <p className="muted small">
              Poprawione kategorie zapamiętamy tylko dla Waszego gospodarstwa.
            </p>
            {possibleDuplicate && (
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={acknowledge}
                  onChange={(e) => {
                    setAcknowledge(e.target.checked);
                    if (e.target.checked) command.setError("");
                  }}
                />
                <span>
                  Jeśli ten paragon już istnieje, potwierdzam, że to osobny
                  zakup.
                </span>
              </label>
            )}
            <ErrorMessage error={command.error} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={saveDraft}
                disabled={command.busy}
              >
                Zapisz szkic
              </button>
              <Submit busy={command.busy}>Zatwierdź paragon</Submit>
            </div>
            <button
              type="button"
              className="text-button destructive"
              onClick={() => setConfirmDiscard(!confirmDiscard)}
            >
              Usuń ten szkic
            </button>
            {confirmDiscard && (
              <div className="notice danger">
                <span>
                  Usuniemy zdjęcie i niezapisane pozycje. Nie zmieni to budżetu.
                </span>
                <button
                  type="button"
                  className="button danger-button"
                  onClick={discard}
                  disabled={command.busy}
                >
                  Usuń szkic
                </button>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setConfirmDiscard(false)}
                >
                  Zostaw
                </button>
              </div>
            )}
          </Card>
        )}
      </form>
    </>
  );
}
export function InboxScreen() {
  const { data } = useApp();
  const taskNames: Record<string, string> = {
    classification: "Sprawdź kategorię",
    extraction: "Uzupełnij dane paragonu",
    duplicate: "Sprawdź możliwy duplikat",
    unallocated: "Przypisz kategorię",
    confirmation: "Zatwierdź paragon",
  };
  return (
    <>
      <PageHeading
        title="Chwila uwagi i gotowe."
        description="Sprawdź niepewne pozycje i dokończ zapis paragonów. Reszta ma swoje miejsce."
      />
      <Card className="inbox-card">
        {data.tasks.length ? (
          <div className="inbox-list">
            {data.tasks.map((task) => (
              <Link
                className="inbox-row"
                href={
                  task.receipt_id
                    ? `/paragony/${task.receipt_id}`
                    : `/transakcje?item=${task.transaction_id}`
                }
                key={task.id}
              >
                <span
                  className={`icon-box ${task.kind === "duplicate" ? "amber" : "green"}`}
                >
                  {task.kind === "duplicate" ? (
                    <AlertTriangle size={22} />
                  ) : task.kind === "extraction" ? (
                    <FilePenLine size={22} />
                  ) : task.kind === "confirmation" ? (
                    <CheckCheck size={22} />
                  ) : (
                    <CircleHelp size={22} />
                  )}
                </span>
                <div>
                  <span className="eyebrow">{taskNames[task.kind]}</span>
                  <strong>{task.title}</strong>
                  <small>
                    {task.kind === "confirmation"
                      ? "Sprawdź sumę i zatwierdź. Budżet zaktualizuje się po zapisie."
                      : task.receipt_id
                        ? "Popraw odczyt lub kategorię, potem zatwierdź."
                        : "Wydatek jest w budżecie. Brakuje mu tylko koperty."}
                  </small>
                </div>
                <ArrowRight size={19} />
              </Link>
            ))}
          </div>
        ) : (
          <Empty
            icon="shield"
            title="Wszystko na bieżąco."
            description="Nie ma nic do sprawdzenia. Możecie zająć się ważniejszymi rzeczami."
            action="Wróć do pulpitu"
            href="/"
          />
        )}
      </Card>
      <div className="quiet-tip">
        <CheckCheck size={18} />
        <p>
          Gdy poprawisz kategorię na paragonie, zapamiętamy ją na kolejne
          zakupy. Tylko w Waszym domu.
        </p>
      </div>
    </>
  );
}
