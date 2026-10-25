"use client";
import { useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Gauge, Plus, Pencil, Trash2 } from "lucide-react";
import { api, json } from "@/lib/api";
import {
  meterDate,
  averageNumber,
  meterDays,
  meterUnit,
  parseReading,
  readingNumber,
  type Meter,
  type MeterDetail,
  type MeterPhoto,
  type MeterReading,
} from "@/lib/meters";
import { useApp, useCommand } from "./context";
import { PageHeading } from "./budget-screens";
import { Card, ErrorMessage, Field, Select, Skeleton, Submit } from "./ui";
import { MeterChart } from "./meter-chart";

export function MetersScreen() {
  const { household } = useApp();
  const [selected, setSelected] = useState("");
  const [creating, setCreating] = useState(false);
  const command = useCommand();
  const list = useQuery({
    queryKey: ["meters", household],
    queryFn: () => api<Meter[]>(`/households/${household}/meters`),
  });
  const meter = list.data?.find((m) => m.id === selected) || list.data?.[0];
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await command.run(
      (key) =>
        api<Meter>(
          `/households/${household}/meters`,
          json(
            "POST",
            {
              name: form.get("name"),
              unit: form.get("unit"),
              interval_days: Number(form.get("interval")),
            },
            key,
          ),
        ),
      "Licznik dodany",
      (result) => {
        setSelected(result.id);
        setCreating(false);
      },
    );
  }
  return (
    <>
      <PageHeading
        title="Wasze liczniki."
        description="Zdjęcie od czasu do czasu. Zużycie bez zgadywania."
        action={
          <div className="meter-heading-actions">
            {meter && (
              <a className="button primary" href="#meter-reading">
                <Camera size={18} />
                Dodaj odczyt
              </a>
            )}
            <button
              className={`button ${meter ? "secondary" : "primary"}`}
              onClick={() => setCreating(!creating)}
            >
              <Plus size={18} />
              Dodaj licznik
            </button>
          </div>
        }
      />
      {list.isPending ? (
        <Skeleton />
      ) : list.isError ? (
        <Card>
          <ErrorMessage error={list.error.message} />
          <button className="button secondary" onClick={() => list.refetch()}>
            Spróbuj ponownie
          </button>
        </Card>
      ) : (
        <>
          {(creating || !list.data?.length) && (
            <Card className="meter-form-card">
              <h2>Dodaj pierwszy punkt pomiaru</h2>
              <p className="muted">
                Na przykład prąd, woda w kuchni albo gaz. Każdy licznik ma
                własną historię.
              </p>
              <form onSubmit={create}>
                <Field
                  label="Nazwa licznika"
                  name="name"
                  placeholder="Np. Prąd w mieszkaniu"
                  maxLength={80}
                  required
                />
                <Select label="Jednostka" name="unit" defaultValue="kWh">
                  <option value="kWh">kWh — prąd lub energia</option>
                  <option value="m3">m³ — woda lub gaz</option>
                  <option value="GJ">GJ — ciepło</option>
                </Select>
                <Field
                  label="Przypomnienie po ilu dniach?"
                  hint="0 wyłącza przypomnienie. Zobaczysz je na tym ekranie; nie wysyłamy powiadomień."
                  name="interval"
                  type="number"
                  min={0}
                  max={365}
                  step={1}
                  defaultValue={30}
                  required
                />
                <ErrorMessage error={command.error} />
                <Submit busy={command.busy}>Zapisz licznik</Submit>
              </form>
            </Card>
          )}
          {!!list.data?.length && (
            <Select
              label="Wybierz licznik"
              value={meter?.id || ""}
              onChange={(e) => setSelected(e.target.value)}
            >
              {list.data.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {meterUnit(item.unit)}
                </option>
              ))}
            </Select>
          )}
          {meter && <MeterView key={meter.id} meterId={meter.id} />}
        </>
      )}
    </>
  );
}

