# Szczegółowa instrukcja uruchomienia i obsługi

Polska aplikacja PWA do wspólnego budżetu Rocha i Kai. Trwałe dane w PostgreSQL, rzeczywiste logowanie i izolacja gospodarstw. Next.js/TypeScript/Tailwind + FastAPI/SQLAlchemy/Alembic. Wszystkie kwoty są liczbami całkowitymi w groszach.

## Uruchomienie od zera

Wymagania: Node.js 22+, npm, Python 3.13+ z `venv` i pip, Docker z Compose. Porty 3000, 8000 i 5434 muszą być wolne.

```bash
./scripts/setup.sh
./scripts/dev.sh
```

Otwórz **http://localhost:3000** i wybierz **Zobacz wersję demo**. Możesz też utworzyć własne konto i gospodarstwo. Setup generuje lokalne hasło bazy w prywatnym `.env`, instaluje zablokowane wersje zależności, uruchamia PostgreSQL, stosuje migracje i zasiewa dane. Ponowne wykonanie nie kasuje danych. Ctrl+C zatrzymuje web/API wraz z procesami reload i zwalnia porty; baza i dane pozostają. Zajęty port powoduje czytelny błąd zamiast połączenia z poprzednim serwerem.

Demo: plan października 2026, dwa źródła wynagrodzenia (Roch: 6000 zł, Kaja: 4000 zł), kategorie, po 600 zł kieszonkowego dla Rocha i Kai, rzeczywiste wpisy wydatków, dwa cele, trzy płatności cykliczne oraz mieszany paragon Lidl z jedną niepewną pozycją. Konto `roch@demo.local` lub `kaja@demo.local` można zalogować hasłem `DEMO_PASSWORD` z `.env`. Przycisk demo działa wyłącznie w środowisku development; nie jest dostępny produkcyjnie.

Budżet wybiera miesiąc według Europe/Warsaw. Jeśli otwierasz aplikację po październiku 2026, wybierz październik 2026 selektorem w nagłówku, aby obejrzeć przykładowy plan.

Wersja zoptymalizowana:

```bash
# Najpierw zatrzymaj ./scripts/dev.sh (Ctrl+C).
npm run build
./scripts/start.sh
```

## Co działa

- Rejestracja, logowanie Argon2, odwoływalne sesje HttpOnly, tworzenie domu i jednorazowe siedmiodniowe zaproszenia dla domowników.
- Miesięczne nazwane źródła dochodu z przypisaniem do domowników i automatyczną sumą, koperty, kieszonkowe i cele; jasne „0 zł do przydzielenia”; migawki nazw i grup w historycznych miesiącach.
- Wpływy, wydatki, podział jednego wydatku na kategorie, terminalne kieszonkowe, przelewy między kontami i wpłaty na cele.
- Prywatne zdjęcia paragonów, edycja OCR i pozycji, niepewne kategorie, pamiętanie reguł gospodarstwa i atomowe zatwierdzanie do transakcji z podziałem.
- Inbox nieprzypisanych wydatków, niepewnych pozycji, błędów odczytu, podejrzeń duplikatu oraz paragonów oczekujących na zatwierdzenie. Zadania ze starych miesięcy mają bezpośrednią ścieżkę rozwiązania.
- Historia z filtrami, szczegółami podziału i paginacją; cele, przewidywane daty, płatności cykliczne z ręcznym potwierdzeniem, salda i kompaktowa analityka/prognoza.
- Kategorie i archiwizacja, reguły klasyfikacji, eksport JSON i usunięcie danych gospodarstwa z potwierdzeniem nazwy.
- Responsywna nawigacja, stany pustych danych, błędów, przetwarzania i braku sieci; manifest, ikony i service worker. Prywatne dane nigdy nie trafiają do cache service workera.

## Paragony i prawdziwy OCR

