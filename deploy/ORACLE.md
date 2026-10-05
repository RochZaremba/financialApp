# Release dla finance.rochzaremba.com

Serwer `ssh oracle` to Ubuntu ARM64. Porty 80/443 obsługuje istniejący systemowy Caddy; dlatego używaj **compose.oracle.yaml**, a nie compose.production.yaml z drugim proxy. Produkcyjny web jest dostępny wyłącznie na `127.0.0.1:8810`; PostgreSQL i API nie mają portów hosta.

## Przygotowany release

Obrazy `finance-api:20261005T133723Z` i `finance-web:20261005T133723Z` są budowane natywnie na serwerze. Katalog: `~/finance/releases/20261005T133723Z`. Przygotowanie nie publikuje domeny ani nie uruchamia produkcyjnej bazy. Testy używają odrębnych usuwanych wolumenów QA.

Kopia gotowych obrazów to `finance-20261005T133723Z-arm64-images.tar.gz` z sumą `images.sha256` w tym samym katalogu. Możesz ją przenieść na inny serwer ARM64 i załadować bez ponownego builda:

```bash
sha256sum --check images.sha256
docker load -i finance-20261005T133723Z-arm64-images.tar.gz
```

Prywatny `.env.production` ma domenę, tag wydania, nowe losowe hasło PostgreSQL oraz konfigurację Gemini z lokalnego projektu. Nie zawiera lokalnej bazy, hasła demo ani danych Rocha/Kai. Nie publikuj tego pliku ani nie dołączaj go do obrazów. Archiwum źródeł go nie zawiera. W środowisku production logowanie demo jest wyłączone; obrazy nie zawierają seeda ani zdjęcia demonstracyjnego. Pierwszy użytkownik tworzy konto i własne gospodarstwo.

## Aktywacja na serwerze

```bash
ssh oracle
cd ~/finance/releases/20261005T133723Z
./deploy/oracle-activate.sh
```

Skrypt uruchamia gotowe obrazy z migracjami i pustą bazą projektu `finance`, czeka na healthcheck, robi kopię obecnej konfiguracji Caddy, dodaje osobny plik `finance.caddy`, waliduje konfigurację i przeładowuje Caddy. Nie zatrzymuje istniejących stron. W razie odrzucenia konfiguracji przywraca pliki Caddy. Kopia znajduje się w `/etc/caddy/finance-backup-<czas>/`.

Domena musi kierować na Oracle. W DNS jest obecnie proxy Cloudflare; rekord origin musi wskazywać ten serwer, a tryb SSL/TLS powinien być **Full (strict)**. Caddy uzyskuje certyfikat automatycznie. Po aktywacji sprawdź:

```bash
curl --fail https://finance.rochzaremba.com/api/health
docker compose --env-file .env.production -p finance -f compose.oracle.yaml ps
```

Otwórz https://finance.rochzaremba.com i utwórz swoje konto. Zaproś Kaję linkiem z Ustawień. Nie ma domyślnego produkcyjnego użytkownika ani hasła.

## Obsługa

Wszystkie polecenia wykonuj z katalogu aktywnego release:

```bash
# Logi (nie udostępniaj prywatnych plików środowiska)
docker compose --env-file .env.production -p finance -f compose.oracle.yaml logs --tail=100 api web
# Zatrzymanie aplikacji; dane pozostają
docker compose --env-file .env.production -p finance -f compose.oracle.yaml stop
# Ponowne uruchomienie
docker compose --env-file .env.production -p finance -f compose.oracle.yaml up -d --no-build --wait
```

Nigdy nie używaj `down -v` na projekcie `finance`: usuwa dane. Przy kolejnych wydaniach zachowaj ten sam projekt Compose, hasło PostgreSQL i wolumeny `finance_postgres_data` oraz `finance_receipt_data`. Zmiana hasła w pliku nie zmienia hasła istniejącej bazy. Powrót do starszego obrazu wymaga zgodności z już zastosowanymi migracjami; nie wykonuj automatycznych downgrade.

## Kopie bezpieczeństwa

```bash
umask 077
backup_dir="$HOME/finance/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
docker compose --env-file .env.production -p finance -f compose.oracle.yaml exec -T db pg_dump -U dom -d dom > "$backup_dir/database.sql"
docker compose --env-file .env.production -p finance -f compose.oracle.yaml exec -T api tar -C /data -czf - receipts > "$backup_dir/receipts.tar.gz"
cp .env.production "$backup_dir/.env.production"
```

Wykonuj kopie regularnie i przed aktualizacjami, przechowuj prywatnie także poza serwerem. Backup zdjęć i bazy wykonuj bez równoległych zapisów (np. po `stop web api`, przy działającej bazie). Sprawdź próbne odtworzenie w osobnym projekcie przed poleganiem na backupie. Produkcja wymaga jednego procesu API, zgodnie z limitami opisanymi w README.

## Automatyczne kolejne wydania

Początkowa wersja została aktywowana. Kolejne wydania obsługuje [GitHub CI/CD](../docs/CI_CD.md): tylko merge PR do main, po pełnych testach, wdraża ARM64 i publikuje Release. Aktualny release wskazuje `~/finance/current`; używaj jego `.env.production` oraz `~/finance/shared/compose.oracle.yaml`. Zachowane są istniejące wolumeny i konfiguracja AI. W CI/CD nie uruchamiaj ponownie pierwotnego `oracle-activate.sh`: konfiguracja host Caddy jest już aktywna i aktualizacje jej nie zmieniają.
