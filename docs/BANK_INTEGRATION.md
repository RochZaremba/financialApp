# Prywatna integracja mBank

Implementacja: Enable Banking AIS, synchronizacja w tle, porównanie sald, dopasowanie paragonów i Web Push. Funkcja pozostaje wyłączona do jednorazowej aktywacji przez właściciela. Zmiana wymaga zwykłego PR i wdrożenia; samo dodanie klucza do rozmowy nie łączy produkcyjnej bazy z bankiem.

## Pierwsze uruchomienie po wdrożeniu

1. Zaloguj się na własne konto administratora i wybierz Wasze wspólne domostwo. W **Konta → Skonfiguruj bank** sprawdź nazwę i dwie wymienione osoby. Aktywacja wymaga dokładnie dwóch obecnych członków.
2. Wybierz otrzymany od Enable Banking plik klucza `.pem` lub `.pem.txt`. Identyfikator aplikacji podpowiada się z nazwy pliku; porównaj go z panelem dostawcy. Wpisz pełną nazwę domu i swoje hasło, zaznacz zgodę na udostępnienie danych tym dwóm osobom, następnie **Aktywuj tylko dla tego domu**. Klucz trafia przez HTTPS do prywatnego magazynu serwera; nie zapisujemy go w repozytorium, obrazie ani przeglądarkowym localStorage. Aktywacja sprawdza aktywną aplikację PRODUCTION z samym AIS, bez pobierania operacji.
3. Kliknij **Połącz mBank** i przejdź oficjalną zgodę bankową. Dla obecnej aplikacji restricted dostępne są wyłącznie rachunki wcześniej powiązane w panelu Enable Banking. Zarejestrowany redirect powinien być równy `WEB_ORIGIN/`, czyli głównej stronie tej instalacji.
4. Przypisz każdy wybrany rachunek do odpowiedniego konta PLN w aplikacji. Brakujące konto dodaj wcześniej w **Konta → Dodaj konto**. Wybierz datę początku pobierania z ostatnich 90 dni. Przypisanie jest jednorazowe; ponowne połączenie zachowuje istniejące dopasowania po stabilnej tożsamości rachunku. Pierwsza synchronizacja może być uruchomiona przyciskiem; później wykonuje ją serwer.
5. Sprawdź pierwszą historię i saldo początkowe. Cały pierwszy import czeka na sprawdzenie, również operacje z dzisiejszą datą; nie importuj ich ponownie jako nowych wydatków, jeśli są już zapisane. Wybierz dopasowanie do istniejącej transakcji albo jawnie utwórz brakujący wpis. Pierwszy import nie wysyła lawiny powiadomień.
6. Każda z dwóch osób osobno włącza **Powiadomienia na telefon → Włącz na tym urządzeniu**. Android: zgoda przeglądarki. iPhone: iOS 16.4+, Safari → Udostępnij → Do ekranu początkowego, następnie otwarcie z ikony i włączenie powiadomień. Samo otwarcie strony nie prosi o zgodę.

Inne domostwa i dodatkowe osoby nie otrzymują bankowego panelu, feedu ani bankowej części eksportu. Właściciel zarządza zgodą i mapowaniem; druga zatwierdzona osoba może opisywać/dopasowywać wpisy i zarządzać własnymi urządzeniami. Dane zaksięgowane w zwykłym budżecie pozostają wspólnymi danymi domu zgodnie z jego istniejącymi uprawnieniami.

## Codzienna obsługa i różnice

- Serwer sprawdza zaksięgowane operacje co około **6 godzin**, także przy zamkniętej aplikacji. Ręczne odświeżanie respektuje ten sam limit. Dostawca dokumentuje bankowe ograniczenia pobierania w tle; nie obiecujemy aktualizacji natychmiast po płatności. Kolejna próba, ostatni sukces, koniec zgody i bezpieczny kod błędu są widoczne w **Bank**. Po wygaśnięciu wybierz **Odnów zgodę / dodaj rachunek**.
- Po ustaleniu pierwszej historii nowe jednoznaczne obciążenia trafiają do budżetu bez kategorii i do uzupełnienia. Kwota i rachunek pochodzą z banku. Blokady kartowe nie są jeszcze wydatkiem. Wpis bez stabilnego identyfikatora czeka na decyzję zamiast ryzykować podwójne zaksięgowanie.
- Wpływy zawsze trafiają do bankowej listy do uzupełnienia, ale wymagają wyboru dochodu lub przelewu własnego przed zaksięgowaniem w budżecie. Zwrot nie powinien automatycznie udawać wynagrodzenia. Rozpoznane przelewy między własnymi podłączonymi kontami również czekają na połączenie obu stron z jednym przelewem w aplikacji. Jeśli bank nie poda drugiego rachunku, sprawdź opis i popraw klasyfikację ręcznie.
- **Paragon po banku:** wybierz właściwe konto płatności i propozycję „Czy to płatność już pobrana z banku?”. Zatwierdzenie uzupełnia istniejący wydatek, nie tworzy drugiego. **Bank po paragonie:** wybierz pasującą zapisaną transakcję w bankowym wpisie. Zgodność kwoty sama nie oznacza pewnego dopasowania — decyzję zatwierdza użytkownik.
- Obok salda księgowego banku widać saldo aplikacji i **Różnicę do wyjaśnienia**. Aplikacja nie nadpisuje salda początkowego ani nie zeruje rozbieżności. Sprawdź nierozliczone wpływy, historię, gotówkę i przelewy własne. Przy saldzie bankowym pokazujemy czas pobrania; nie jest to saldo dostępne po blokadach.
- W **Do sprawdzenia** i **Konta** jest skrót do bankowej listy. Powiadomienia mają ogólną treść, bez kwot i odbiorców na blokadzie ekranu. Niedostarczony push nie usuwa wpisu. Można odłączyć każde własne urządzenie; martwe subskrypcje są usuwane przy błędzie dostawcy.