Brakujące dane można zapisać w szkicu i uzupełnić później. Ilość jest opcjonalna — nie trzeba jej zgadywać. Rabaty wpisuje się ze znakiem minus i przypisuje do kategorii zakupów, których dotyczą. Przed zatwierdzeniem suma pozycji i podział między kategoriami muszą odpowiadać kwocie paragonu.

Tryby `RECEIPT_PROVIDER` w `.env`:

- `fixture`: wyłącznie developerski, rozpoznaje **dokładnie** obraz `fixtures/lidl.png`. Każde inne zdjęcie zostaje uczciwym szkicem do ręcznego uzupełnienia. Niedozwolony w production. Domyślna konfiguracja skryptu setup.
- `manual`: każde prywatne zdjęcie staje się szkicem. Bez wymyślonych pozycji ani fikcyjnego powodzenia OCR.
- `openai`: rzeczywisty multimodalny odczyt przez Responses API, wymagający `OPENAI_API_KEY`. Ustaw `OPENAI_MODEL` na dostępny model obsługujący obraz i Structured Outputs (domyślnie `gpt-4.1-mini`), a następnie zrestartuj API. Wynik przechodzi ścisłą walidację Pydantic. Błędy dostawcy zachowują zdjęcie i tworzą zadanie uzupełnienia.
- `gemini`: odczyt i klasyfikacja pozycji przez Google Gemini API. Wymaga `GEMINI_API_KEY`; model ustawiasz przez `GEMINI_MODEL` (domyślnie `gemini-3.1-flash-lite`). Klucz pozostaje na serwerze. Niepełna, zablokowana lub nieprawidłowa odpowiedź zachowuje zdjęcie do ręcznego uzupełnienia.

Konfiguracja Gemini w `.env`:

```dotenv
RECEIPT_PROVIDER=gemini
GEMINI_API_KEY=twoj_klucz_z_google_ai_studio
GEMINI_MODEL=gemini-3.1-flash-lite
```

