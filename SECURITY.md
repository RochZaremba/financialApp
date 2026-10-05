# Bezpieczeństwo

Wspierana jest najnowsza opublikowana wersja. Aplikacja przechowuje prywatne dane finansowe; testuj problemy na syntetycznych danych i osobnym gospodarstwie.

Zgłoszenia dotyczące autoryzacji, sesji, ujawnienia danych lub sekretów wysyłaj przez **Security → Advisories → Report a vulnerability** w tym repozytorium. Nie publikuj ich jako zwykłego issue. Podaj kroki odtworzenia, wersję i oczekiwany rezultat, bez tokenów i danych domowników.

Granice bezpieczeństwa: autoryzacja gospodarstwa na serwerze, prywatne zdjęcia, walidacja plików/modeli AI, idempotencja zapisów, sesje HttpOnly/Secure/SameSite i izolowane środowiska testowe. Sekrety OCR i hasło bazy pozostają na serwerze; GitHub otrzymuje wyłącznie osobny ograniczony klucz wdrożeniowy. Szczegóły architektury: [ADR-007](docs/adr/ADR-007-security-privacy.md) i [ADR-008](docs/adr/ADR-008-local-auth-storage.md).
