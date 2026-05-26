# scripts/run_frontend.ps1
# Ativa a venv e sobe o Streamlit apontando pro backend local

# Raiz do projeto
Set-Location (Split-Path $PSScriptRoot -Parent)

# Libera execução só nesta sessão
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Ativa a venv (cria se não existir)
if (-not (Test-Path ".\.venv")) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

# Garante dependências
python -m pip install --upgrade pip
pip install -r requirements.txt

# (Opcional) definir BACKEND_URL desta sessão
$env:BACKEND_URL = "http://127.0.0.1:8010"

# Sobe o Streamlit
python -m streamlit run frontend/streamlit_app.py
