# Prywatna integracja mBank

Implementacja: Enable Banking AIS, synchronizacja w tle, porównanie sald, dopasowanie paragonów i Web Push. Funkcja pozostaje wyłączona do jednorazowej aktywacji przez właściciela. Zmiana wymaga zwykłego PR i wdrożenia; samo dodanie klucza do rozmowy nie łączy produkcyjnej bazy z bankiem.

## Pierwsze uruchomienie po wdrożeniu

1. Zaloguj się na własne konto administratora i wybierz Wasze wspólne domostwo. W **Konta → Skonfiguruj bank** sprawdź nazwę i dwie wymienione osoby. Aktywacja wymaga dokładnie dwóch obecnych członków.
2. Wybierz otrzymany od Enable Banking plik klucza `.pem` lub `.pem.txt`. Identyfikator aplikacji podpowiada się z nazwy pliku; porównaj go z panelem dostawcy. Wpisz pełną nazwę domu i swoje hasło, zaznacz zgodę na udostępnienie danych tym dwóm osobom, następnie **Aktywuj tylko dla tego domu**. Klucz trafia przez HTTPS do prywatnego magazynu serwera; nie zapisujemy go w repozytorium, obrazie ani przeglądarkowym localStorage. Aktywacja sprawdza aktywną aplikację PRODUCTION z samym AIS, bez pobierania operacji.
3. Kliknij **Połącz mBank** i przejdź oficjalną zgodę bankową. Dla obecnej aplikacji restricted dostępne są wyłącznie rachunki wcześniej powiązane w panelu Enable Banking. Zarejestrowany redirect powinien być równy `WEB_ORIGIN/`, czyli głównej stronie tej instalacji.
4. Przypisz każdy wybrany rachunek do odpowiedniego konta PLN w aplikacji. Brakujące konto dodaj wcześniej w **Konta → Dodaj konto**. Wybierz datę początku pobierania z ostatnich 90 dni. Przypisanie jest jednorazowe; ponowne połączenie zachowuje istniejące dopasowania po stabilnej tożsamości rachunku. Pierwsza synchronizacja może być uruchomiona przyciskiem; później wykonuje ją serwer.
5. Sprawdź pierwszą historię i saldo początkowe. Cały pierwszy import czeka na sprawdzenie, również operacje z dzisiejszą datą; nie importuj ich ponownie jako nowych wydatków, jeśli są już zapisane. Jednoznaczne dopasowanie do zapisanego wpisu połączy się automatycznie; przy kilku propozycjach wybierz właściwą. Brakujący wpis z pierwszej historii utwórz świadomie. Pierwszy import nie wysyła lawiny powiadomień.
6. Każda z dwóch osób osobno włącza **Powiadomienia na telefon → Włącz na tym urządzeniu**. Android: zgoda przeglądarki. iPhone: iOS 16.4+, Safari → Udostępnij → Do ekranu początkowego, następnie otwarcie z ikony i włączenie powiadomień. Samo otwarcie strony nie prosi o zgodę.

Inne domostwa i dodatkowe osoby nie otrzymują bankowego panelu, feedu ani bankowej części eksportu. Właściciel zarządza zgodą i mapowaniem; druga zatwierdzona osoba może opisywać/dopasowywać wpisy i zarządzać własnymi urządzeniami. Dane zaksięgowane w zwykłym budżecie pozostają wspólnymi danymi domu zgodnie z jego istniejącymi uprawnieniami.

## Codzienna obsługa i różnice