function MeterView({ meterId }: { meterId: string }) {
  const { household } = useApp();
  const [editing, setEditing] = useState<MeterReading | null>(null);
  const command = useCommand();
  const detail = useQuery({
    queryKey: ["meter", household, meterId],
    queryFn: () =>
      api<MeterDetail>(`/households/${household}/meters/${meterId}`),
  });
  if (detail.isPending) return <Skeleton />;
  if (detail.isError)
    return (
      <Card>
        <ErrorMessage error={detail.error.message} />
        <button className="button secondary" onClick={() => detail.refetch()}>
          Spróbuj ponownie
        </button>
      </Card>
    );
  const data = detail.data;
  const meter = data.meter;
  const last = data.readings.at(-1);
  const unit = meterUnit(meter.unit);
  async function remove(row: MeterReading) {
    if (
      !window.confirm(
        `Usunąć odczyt z ${meterDate(row.date)}? Zużycie sąsiednich okresów zostanie przeliczone.`,
      )
    )
      return;
    await command.run(
      () =>
        api(
          `/households/${household}/meters/${meterId}/readings/${row.id}`,
          json("DELETE", { expected_updated_at: row.updated_at }),
        ),
      "Odczyt usunięty",
      () => setEditing(null),
    );
  }
  return (
    <div className="meter-view">
      <div className="meter-summary">
        <Card>
          <span>Ostatni stan · {meter.name}</span>
          <strong>
            {last ? readingNumber(last.value) : "—"} {unit}
          </strong>
          <small>{last ? meterDate(last.date) : "Dodaj pierwszy odczyt"}</small>
        </Card>
        <Card>
          <span>Zużycie od poprzedniego odczytu</span>
          <strong>
            {last?.consumption != null
              ? `${readingNumber(last.consumption)} ${unit}`
              : "Jeszcze jeden odczyt"}
          </strong>
          <small>
            {last?.days
              ? `${meterDays(last.days)} · średnio ${averageNumber(last.average!, last.consumption!)} ${unit}/dzień`
              : "Nie zakładamy początkowego stanu zero"}
          </small>
        </Card>
      </div>
      {data.next_due && (
        <p className={`notice ${data.overdue ? "warning" : ""}`}>
          <Gauge size={20} />
          {data.overdue ? "Czas na kolejny odczyt" : "Następny odczyt"}:{" "}
          {meterDate(data.next_due)}
        </p>
      )}
      <MeterChart readings={data.readings} unit={meter.unit} />
      <div id="meter-reading">
        <ReadingForm
          key={editing?.id || "new"}
          data={data}
          reading={editing}
          close={() => setEditing(null)}
        />
      </div>
      <Card>
        <h2>Historia odczytów</h2>
        {data.truncated && (
          <p className="muted small">
            Ostatnie 500 wpisów. Pełna historia jest w eksporcie gospodarstwa.
          </p>
        )}
        <ErrorMessage error={command.error} />
        {!data.readings.length ? (
          <p className="muted">
            Zapisz pierwszy stan ręcznie albo dodaj zdjęcie.
          </p>
        ) : (
          <div className="meter-history">
            {[...data.readings].reverse().map((row) => (
              <article key={row.id}>
                <div>
                  <time dateTime={row.date}>{meterDate(row.date)}</time>
                  <strong>
                    {readingNumber(row.value)} {unit}
                  </strong>
                  <small>
                    {row.consumption == null
                      ? "Punkt początkowy"
                      : `Zużycie: ${readingNumber(row.consumption)} ${unit} przez ${meterDays(row.days!)} `}
                  </small>
                  <small>
                    Dodano przez: {row.created_by_name || "Nieznany autor"}
                  </small>
                  {row.photo_id && (
                    <a
                      href={`/api/households/${household}/meters/${meterId}/photos/${row.photo_id}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Zobacz zdjęcie
                    </a>
                  )}
                </div>
                <div className="meter-history-actions">
                  <button
                    className="icon-button"
                    aria-label={`Popraw odczyt ${row.date}`}
                    onClick={() => setEditing(row)}
                  >
                    <Pencil size={18} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`Usuń odczyt ${row.date}`}
                    disabled={command.busy}
                    onClick={() => remove(row)}
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>
      <MeterPlan key={meter.updated_at} meter={meter} />
    </div>
  );
}

function ReadingForm({
  data,
  reading,
  close,
}: {
  data: MeterDetail;
  reading: MeterReading | null;
  close: () => void;
}) {
  const { household, me, notify } = useApp();
  const query = useQueryClient();
  const command = useCommand();
  const [date, setDate] = useState(reading?.date || data.today);
  const [value, setValue] = useState(
    reading ? readingNumber(reading.value).replace(/\s/g, "") : "",
  );
  const [file, setFile] = useState<File | null>(null);
  const [photo, setPhoto] = useState<MeterPhoto | null>(null);
  const [uploading, setUploading] = useState(false);
  const [photoError, setPhotoError] = useState("");
  const uploadKey = useRef("");
  const inFlight = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const base = `/households/${household}/meters/${data.meter.id}`;
  async function upload() {
    if (!file || inFlight.current) return;
    if (file.size > 10 * 1024 * 1024) {
      setPhotoError("Zdjęcie może mieć najwyżej 10 MB.");
      return;
    }
    inFlight.current = true;
    setUploading(true);
    setPhotoError("");
    if (!uploadKey.current) uploadKey.current = crypto.randomUUID();
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api<MeterPhoto>(`${base}/photos`, {
        method: "POST",
        body: form,
        headers: { "Idempotency-Key": uploadKey.current },
      });
      setPhoto(result);
      uploadKey.current = "";
      notify("Zdjęcie zapisane");
      await query.invalidateQueries({
        queryKey: ["meter", household, data.meter.id],
      });
    } catch (error) {
      setPhotoError(
        error instanceof Error
          ? error.message
          : "Nie udało się zapisać zdjęcia. Spróbuj ponownie.",
      );
    } finally {
      inFlight.current = false;
      setUploading(false);
    }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsed: number;
    try {
      parsed = parseReading(value);
    } catch (error) {
      command.setError((error as Error).message);
      return;
    }
    const payload = {
      date,
      value: parsed,
      photo_id: photo?.id || reading?.photo_id || null,
    };
    await command.run(
      (key) =>
        api(
          reading ? `${base}/readings/${reading.id}` : `${base}/readings`,
          json(
            reading ? "PUT" : "POST",
            reading
              ? { ...payload, expected_updated_at: reading.updated_at }
              : payload,
            key,
          ),
        ),
      reading ? "Odczyt poprawiony" : "Odczyt zapisany",
      () => {
        close();
        setValue("");
        setDate(data.today);
        setPhoto(null);
        setFile(null);
        if (fileInput.current) fileInput.current.value = "";
      },
    );
  }
  return (
    <Card className="meter-form-card">
      <h2>{reading ? "Popraw odczyt" : "Dodaj kolejny odczyt"}</h2>
      <p className="muted">
        Wpisz cały stan widoczny na liczniku, nie samo zużycie.
      </p>
      <fieldset disabled={uploading || command.busy}>
        <legend className="sr-only">Zdjęcie i sprawdzenie odczytu</legend>
        <label className="field meter-file-field">
          <span>Zdjęcie licznika (opcjonalnie)</span>
          <input
            ref={fileInput}
            className="meter-file-input"
            aria-label="Zdjęcie licznika"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              uploadKey.current = "";
              setPhotoError("");
            }}
          />
          <span className="button secondary">
            <Camera size={18} />
            Zrób lub wybierz zdjęcie
          </span>
          <small>{file?.name || "Nie wybrano zdjęcia"}</small>
        </label>
        <p className="muted small">
          {me.receipt_ai_available
            ? `Po wybraniu odczytu zdjęcie trafi do ${me.receipt_provider === "gemini" ? "Gemini" : "OpenAI"}. Sprawdź propozycję przed zapisaniem; odczyt może być płatny.`
            : "AI nie jest skonfigurowane. Zdjęcie możesz zachować i wpisać stan ręcznie."}
        </p>
        <button
          type="button"
          className="button secondary"
          disabled={!file}
          onClick={upload}
        >
          <Camera size={18} />
          {uploading
            ? "Odczytuję zdjęcie…"
            : me.receipt_ai_available
              ? "Odczytaj zdjęcie z AI"
              : "Zapisz zdjęcie"}
        </button>
        <ErrorMessage error={photoError} />
        {photo && (
          <div className="meter-proposal">
            <a
              href={`/api${base}/photos/${photo.id}`}
              target="_blank"
              rel="noreferrer"
            >
              Zobacz zapisane zdjęcie
            </a>
            {photo.proposal?.value != null ? (
              <>
                <p>
                  Propozycja:{" "}
                  <strong>
                    {readingNumber(photo.proposal.value)}{" "}
                    {meterUnit(data.meter.unit)}
                  </strong>{" "}
                  · pewność {photo.proposal.confidence}%
                </p>
                {photo.provider === "fixture" && (
                  <p className="muted small">
                    To testowe zdjęcie demonstracyjne.
                  </p>
                )}
                <button
                  type="button"
                  className="button secondary"
                  onClick={() =>
                    setValue(
                      readingNumber(photo.proposal!.value!).replace(/\s/g, ""),
                    )
                  }
                >
                  Użyj tego odczytu
                </button>
                <p className="muted small">
                  Porównaj cyfry ze zdjęciem. Zapis nastąpi dopiero po
                  zatwierdzeniu formularza.
                </p>
              </>
            ) : (
              <p className="notice warning">
                {photo.diagnostics.message ||
                  "Cyfry są nieczytelne. Wpisz stan ręcznie."}
                {photo.diagnostics.code && (
                  <>
                    {" "}
                    Kod: {photo.diagnostics.code}
                    {photo.diagnostics.http_status &&
                      ` · HTTP ${photo.diagnostics.http_status}`}
                  </>
                )}
              </p>
            )}
          </div>
        )}
        <form onSubmit={save}>
          <Field
            label="Data odczytu"
            type="date"
            min="2000-01-01"
            max={data.today}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          <Field
            label={`Stan licznika (${meterUnit(data.meter.unit)})`}
            inputMode="decimal"
            maxLength={20}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Np. 12345,678"
            hint="Do 3 miejsc po przecinku. Możesz poprawić cyfry z AI."
            required
          />
          <ErrorMessage error={command.error} />
          <Submit busy={command.busy}>Zapisz odczyt</Submit>
          {reading && (
            <button type="button" className="text-button" onClick={close}>
              Anuluj poprawkę
            </button>
          )}
        </form>
      </fieldset>
      {!!data.photos.length && (
        <details className="meter-photos">
          <summary>Ostatnie zdjęcia ({data.photos.length})</summary>
          {data.photos.map((item) => (
            <div key={item.id}>
              <a
                href={`/api${base}/photos/${item.id}`}
                target="_blank"
                rel="noreferrer"
              >
                Zdjęcie z{" "}
                {new Date(item.created_at).toLocaleDateString("pl-PL", {
                  timeZone: "Europe/Warsaw",
                })}
              </a>
              <button
                className="text-button"
                type="button"
                disabled={uploading || command.busy}
                onClick={() => setPhoto(item)}
              >
                Sprawdź odczyt
              </button>
            </div>
          ))}
        </details>
      )}
    </Card>
  );
}

function MeterPlan({ meter }: { meter: Meter }) {
  const { household } = useApp();
  const command = useCommand();
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await command.run(
      () =>
        api(
          `/households/${household}/meters/${meter.id}/plan`,
          json("PUT", {
            interval_days: Number(form.get("interval")),
            expected_updated_at: meter.updated_at,
          }),
        ),
      "Plan odczytów zapisany",
    );
  }
  return (
    <Card className="meter-form-card">
      <h2>Wasz rytm odczytów</h2>
      <p className="muted">
        Zdjęcia możesz dodawać nieregularnie. Ustaw odstęp, po którym pokażemy
        przypomnienie o kolejnym pomiarze.
      </p>
      <form onSubmit={save}>
        <Field
          label="Odstęp odczytów w dniach"
          name="interval"
          type="number"
          min={0}
          max={365}
          step={1}
          defaultValue={meter.interval_days}
          hint="0 wyłącza przypomnienie. Jest widoczne tutaj, bez powiadomień w tle."
          required
        />
        <ErrorMessage error={command.error} />
        <Submit busy={command.busy}>Zapisz plan</Submit>
      </form>
      <p className="muted small">
        Po wymianie lub wyzerowaniu licznika dodaj nowy punkt pomiaru. Zachowasz
        poprzednią historię.
      </p>
    </Card>
  );
}
