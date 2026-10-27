"use client";
import { useState } from "react";
import {
  meterUnit,
  readingNumber,
  averageNumber,
  readingMoment,
  readingDuration,
  activitySummary,
  type MeterReading,
  type MeterUnit,
} from "@/lib/meters";
import { Card, Empty } from "./ui";

export function MeterChart({
  readings,
  unit,
}: {
  readings: MeterReading[];
  unit: MeterUnit;
}) {
  const [daily, setDaily] = useState(false);
  const [selected, setSelected] = useState("");
  const intervals = readings.filter((r) => r.consumption !== null).slice(-6);
  if (!intervals.length)
    return (
      <Card>
        <Empty
          icon="account"
          title="Zużycie pojawi się po drugim odczycie."
          description="Pierwszy stan jest punktem odniesienia. Kolejne zdjęcie lub wpis pozwoli policzyć rzeczywiste zużycie."
        />
      </Card>
    );
  const shown =
    intervals.find((r) => r.id === selected) || intervals[intervals.length - 1];
  const amount = (row: MeterReading) =>
    (daily ? row.average : row.consumption) ?? 0;
  const maximum = Math.max(1, ...intervals.map(amount));
  const label = (row: MeterReading) =>
    daily
      ? averageNumber(row.average ?? 0, row.consumption ?? 0)
      : readingNumber(amount(row));
  const suffix = meterUnit(unit) + (daily ? "/dzień" : "");
  return (
    <Card className="meter-chart">
      <div className="section-title">
        <h2>Jak zmienia się zużycie?</h2>
      </div>
      <div
        className="meter-chart-toggle"
        role="group"
        aria-label="Rodzaj wykresu"
      >
        <button
          className={`button ${daily ? "secondary" : "primary"}`}
          aria-pressed={!daily}
          onClick={() => setDaily(false)}
        >
          Między odczytami
        </button>
        <button
          className={`button ${daily ? "primary" : "secondary"}`}
          aria-pressed={daily}
          onClick={() => setDaily(true)}
        >
          Średnio dziennie
        </button>
      </div>
      <p className="muted small">
        Ostatnie {intervals.length} okresów · {suffix}. Wybierz słupek, aby
        sprawdzić szczegóły.
      </p>
      <div className="meter-bars" aria-label={`Wykres zużycia w ${suffix}`}>
        {intervals.map((row) => (
          <div className="meter-bar-column" key={row.id}>
            <button
              type="button"
              className={`meter-bar-choice ${row.id === shown.id ? "selected" : ""}`}
              aria-label={`${readingMoment(row.from_date!, row.from_time)} – ${readingMoment(row.date, row.time)}: ${label(row)} ${suffix}`}
              aria-pressed={row.id === shown.id}
              onClick={() => setSelected(row.id)}
            >
              <span className="meter-bar-number" aria-hidden="true">
                {label(row)}
              </span>
              <span
                className="meter-bar"
                aria-hidden="true"
                style={{
                  height: `${Math.max(3, (130 * amount(row)) / maximum)}px`,
                }}
              />
              <time dateTime={row.date}>
                {row.date.slice(8)}.{row.date.slice(5, 7)}
              </time>
            </button>
          </div>
        ))}
      </div>
      <div className="meter-chart-detail">
        <strong>
          {label(shown)} {suffix}
        </strong>
        <span>
          {readingMoment(shown.from_date!, shown.from_time)} –{" "}
          {readingMoment(shown.date, shown.time)} · {readingDuration(shown)}
        </span>
        {activitySummary(shown.activities) && (
          <p className="meter-context-text">
            {activitySummary(shown.activities)}
          </p>
        )}
        {shown.note && <p className="meter-context-text">{shown.note}</p>}
      </div>
      <p className="muted small">
        Każdy słupek obejmuje cały okres między odczytami. Średnia dzienna nie
        jest pomiarem każdego dnia.
        {shown.elapsed_seconds == null &&
          " Nieznana godzina jednego z odczytów — średnia liczona według dat."}
      </p>
    </Card>
  );
}
