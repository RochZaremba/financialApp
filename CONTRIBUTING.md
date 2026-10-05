# Współpraca

Przeczytaj [AGENTS.md](AGENTS.md) i zaakceptowane [ADR-y](docs/adr/ADR.md). Projekt ma prosty model: wspólny miesięczny budżet, osobiste kieszonkowe jako końcowy transfer oraz klasyfikacja paragonów po pozycjach. Kwoty są całkowitymi groszami.

1. Utwórz branch z `main` i uruchom projekt według README.
2. Zmień najmniejszy kompletny fragment. Dodaj migrację, jeśli zmienia się schemat. Nie wprowadzaj fikcyjnego powodzenia OCR.
3. Zatrzymaj lokalne web/API i uruchom `WEBKIT=1 ./scripts/check.sh` (wcześniej `npx playwright install --with-deps chromium webkit`). Sprawdź zmienione ekrany mobile/desktop; zachowaj dane produkcji poza testami.
4. Otwórz PR z opisem problemu, zmiany i weryfikacji. CI musi przejść przed merge. Używamy squash merge.

Nie commituj `.env`, kluczy, prywatnych zdjęć, arkuszy, eksportów ani backupów. `fixtures/` zawiera wyłącznie syntetyczny paragon testowy. Sekrety wdrożenia nie są dostępne w workflow testującym PR.

Merge do `main` uruchamia produkcyjny release. Przed merge zmian migracji sprawdź zgodność z poprzednią wersją aplikacji: rollback obrazów nie cofa automatycznie bazy. Szczegóły: [CI/CD](docs/CI_CD.md).
