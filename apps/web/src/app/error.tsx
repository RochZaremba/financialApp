"use client";
export default function Error({ reset }: { reset: () => void }) {
  return (
    <main className="empty">
      <h1>Coś poszło nie tak</h1>
      <p>Twoje zapisane dane są bezpieczne. Spróbuj odświeżyć widok.</p>
      <button className="button primary" onClick={reset}>
        Spróbuj ponownie
      </button>
    </main>
  );
}