- Serwer sprawdza zaksięgowane operacje co około **6 godzin**, także przy zamkniętej aplikacji. Ręczne odświeżanie respektuje ten sam limit. Dostawca dokumentuje bankowe ograniczenia pobierania w tle; nie obiecujemy aktualizacji natychmiast po płatności. Kolejna próba, ostatni sukces, koniec zgody i bezpieczny kod błędu są widoczne w **Bank**. Po wygaśnięciu wybierz **Odnów zgodę / dodaj rachunek**.
- Po ustaleniu pierwszej historii nowe jednoznaczne obciążenia trafiają do budżetu bez kategorii i do uzupełnienia. Kwota i rachunek pochodzą z banku. Blokady kartowe nie są jeszcze wydatkiem. Wpis bez stabilnego identyfikatora czeka na decyzję zamiast ryzykować podwójne zaksięgowanie.
- Nowy zaksięgowany wpływ może być automatycznym zwrotem, gdy ma stały identyfikator, pasujący rachunek i kontrahenta oraz dokładnie jeden możliwy zakup z ostatnich 90 dni. Pełny zwrot pasuje do pozostałej kwoty zakupu; częściowy wymaga dodatkowo wskazania zwrotu w opisie. Zwrot pomniejsza wydatki i kategorie, nie jest nowym dochodem. Dwa równe obciążenia nie są zwrotem. Pozostałe wpływy czekają na opis lub dopasowanie. Rozpoznane przelewy między własnymi podłączonymi kontami również czekają na połączenie obu stron z jednym przelewem w aplikacji. Jeśli bank nie poda drugiego rachunku, sprawdź opis i popraw klasyfikację ręcznie.
- **Paragon po banku:** po wybraniu właściwego konta jedyna pasująca płatność połączy się przy zatwierdzeniu paragonu, bez dodatkowej akceptacji pary i bez drugiego wydatku. **Bank po paragonie/wpisie:** jedyna para po rachunku, kwocie i oknie ±7 dni łączy się automatycznie. Automat sprawdza także drugą stronę: dwie płatności konkurujące o jeden paragon pozostają do wyboru. Gdy to inny zakup, użyj „To jednak osobny zakup”; ta decyzja jest pamiętana i późniejszy automat jej nie cofnie.
- Obok salda księgowego banku widać saldo aplikacji i **Różnicę do wyjaśnienia**. Aplikacja nie zeruje rozbieżności automatycznie. Właściciel może użyć **Wyrównaj saldo aplikacji do banku**: przed potwierdzeniem widzi obie kwoty i korektę. Zapisywana jest osobna historia korekt z autorem/czasem, bez zmiany salda początkowego i bez dochodu/wydatku w budżecie. Zmiana salda w trakcie potwierdzania zatrzymuje zapis; ponowienie żądania nie dodaje drugiej korekty. Najpierw sprawdź zaległe wpisy: dopisanie ich później znowu zmieni saldo. Sprawdź nierozliczone wpływy, historię, gotówkę i przelewy własne. Przy saldzie bankowym pokazujemy czas pobrania; nie jest to saldo dostępne po blokadach.
- W **Do sprawdzenia** i **Konta** jest skrót do bankowej listy. Powiadomienia mają ogólną treść, bez kwot i odbiorców na blokadzie ekranu. Niedostarczony push nie usuwa wpisu. Można odłączyć każde własne urządzenie; martwe subskrypcje są usuwane przy błędzie dostawcy.

Pierwsza wersja księguje tylko PLN. Pozostałe waluty nie są przeliczane ani automatycznie importowane. Nie rozwiązuje automatycznie każdej rozbieżności historycznej; zapewnia źródło operacji i jawne uzgodnienie.

## Zwroty i istniejąca historia

W **Transakcje → szczegóły zakupu → Zarejestruj zwrot** zapiszesz pełny lub częściowy zwrot na wskazane konto PLN. Suma zwrotów nie może przekroczyć zakupu. Częściowe zwroty dzielimy w dokładnych groszach proporcjonalnie według pozostałych kategorii; gdy zakup jeszcze nie ma kategorii, zwroty przejmą je po jego uzupełnieniu. Koszt zmniejsza się w miesiącu otrzymania zwrotu, a zamknięty miesiąc zakupu pozostaje bez zmian. Zmiany kategorii nie mogą przerabiać zamkniętych miesięcy zwrotów.

