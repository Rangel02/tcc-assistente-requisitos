# scripts/run_frontend.ps1
# Ativa a venv e sobe o Streamlit apontando pro backend local

# Garante que estamos na raiz do projeto.
Set-Location (Split-Path $PSScriptRoot -Parent)

# Libera a execução de scripts apenas nesta sessão do PowerShell.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Cria a venv se ela ainda não existir e depois ativa o ambiente.
if (-not (Test-Path ".\.venv")) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

# Instala as dependências necessárias para rodar o frontend.
python -m pip install --upgrade pip
pip install -r requirements.txt

# Define a URL do backend usada pelo Streamlit nesta sessão.
$env:BACKEND_URL = "http://127.0.0.1:8010"

# Inicia a interface Streamlit.
python -m streamlit run frontend/streamlit_app.py