Pierwsza wersja księguje tylko PLN. Pozostałe waluty nie są przeliczane ani automatycznie importowane. Nie rozwiązuje automatycznie każdej rozbieżności historycznej; zapewnia źródło operacji i jawne uzgodnienie.

## Sekrety, backup i odłączenie

Konfiguracja domyślnie znajduje się w `RECEIPT_STORAGE/.bank/config.json`; opcjonalny `BANK_CONFIG_PATH` służy operatorowi. Katalog ma prawa 0700, pliki 0600: klucz RSA dostawcy, osobny klucz szyfrowania, klucz VAPID i konfiguracja wiążąca dom/dwie osoby. Sesje, identyfikatory rachunków dostawcy i subskrypcje w PostgreSQL są szyfrowane. W odpowiedziach widać tylko końcówki rachunków. Moduł bankowy nie dodaje narzędzi do ogólnego katalogu MCP. Eksport nigdy nie zawiera kluczy, sesji ani urządzeń.

**Istniejący prywatny backup wolumenu paragonów obejmuje teraz również `.bank/`.** Chroń go razem z kopią bazy i nie publikuj żadnego z tych archiwów. Odtwarzaj bazę i jej klucz szyfrowania razem; utrata klucza uniemożliwia odczyt zaszyfrowanych sesji/urządzeń. Publiczny pakiet release zawiera wyłącznie obrazy/manifest, bez wolumenu. Po zmianie prawa na zbyt szerokie bank wyłącza się bezpiecznie zamiast kontynuować pracę.

**Odłącz** natychmiast zatrzymuje pobieranie, cofa zgodę u dostawcy i zachowuje zaksięgowaną historię. Przy niedostępności API cofnięcie jest ponawiane; jego status jest widoczny. Przed usunięciem domu wszystkie zgody muszą być odwołane. Usunięcie domu usuwa feed, wpisy, urządzenia i prywatne pliki kluczy. Backupy podlegają osobnej retencji operatora.

Panel nie nadpisuje klucza, nie przenosi integracji między domami i nie zatwierdza nowych osób automatycznie. Rotację dostawcy/zmianę zatwierdzonych użytkowników wykonuje zaufany operator po cofnięciu zgód i zabezpieczeniu historii. Nie usuwaj klucza szyfrowania z aktywnej instalacji. Awaryjna aktywacja z SSH jest dostępna przez `python -m app.bank_setup --household-id … --app-id … --owner-email … --key-stdin`; klucz podaj na stdin, nigdy jako argument czy komendę z jego treścią. Zwykła aktywacja przez panel nie wymaga SSH ani nowej konfiguracji Compose.

## Weryfikacja i granice dowodów

Sprawdzono podpisanym odczytem metadanych aktywną aplikację PRODUCTION/AIS i obecność mBank PL personal w katalogu. Dostawca oznacza obecnie mBank jako **beta**. Nie utworzono rzeczywistej sesji bankowej, nie pobrano prywatnych operacji i nie zmieniono salda produkcyjnego. Rejestracja restricted nie jest obietnicą bezpłatnej usługi ani ogólnego dostępu do cudzych rachunków.

Automatyczne testy korzystają wyłącznie z syntetycznego dostawcy i kluczy. Pokrywają paginację, ponowienia, limity, zmiany członkostwa podczas HTTP, izolację domów/osób, ponowne połączenie, dokładne grosze, przelewy własne, paragon przed/po banku, brak duplikatów, eksport/usuwanie i kolejkę powiadomień. Testy przeglądarkowe przechodzą realny formularz aktywacji i callback przez proxy Next; screenshoty, WCAG i szerokości 390/430/768/1440 są w artefaktach. Szczegóły wyników: [LOOP_LOG.md](quality/LOOP_LOG.md), architektura: [ADR-022](adr/ADR-022-private-bank-synchronization.md).

Po wdrożeniu pozostaje zatwierdzenie rzeczywistej zgody i sprawdzenie pierwszego wyciągu przez właściciela oraz dostarczenia push na fizycznym Androidzie/iPhonie. Test syntetycznej kolejki nie dowodzi doręczenia na telefon. Nie ma jeszcze deklaracji działającego połączenia produkcyjnego.

Źródła: [Enable Banking API](https://enablebanking.com/docs/api/reference/), [FAQ i ograniczenia](https://enablebanking.com/docs/faq/).