Klucz utworzysz w [Google AI Studio](https://aistudio.google.com/apikey). Po zmianie zrestartuj API (`Ctrl+C` i ponownie `./scripts/dev.sh` lub `./scripts/start.sh`). W Dockerze odtwórz usługę API: `docker compose -f compose.production.yaml up -d --build api`. Wybieraj model obsługujący obrazy i JSON Schema; podawaj sam identyfikator modelu, bez prefiksu `models/`. Aktywny dostawca otrzymuje zdjęcie i kategorie potrzebne do odczytu; aplikacja nie przełącza się automatycznie na inną usługę po błędzie.

Adapter Gemini używa `generateContent`, obrazu PNG przez `inlineData` oraz `generationConfig.responseFormat.text` ze schematem JSON i **`mimeType: "APPLICATION_JSON"`** (enum protokołu REST, nie napis `application/json`): [Google Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output), [REST TextResponseFormat](https://ai.google.dev/api/generate-content#TextResponseFormat). Schemat wysyłany do Google opisuje strukturę i typy; wszystkie ograniczenia kwot, dat i długości są sprawdzane na serwerze przez tę samą klasę Pydantic co dla OpenAI. Kwoty pozostają całkowitymi groszami. Obsługa nie wymaga dodatkowego SDK.

Adapter OpenAI używa formatu `text.format` z `json_schema`, przekazuje obraz jako Base64 i ustawia `store:false`: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Images and vision](https://developers.openai.com/api/docs/guides/images-vision). Obaj dostawcy respektują kolejność klasyfikacji: reguła dokładna → znormalizowana → sklep → propozycja AI → człowiek. Progi są konfiguracją serwera. Pewne pozycje są zwarte; edycja jest dostępna jednym kliknięciem. Niepewne pozycje rozwijają pola i szybkie kategorie.

Po odczycie porównujemy sumę pozycji z sumą paragonu. Zatwierdzenie zapisuje osobno Receipt/ReceiptItem oraz Transaction/TransactionAllocation. Powtórne zatwierdzenie zwraca tę samą transakcję. Upload z tym samym `Idempotency-Key` zwraca ten sam paragon także po błędzie OCR i przy równoczesnych próbach; interfejs zachowuje klucz przy ponowieniu po błędzie sieci. Nowy świadomy upload tego samego zdjęcia tworzy osobny szkic z ostrzeżeniem o duplikacie. Podejrzenie duplikatu obejmuje też inne zdjęcie ze zgodnym sklepem, datą i sumą, również po poprawieniu OCR. Kolejny taki wydatek wymaga wyraźnego potwierdzenia osobnego zakupu; dopasowanie nigdy nie przekracza granic gospodarstwa. Niepełny szkic można zapisać bez daty, sumy i kwot pozycji. Rabaty wpisuj jako ujemne pozycje w kategorii zakupów, których dotyczą; wynik kategorii nie może być ujemny.

Przegląd release z rzeczywistym kluczem potwierdził pełny odczyt przez Gemini 3.1 Flash-Lite: 6 pozycji, suma 139,75 zł, przegląd kategorii, zbilansowany podział transakcji i aktualizacja budżetu. Wysłano wyłącznie dołączony syntetyczny paragon. Wcześniejszy Gemini 3.8 Flash zwracał HTTP 503; domyślną konfigurację zmieniono na sprawdzony model. Przy błędzie usługi zdjęcie i szkic pozostają dostępne do ręcznego uzupełnienia. To sprawdzenie jednej próbki, nie gwarancja poprawnego OCR każdego zdjęcia. Można powtórzyć izolowany test z aktywnym kluczem poleceniem `.venv/bin/python scripts/live-ai-review.py`; używa wyłącznie dołączonego syntetycznego paragonu, tworzy i usuwa własną bazę QA, a wywołanie zewnętrznego API może być płatne. Wymaga `npm run build`, uruchomionej bazy i wolnych portów 3001, 8001, 3010.

## Testy i migracje

### Ponowny odczyt i diagnozowanie Gemini

W widoku zapisanego paragonu wybierz „Odczytaj ponownie” i potwierdź wysłanie istniejącego zdjęcia. Wywołanie może być płatne. Wynik najpierw pojawia się jako podgląd; „Zastosuj odczyt do szkicu” zastępuje pola i pozycje, także ręczne lub niezapisane poprawki. Nieudana próba ich nie usuwa. Jeśli szkic zapisano po rozpoczęciu OCR, zastosowanie starego wyniku jest blokowane. Na zatwierdzonym paragonie wynik służy wyłącznie do porównania — nie zmienia wydatku, podziału kategorii ani zapasów.

Historia pokazuje dostawcę/model, czas, status i kod próby. Odróżnia m.in. `RESOURCE_EXHAUSTED` / HTTP 429 (limity lub rozliczenia), 401/403 (klucz/uprawnienia/sieć), 404 (model/adres usługi), 5xx (awaria/przeciążenie), `TIMEOUT`, `MAX_TOKENS`, blokady bezpieczeństwa, brak kandydatów, niezgodność ze schematem i niepełne dane lub `TOTAL_MISMATCH`. Odpowiedź HTTP 200 nie oznacza poprawnego odczytu. Surowe komunikaty/odpowiedzi dostawcy mogą zawierać prywatne dane i nie są ujawniane; kody i bezpieczne nazwy pól wystarczają do rozróżnienia tych klas awarii.

W `/administrator` sekcja „Diagnostyka OCR” grupuje nowe próby Gemini/OpenAI z ostatnich siedmiu dni według modelu, wyniku i kodu. Osobno pokazuje błędy i niepełne odczyty. Dane zaczynają się po wdrożeniu migracji 011; starszych ogólnych błędów nie da się z nich odtworzyć. Aby zbadać zgłaszaną częstość awarii, porównaj kody i modele w tej sekcji zamiast zakładać, że każda awaria oznacza przeciążenie Gemini. Log backendu zawiera identyfikator próby oraz bezpieczne kody, bez zdjęcia, tekstu paragonu czy klucza. Nie zmieniaj modelu ani nie podnoś limitów rozliczeniowych bez sprawdzenia rzeczywistego kodu.

Izolowany, bezpłatny test ponownego OCR i krytycznych przepływów (zatrzymaj web/API; wymagany build i działający PostgreSQL):

```bash
CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python scripts/admin-review.py --ocr --regression -- product.spec.ts
```

Bez systemowego Chromium pomiń tę zmienną i użyj przeglądarki zainstalowanej przez Playwright. Test wykonuje dwa kolejne przebiegi, po 12 kontroli widoków/stanu/dostępności na czterech viewportach; używa syntetycznego paragonu i atrap błędów, bez płatnego OCR. Wyniki: `artifacts/ui-review/ocr-1/` i `ocr-2/`.

### Administrator i zapomniane hasło

Na zaufanym serwerze, po zastosowaniu migracji, utwórz konto administratora:

```bash
cd apps/api
../../.venv/bin/python -m app.create_admin admin@example.com --name "Administrator"
```

Jeśli konto już istnieje, polecenie nadaje uprawnienia bez zmiany hasła i wylogowuje wcześniejsze sesje. Dla nowego konta pyta o hasło i jego powtórzenie bez wyświetlania wartości. Nie podawaj hasła w argumentach, repozytorium ani na czacie. W Dockerze użyj `docker compose -f compose.production.yaml exec api python -m app.create_admin admin@example.com`. Konta demonstracyjne nie mogą zostać administratorami.

Zaloguj się zwykłym formularzem i otwórz `/administrator` (także z menu Administrator lub Więcej). Administrator nie musi należeć do gospodarstwa. Wpisz e-mail użytkownika, nowe hasło dwukrotnie i własne hasło administratora. Najpierw potwierdź tożsamość proszącej osoby, a nowe hasło przekaż prywatnie. Reset wylogowuje wszystkie sesje użytkownika i zapisuje identyfikatory administratora/użytkownika oraz czas w `password_reset_events`, bez haseł. Limit wynosi 5 prób na 5 minut na administratora. Rola nie przyznaje dostępu do cudzych danych finansowych.

Panel nie zmienia haseł kont administratorów. Zapomniane hasło administratora nadal zmienia właściciel serwera poleceniem `python -m app.reset_password admin@example.com`. Utworzenie administratora jest świadomą operacją właściciela; migracja nie nadaje nikomu tej roli automatycznie.

Zatrzymaj lokalne web/API (Ctrl+C). `check.sh` buduje i uruchamia własne serwery z testowanego kodu, wykonuje testy i przeglądy ekranów, następnie zatrzymuje serwery. Przeglądarka używa świeżej, jednorazowej bazy i osobnego katalogu zdjęć, usuwanych po przebiegu; dane Waszego domu pozostają. Tryb testów wymusza fixture i nie wywołuje płatnego AI. Zainstaluj silnik przeglądarki, potem:

```bash
npx playwright install chromium
./scripts/check.sh

# Osobny przegląd wizualny: w drugim terminalu uruchom ./scripts/start.sh.
node scripts/visual-review.mjs moj-przeglad
node scripts/state-review.mjs
```

Izolowany test panelu administratora (zatrzymaj web/API; wymaga zbudowanego frontendu i działającej bazy):

```bash
.venv/bin/python scripts/admin-review.py --regression
# W środowisku z systemowym Chromium:
CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python scripts/admin-review.py --regression
```

Skrypt tworzy i usuwa własną bazę oraz konta QA, wykonuje dwa przebiegi odzyskiwania hasła i sprawdza cztery rozmiary ekranu oraz dostępność. `--regression` dodaje istniejące E2E Chromium. Hasła QA są losowane w pamięci; dane użytkowników i klucze OCR nie są używane. Zrzuty i wyniki: `artifacts/ui-review/admin-1` i `admin-2`.

`check.sh`: lint bez ostrzeżeń, TypeScript, Vitest, produkcyjny build, Ruff check/format, migracje i pytest na osobnej bazie `dom_test`, Playwright mobile/desktop oraz zrzuty wszystkich ekranów i stanów z kontrolą dostępności i overflow. Nigdy nie czyści bazy development. Nazwę katalogu dowodów zmienia `REVIEW_PASS`, np. `REVIEW_PASS=review-1 ./scripts/check.sh`. Porty 3000/8000 muszą być wolne; skrypt odmawia przebudowy działającego Next.js, aby nie uszkodzić serwowanych plików. `./scripts/check.sh --static` wykonuje te same bramki bez przeglądarki (wymaga wolnego portu 3000); po zbudowaniu uruchom `./scripts/start.sh` i osobno `npm run e2e`, aby sprawdzić produkcyjny build. Testy izolacji gospodarstw, arytmetyki, duplikatów, sum kategorii, historii, kieszonkowego i płatności cyklicznych są w `apps/api/tests`. Krytyczne scenariusze przeglądarkowe są w `apps/web/e2e`. Opcjonalnie `npx playwright install webkit` i `WEBKIT=1 npm run e2e` dodają testy silnika Safari. Na Linuksie bez bibliotek WebKit (np. Arch) zatrzymaj lokalne serwery i uruchom pełny zestaw przez oficjalny kontener: `PLAYWRIGHT_DOCKER=1 WEBKIT=1 ./scripts/check.sh`. Skrypt dobiera wersję obrazu do zainstalowanego Playwright; Docker używa sieci hosta i wymaga Linuksa. `node scripts/webkit-offline.mjs` dodatkowo sprawdza prawdziwą awarię sieci: emulator Playwright 1.63 ma błąd SW/offline w WebKit.

```bash
cd apps/api
../../.venv/bin/python -m alembic upgrade head
```

Migracje: `001` tworzy niezmienny schemat domeny oraz odroczone ograniczenie PostgreSQL sprawdzające sumy podziału wydatków; `002` dodaje rejestr idempotencji tworzenia gospodarstw, kont, celów, kategorii i stałych wydatków. `003` zapewnia powrót do każdego niezatwierdzonego paragonu przez Inbox. `004` pozwala zachować nieznane kwoty w szkicu jako null oraz ujemne rabaty; finalizacja nadal wymaga kompletnych danych i dokładnej sumy. Downgrade `004` odmawia działania, jeśli istnieją częściowe lub ujemne pozycje, zamiast kasować dane. Migracje zostały sprawdzone na świeżej bazie, wraz z bezpiecznym downgrade/upgrade. Skrypty dev/start stosują nowe migracje przed uruchomieniem API.

Artefakty przeglądu są w ignorowanym `artifacts/ui-review/`, wyniki testów w `artifacts/`, raport i lista poprawek w `docs/quality/LOOP_LOG.md`. Review obejmuje 390×844, 430×932, 768×1024 i 1440×900.

Końcowa weryfikacja release: dwa kolejne pełne czyste przebiegi po ostatniej poprawce, każdy z 7 testami frontendowymi, 63 testami API, 18 testami E2E Chromium/WebKit oraz 84 kontrolami ekranów i stanów. Lint, typecheck i build przechodzą. Osobno sprawdzono uruchomienie od zera, produkcyjny stack przez HTTPS oraz dwa rzeczywiste odczyty syntetycznego paragonu przez Gemini. Dokładne wyniki, zakres i ograniczenia: [Loop Log](quality/LOOP_LOG.md).

## Wdrożenie

**Oracle, `finance.rochzaremba.com`:** gotowy wariant ARM64 korzystający z istniejącego systemowego Caddy jest w [deploy/ORACLE.md](../deploy/ORACLE.md). Używa `compose.oracle.yaml`, prywatnego `.env.production` i portu loopback 8810. Obrazy produkcyjne nie zawierają seeda ani demonstracyjnego zdjęcia; start nie zasiewa danych. Instrukcja zawiera aktywację przygotowanego release oraz kopie bezpieczeństwa.

Przygotowany wariant jednego serwera z Docker Compose i Caddy:

1. W prywatnym `.env` ustaw `DOMAIN`, mocne `POSTGRES_PASSWORD`, `RECEIPT_PROVIDER=manual`, `openai` albo `gemini` oraz klucz wybranego dostawcy (`OPENAI_API_KEY` lub `GEMINI_API_KEY`). Użyj losowego hasła URL-safe (np. wygenerowanego przez `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`). Zmiana `.env` nie zmienia hasła istniejącego wolumenu PostgreSQL; jego rotację wykonuje się także w bazie. Domena musi wskazywać serwer; porty 80/443 muszą być dostępne.
2. Uruchom:

```bash
docker compose -f compose.production.yaml up -d --build
```

Caddy obsługuje HTTPS; API i PostgreSQL nie mają publicznych portów. Produkcja wymaga HTTPS, odrzuca fixture i wyłącza logowanie demo. Migracje wykonują się przed startem API. Używaj jednego procesu API, ponieważ praktyczne limity logowań i OCR są w pamięci procesu. Uploady: 12/osobę/godzinę i 60/godzinę na wdrożenie; ponowienie tego samego zapisu nie zużywa kolejnego limitu. Zdjęcia mają limit 10 MB oraz 30 milionów pikseli; wynik po usunięciu metadanych jest również ograniczony do 10 MB. Zabezpiecz i regularnie archiwizuj oba trwałe wolumeny: `postgres_data` i `receipt_data`. Nie usuwaj wolumenów bez świadomej decyzji o utracie danych.

Zaproszenia przekazuje użytkownik — aplikacja nie wysyła e-maili. Odzyskanie hasła przez właściciela wdrożenia na zaufanym serwerze, bez wpisywania hasła w argumenty:

```bash
cd apps/api
../../.venv/bin/python -m app.reset_password osoba@example.com
```

Zmiana odwołuje wszystkie sesje tej osoby. Hasła są porównywane dokładnie, również z początkowymi i końcowymi spacjami.

Deployment Docker: `docker compose -f compose.production.yaml exec api python -m app.reset_password osoba@example.com`.

Domyślny eksport zawiera dane w JSON, bez sekretów/sesji i bez binarnych zdjęć. Zdjęcia są dostępne tylko członkom domu przez endpoint API; nie są publicznymi plikami. Konto osobiste po wypłacie kieszonkowego jest poza wspólnym budżetem. Integracje bankowe są przyszłym źródłem Transaction; nie są częścią MVP.
# Autorzy wpisów i aktywność

W gospodarstwie ekran `/aktywnosc` (Aktywność na komputerze, Więcej → Aktywność domowników na telefonie) pokazuje, kto zapisał paragony, wydatki i wpływy. Domyślny okres odpowiada miesiącowi wybranemu w nagłówku; „Cały okres” uwzględnia wszystkie zachowane wpisy. Liczy się czas dodania w Europe/Warsaw, a nie data zakupu. Wydatki i wpływy mają osobne liczby wpisów i sumy PLN. Paragon jest dokumentem (także szkicem), a jego kwota nie jest ponownie doliczana do wydatków.

Autor paragonu jest widoczny przy jego szczegółach, a autor transakcji w historii i po rozwinięciu wpisu, wraz z czasem dodania. Gdy inny domownik zatwierdzi cudze zdjęcie, paragon należy do osoby dodającej zdjęcie, a zapisany wydatek do osoby zatwierdzającej. Edycja, ponowny OCR i ponowienie tej samej operacji nie zmieniają pierwotnego autora. Starsze wpisy bez autora pozostają oznaczone jako nieznane; kwoty nie oznaczają, kto osobiście zapłacił lub zarobił.

Weryfikacja dwóch domowników i czterech rozmiarów ekranu na izolowanej bazie: `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python scripts/admin-review.py --activity`. Wymaga zatrzymania lokalnych serwerów oraz aktualnego buildu frontendu. Nie zapisuje danych produkcyjnych.
# Liczniki i zdjęcia odczytów

Opcjonalny ekran `/liczniki` jest dostępny w nawigacji oraz pod Więcej → Liczniki i zużycie. Skrót „Odczyt licznika” jest też na ekranie Dodaj. Utwórz nazwany licznik (np. Prąd, Zimna woda, Gaz) z jednostką kWh, m³ lub GJ. Jednostka jest stała; po wymianie/wyzerowaniu licznika utwórz nowy punkt pomiaru, a dla starego wyłącz przypomnienia.

Przycisk „Dodaj odczyt” prowadzi do formularza zdjęcia i stanu. Zdjęcie JPG/PNG/WebP (maks. 10 MB) jest sanitowane i zapisane prywatnie. Jawny odczyt używa istniejącego `RECEIPT_PROVIDER` i jego klucza Gemini/OpenAI. Wysłanie zdjęcia może być płatne; wejście na ekran nigdy nie wywołuje AI. Wspólne limity z OCR paragonów: 12 zdjęć/odczytów na osobę i 60 na usługę na godzinę. Powtórzenie tego samego zatwierdzonego żądania nie wywołuje ponownie dostawcy. Bez klucza lub po błędzie zdjęcie nadal jest dostępne, a stan można wpisać ręcznie. Lista ostatnich zdjęć pozwala wrócić do zachowanej propozycji.

Wynik AI nie nadpisuje wpisanych cyfr i nie zapisuje odczytu. Porównaj propozycję ze zdjęciem, użyj jej lub wpisz własną wartość i zatwierdź datę/stan formularzem. Podaje się cały rosnący stan, z maksymalnie trzema miejscami po przecinku. Jeden licznik ma jeden odczyt dziennie; poprawka/usunięcie istniejącego wpisu wymaga aktualnej rewizji. Niezgodne stany względem wcześniejszego/późniejszego odczytu są odrzucane.

Pierwszy wpis jest punktem odniesienia. Od drugiego wykres pokazuje różnice i średnie na rzeczywistą liczbę dni, także dla nieregularnych odstępów i zużycia zero. Można przełączać „Między odczytami” i „Średnio dziennie” oraz wybierać słupki. Średnie są zaokrąglane do 0,001 jednostki; dodatnia wartość poniżej tej rozdzielczości pokazuje „<0,001”. Wykres obejmuje do sześciu ostatnich okresów, ekran do 500 ostatnich odczytów, a pełna historia pozostaje w eksporcie. Dane w API/eksporcie to całkowite tysięczne zadeklarowanej jednostki; nie są to grosze. Nie powstają transakcje ani automatyczne szacunki kosztu.

Plan odczytów ustawia odstęp 0–365 dni od ostatniego datowanego pomiaru. 0 wyłącza przypomnienie. Komunikat jest widoczny na ekranie liczników, bez push/e-maili. Zdjęcia korzystają z istniejącego prywatnego wolumenu/backupów zdjęć; usunięcie gospodarstwa usuwa również dane i pliki liczników. Migracja 012 jest addytywna i odmawia downgrade z istniejącą historią.

Izolowany przegląd: `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python scripts/admin-review.py --meters`. Używa wyłącznie dokładnego syntetycznego zdjęcia `fixtures/meter.png` w trybie fixture, bez płatnych wywołań. Inne zdjęcia nie otrzymują wymyślonego odczytu. Wymaga aktualnego buildu i zatrzymanych lokalnych serwerów.