W Banku możesz wybrać **Zwrot za wcześniejszy zakup** również ręcznie. Błędny zwrot zmienisz na **To zwykły wpływ, nie zwrot** bez ponownego rejestrowania pieniędzy. Nowe jawne decyzje o zwykłym wpływie nie są nadpisywane. Starszy wpływ bankowy bez zapisanej jawnej decyzji może zostać jednoznacznie przeklasyfikowany, używając istniejącego ruchu pieniężnego. Pierwszy import i stare nierozliczone wpisy bez informacji o pochodzeniu nie tworzą samodzielnie nowych zwrotów; mogą dopasować się do już zapisanej transakcji.

Łączenie działa lokalnie po imporcie, dodaniu wpisu/paragonu, otwarciu Banku i w zadaniu w tle. Nie uruchamia dodatkowego odczytu bankowego i nie skraca sześciogodzinnego limitu.

## Automatyczny Bufor

W **Budżet → Edytuj plan → Koperta buforowa** wybierz kategorię rezerwy. Otwarty istniejący plan z jedną kopertą nazwaną „Bufor” rozpoznajemy przy migracji; zamknięte plany pozostają nietknięte. Miesiąc pamięta wybraną kategorię niezależnie od późniejszej zmiany nazwy, a kopiowanie planu zachowuje wybór.

Do bufora trafia planowany dochód pozostały po innych przydziałach. Gdy inne koperty przekroczą plan, rezerwa pokryje przekroczenia do wysokości dostępnych środków. Szczegóły **Bufor · rezerwa budżetu** pokazują każdą kopertę, przekroczenie, pobraną kwotę i niepokrytą część. Przy niedoborze dzielimy dostępną rezerwę proporcjonalnie w groszach; nic nie jest finansowane fikcyjnymi pieniędzmi. Zwroty i korekty zmniejszające przekroczenia automatycznie zwalniają rezerwę. To przesunięcie dostępności między kopertami, bez drugiego wydatku, zmiany kont lub zakładania nowego dochodu.

## Nieudana synchronizacja

W **Bank → Szczegóły błędu synchronizacji** znajdziesz etap, bezpieczny rodzaj i kod błędu, odpowiedź HTTP (jeśli wystąpiła), czas próby i czas jej trwania. Dane są zapisane w bazie i przetrwają restart API. Nie zawierają treści operacji, numerów rachunków, tokenów ani oryginalnych komunikatów dostawcy. W logach serwera pojawiają się wyłącznie dozwolone kody/etap/rodzaj/HTTP. Po udanej synchronizacji poprzedni błąd znika.

Sześciogodzinny odstęp jest ustawiony w aplikacji i obowiązuje także po błędzie, bez zerowania zgody. Podczas oczekiwania **Synchronizuj teraz** jest nieaktywne; status odświeża się co 30 sekund przy otwartym ekranie. Ręczne żądanie przed terminem nie pobiera operacji i nie jest pokazywane jako sukces. Nieprzypisany rachunek nie uruchamia pobierania ani blokady. Starsze błędy sprzed migracji 016 nie mają odtworzonych szczegółów — pojawią się przy następnej nieudanej próbie. Poprawka diagnostyki sama nie ustala przyczyny wcześniejszego `SYNC_FAILED`.

Pola identyfikatora rachunku drugiej strony, nazwy i opisu operacji są opcjonalne w kontrakcie dostawcy. Parser traktuje ich brak i `null` jako brak informacji, także gdy `iban` lub `name` wewnątrz obiektu są puste. Bez tekstu pokazuje „Operacja bankowa”; nie dopisuje numeru rachunku ani nie zgaduje kontrahenta. Inne nieprawidłowe typy, brak wymaganej kwoty/daty i niezgodna waluta nadal zatrzymują cały import z bezpieczną diagnostyką. Dotychczasowa normalizacja poprawnego IBAN-u i dopasowanie przelewów własnych pozostają zachowane. Kontrakt pól: [Transaction](https://enablebanking.com/docs/api/reference/#transaction), [AccountIdentification](https://enablebanking.com/docs/api/reference/#accountidentification), [PartyIdentification](https://enablebanking.com/docs/api/reference/#partyidentification).

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
