# accounting_agent

Pobieranie faktur zakupowych z KSeF za wybrany miesiąc i zapis jako PDF z czytelną nazwą.

## Instalacja

Wymagany [uv](https://docs.astral.sh/uv/). Na Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Następnie w katalogu projektu:

```
uv sync
```

Utwórz plik `.env`:

```
KSEF_ENV=prod
KSEF_NIP=<NIP firmy>
KSEF_CERT_PATH=certs/<nazwa>.crt
KSEF_KEY_PATH=certs/<nazwa>.key
OUTPUT_DIR=<folder na faktury>
```

Certyfikat KSeF (typ „Uwierzytelnienie w systemie KSeF”) i klucz wrzuć do `certs/`.
Hasło do klucza zapisz w systemowym sejfie (Pęk kluczy / Menedżer poświadczeń):

```
uv run ksef ustaw-haslo
```
