"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, ReceiptText, ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { money, monthName } from "@/lib/money";
import { useApp } from "./context";
import { PageHeading } from "./budget-screens";
import { Card, Empty, ErrorMessage, Skeleton } from "./ui";

type Counts = {
  receipts: number;
  expenses: number;
  expense_amount: number;
  incomes: number;
  income_amount: number;
};
type Activity = {
  month: string | null;
  totals: Counts;
  people: (Counts & {
    user_id: string | null;
    name: string;
    current_member: boolean;
  })[];
};

export function ActivityScreen() {
  const { household, month } = useApp();
  const [allTime, setAllTime] = useState(false);
  const result = useQuery({
    queryKey: ["activity", household, allTime ? "all" : month],
    queryFn: () =>
      api<Activity>(
        `/households/${household}/activity${allTime ? "" : `?month=${month}`}`,
      ),
  });
  const data = result.data;
  return (
    <>
      <PageHeading
        title="Aktywność domowników."
        description="Zobacz, kto dodaje paragony, wydatki i wpływy do Waszego domu."
      />
      <div
        className="activity-period"
        role="group"
        aria-label="Okres aktywności"
      >
        <button
          className={`button ${allTime ? "secondary" : "primary"}`}
          aria-pressed={!allTime}
          onClick={() => setAllTime(false)}
        >
          {monthName(month)}
        </button>
        <button
          className={`button ${allTime ? "primary" : "secondary"}`}
          aria-pressed={allTime}
          onClick={() => setAllTime(true)}
        >
          Cały okres
        </button>
      </div>
      <p className="muted small activity-explanation">
        Liczymy zachowane wpisy według czasu dodania w Polsce. Autor wpisu to
        osoba, która go zapisała — niezależnie od tego, kto płacił lub zarobił.
      </p>
      {result.isPending ? (
        <Skeleton />
      ) : result.isError ? (
        <Card>
          <ErrorMessage error={result.error.message} />
          <button className="button secondary" onClick={() => result.refetch()}>
            Spróbuj ponownie
          </button>
        </Card>
      ) : data ? (
        <>
          {!data.totals.receipts &&
            !data.totals.expenses &&
            !data.totals.incomes && (
              <Empty
                icon="receipt"
                title="Tutaj jeszcze spokojnie."
                description="W tym okresie nikt nie dodał paragonu, wydatku ani wpływu. Wybierz inny miesiąc lub cały okres."
              />
            )}
          <div className="activity-people" aria-label="Aktywność według osoby">
            {data.people.map((person) => (
              <Card
                key={person.user_id || "unknown"}
                className="activity-person"
              >
                <div className="activity-person-heading">
                  <Users size={22} aria-hidden="true" />
                  <div>
                    <h2>{person.name}</h2>
                    {person.user_id === null ? (
                      <p className="muted small">
                        Starsze wpisy bez informacji o autorze
                      </p>
                    ) : !person.current_member ? (
                      <p className="muted small">Były domownik</p>
                    ) : null}
                  </div>
                </div>
                <dl className="activity-person-counts">
                  <div>
                    <dt>Paragony</dt>
                    <dd>{person.receipts}</dd>
                  </div>
                  <div>
                    <dt>Wydatki</dt>
                    <dd>
                      {person.expenses}
                      <small>{money(person.expense_amount)}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Wpływy</dt>
                    <dd>
                      {person.incomes}
                      <small>{money(person.income_amount)}</small>
                    </dd>
                  </div>
                </dl>
              </Card>
            ))}
          </div>
          <h2 className="activity-total-heading">Razem w tym okresie</h2>
          <div className="activity-summary" aria-label="Łączna aktywność">
            <Card>
              <ReceiptText size={20} aria-hidden="true" />
              <span>Paragony</span>
              <strong>{data.totals.receipts}</strong>
              <small>Także niezakończone szkice</small>
            </Card>
            <Card>
              <ArrowUpRight size={20} aria-hidden="true" />
              <span>Wydatki</span>
              <strong>{money(data.totals.expense_amount)}</strong>
              <small>Liczba wpisów: {data.totals.expenses}</small>
            </Card>
            <Card>
              <ArrowDownLeft size={20} aria-hidden="true" />
              <span>Wpływy</span>
              <strong>{money(data.totals.income_amount)}</strong>
              <small>Liczba wpisów: {data.totals.incomes}</small>
            </Card>
          </div>
          <p className="muted small">
            Wydatek z paragonu przypisujemy osobie, która go zatwierdziła.
            Zdjęcie przypisujemy osobie, która je dodała. Wartości paragonów nie
            doliczamy ponownie do wydatków.
          </p>
        </>
      ) : null}
    </>
  );
}
