# scripts/run_backend.ps1
# Ativa a venv desta pasta e sobe o backend no :8000

# Garante que estamos na raiz do projeto (pasta pai deste script)
Set-Location (Split-Path $PSScriptRoot -Parent)

# Libera execução só nesta sessão
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Ativa a venv (cria se não existir)
if (-not (Test-Path ".\.venv")) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

# Atualiza pip (opcional) e garante dependências
python -m pip install --upgrade pip
pip install -r requirements.txt

# Sobe o backend (altere a porta se quiser)
python -m uvicorn backend.app.main:app --reload --port 8010
