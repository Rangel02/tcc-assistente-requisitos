# scripts/run_backend.ps1
# Ativa a venv desta pasta e sobe o backend no :8000

# Garante que estamos na raiz do projeto (pasta pai deste script)
Set-Location (Split-Path $PSScriptRoot -Parent)

# Libera a execução de scripts apenas nesta sessão do PowerShell.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Cria a venv se ela ainda não existir e depois ativa o ambiente.
if (-not (Test-Path ".\.venv")) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

# Atualiza o pip e instala as dependências necessárias do projeto.
python -m pip install --upgrade pip
pip install -r requirements.txt

# Inicia a API FastAPI com reload para facilitar testes locais.
python -m uvicorn backend.app.main:app --reload --port 8010
