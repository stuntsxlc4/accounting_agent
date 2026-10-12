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
copy .env.example .env   # macOS/Linux: cp .env.example .env
```

i uzupełnij `.env`.
