# CI/CD: GitHub → Oracle → Releases

## Zasada publikacji

`CI` działa na pull requestach i pushach do `main`. Release uruchamia wyłącznie **zamknięty i zmergowany PR do main**. Push, tag, otwarcie PR ani zamknięcie bez merge nie wdrażają aplikacji.

Release używa zdarzenia `pull_request_target: closed`, ale wszystkie joby zależą od `merged == true` i wykonują checkout **merge_commit_sha** — już zaakceptowanego kodu w main. Nie wykonujemy niezmergowanego kodu forka z sekretami. Weryfikacja PR ma tylko `contents: read` i nie ma dostępu do środowiska production.

## Pipeline

1. **Quality gates** — setup od zera, lint, typecheck, unit/API/deployment tests, świeże migracje, produkcyjny build, Chromium i iPhone WebKit, 4 viewporty i stany ekranów.
2. **ARM64** — natywny runner [`ubuntu-24.04-arm`](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job), obrazy API/web oznaczone dokładnym SHA commita. Produkcyjne obrazy nie zawierają seeda ani zdjęcia demo.
3. **Production smoke** — świeża baza, prywatne zdjęcia QA, prawdziwy HTTPS przez testowy Caddy, pełne flow rejestracji/budżetu/paragonu/zaproszenia. Bez płatnego OCR i sekretów produkcji.
4. **Artifact** — `finance-v0.1.<run_number>-arm64.tar` zawiera `images.tar.gz`, `release.json` i `SHA256SUMS`; obok jest suma zewnętrznego archiwum. Brak env, użytkowników i danych gospodarstwa.
5. **Deploy Oracle** — odbiornik ograniczonego klucza SSH sprawdza wersję, SHA, dozwolone pliki i checksumy, ładuje obrazy i sprawdza ARM64/revision. Przed migracją zatrzymuje web/API na krótki czas i tworzy prywatny backup PostgreSQL oraz zdjęć. Uruchamia release z istniejącymi wolumenami i tym samym hasłem bazy/Gemini. Sprawdza health origin/public i wyłączenie demo.
6. **Publish** — dopiero po powodzeniu deploymentu tworzy tag i GitHub Release dla dokładnego commita zmerge'owanego PR, z obrazami i sumami. Testy/build/deployment zakończone błędem nie publikują release.

Deploymenty są serializowane w Actions i blokadą na serwerze. GitHub zachowuje aktywny przebieg i najnowszy oczekujący; szybka seria merge może zastąpić starszy oczekujący release. Ponowienie tej samej wdrożonej wersji jest idempotentne. Odbiornik odrzuca starszą wersję i zmianę commita pod istniejącym numerem.

## Konfiguracja repozytorium

Środowisko **production** dopuszcza tylko branch `main`. Zawiera cztery sekrety:

| Secret | Znaczenie |
| --- | --- |
| `ORACLE_HOST` | Host serwera, port SSH 22 |
| `ORACLE_USER` | Użytkownik wdrożenia |
| `ORACLE_SSH_KEY` | Osobny klucz Ed25519 tylko do deploymentu |
| `ORACLE_KNOWN_HOSTS` | Klucz hosta zweryfikowany przez zaufane połączenie SSH |

Kluczy AI i hasła bazy nie dodajemy do GitHub. Uprawnienie `contents: write` ma wyłącznie job publikacji release. Akcje są przypięte do commitów; Dependabot proponuje aktualizacje jako PR.

`main` wymaga pull requesta i zielonego **Quality gates**. Force push i usuwanie main są zablokowane. W repo jednoosobowym nie wymagamy zatwierdzenia własnego PR przez drugą osobę; testy nadal blokują merge. Wspierany jest squash merge.

## Układ na Oracle

```text
~/finance/
  bin/ci-deploy.py                  ograniczony odbiornik, instalowany przez administratora
  shared/.env.production           prywatna baza konfiguracji; ten sam PostgreSQL/AI
  shared/compose.oracle.yaml       konfiguracja usług, bez publicznego API/bazy
  current -> releases/<version>    ostatnie zdrowe wydanie
  releases/<version>/              manifest i prywatny env danej wersji
  backups/<version>-<UTC>/          database.sql, receipts.tar.gz, prywatny env
```

W `authorized_keys` klucz CI ma `restrict,command="/usr/bin/python3 .../ci-deploy.py"`: brak powłoki, PTY i tuneli. Przyjmuje tylko `deploy <semver> <commit>` oraz strumień ściśle ograniczonego archiwum. Nie jest to osobisty klucz administratora. Pierwotny release pozostaje jako poprzednia wersja.

Odbiornik i shared Compose instalujemy administracyjnie, nie zastępujemy ich skryptem z wysłanego archiwum. Zmiana topologii usług wymaga osobnej aktualizacji tych plików. Same zmiany aplikacji/migracji idą przez zwykły merge. Host Caddy i pozostałe strony nie są przeładowywane przy aktualizacjach aplikacji.

## Operacje

```bash
ssh oracle
cd ~/finance/current
# Status i logi
 docker compose --env-file .env.production -p finance -f ~/finance/shared/compose.oracle.yaml ps
 docker compose --env-file .env.production -p finance -f ~/finance/shared/compose.oracle.yaml logs --tail=100 api web
```

Przed aktualizacją wykonywany jest backup przy zatrzymanych web/API — oznacza krótką przerwę dostępności. Stop daje API do 130 sekund na dokończenie trwających zapisów/OCR przed backupem (wywołanie AI ma timeout 75 sekund). Kopie są prywatne; regularnie kopiuj je poza serwer i sprawdzaj odtworzenie. Monitoruj miejsce na dysku. Pipeline nie usuwa danych ani starszych backupów.

Jeśli healthcheck nie przejdzie, przywracane są poprzednie obrazy i pozostaje poprzedni `current`. **Baza nie jest automatycznie cofana ani zastępowana backupem**: migracje muszą pozostawać zgodne z poprzednią wersją. Przy niezgodnej migracji odzyskanie może wymagać ręcznej interwencji. Backup pozostaje nawet przy nieudanym release.

Jeśli deployment udał się, a publikacja Release nie: użyj **Re-run failed jobs** w GitHub Actions. Nie twórz osobnego push/tag jako obejścia. Jeśli wykonasz pełny rerun, odbiornik rozpozna już wdrożony commit. Przed ręcznym rollbackiem sprawdź schemat i manifest; nie używaj `down -v`, `docker system prune` ani automatycznego downgrade.

Archiwum release można zweryfikować `sha256sum --check ...sha256`, rozpakować i załadować `docker load -i images.tar.gz` na serwerze ARM64. Nie zawiera konfiguracji infrastruktury ani danych produkcyjnych — używaj zatwierdzonego `compose.oracle.yaml` i własnego prywatnego env.

## Dowody weryfikacji

Workflow testuje rzeczywisty build, przeglądarki i API na świeżym runnerze. Obrazy z produkcyjnego smoke są tymi samymi obrazami, które trafiają na Oracle — deployment nie buduje ich ponownie. Prywatna konfiguracja jest dziedziczona z serwera, a checksumy i etykieta revision wiążą paczkę z commitem PR. Artefakt obrazów w Actions jest tymczasowy (1 dzień); udany Release zachowuje publiczną paczkę i sumy.

Warunek merge jest zgodny z [dokumentacją zdarzeń GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows). Testy odbiornika SSH obejmują odrzucenie poleceń i niebezpiecznych archiwów, tożsamość/checksumy, zachowanie sekretów, backup przed migracją, rollback obrazów, idempotencję i odmowę starszego deploymentu.
