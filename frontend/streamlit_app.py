# frontend/streamlit_app.py
import os
import requests
import streamlit as st

import uuid

# --- estado inicial (tem que existir antes de qualquer uso) ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())  # id único da sessão
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_id" not in st.session_state:
    st.session_state.current_id = None
if "started" not in st.session_state:
    st.session_state.started = False


DEFAULT_BACKEND = os.getenv("BACKEND_URL") or "http://127.0.0.1:8010"

# guarda o backend url no estado para não “sumir” a cada st.rerun()
if "backend_url" not in st.session_state:
    st.session_state.backend_url = DEFAULT_BACKEND

st.set_page_config(page_title="Assistente de Requisitos (MVP)", page_icon="🧭")

# ---------- Sidebar ----------
st.sidebar.title("Configurações")
backend_url = st.sidebar.text_input(
    "Backend URL",
    value=st.session_state.backend_url,
    key="backend_url",
)

if st.sidebar.button("✅ Testar /health"):
    try:
        r = requests.get(f"{backend_url}/health", timeout=5)
        r.raise_for_status()
        st.sidebar.success(f"OK: {r.json()}")
    except Exception as e:
        st.sidebar.error(f"Erro: {e}")

# ---------- Estado ----------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_id" not in st.session_state:
    st.session_state.current_id = None
if "started" not in st.session_state:
    st.session_state.started = False

# ---------- Chamada à API ----------
def call_next(answer: str | None = None):
    try:
        payload = {
            "session_id": st.session_state.session_id,
            "current_id": st.session_state.current_id,   # None para 1ª pergunta
            "answer": None if answer in (None, "") else answer
        }

        r = requests.post(f"{backend_url}/interview/next", json=payload, timeout=10)
        r.raise_for_status()  # se der 4xx/5xx, levanta exceção com detalhes
        data = r.json()

        # mostra a resposta do assistente
        st.session_state.messages.append({"role": "assistant", "content": data["message"]})

        # atualiza ponteiro do fluxo
        st.session_state.current_id = data.get("next_id")

        # terminou?
        if data.get("done"):
            st.session_state.started = False
            st.success("Entrevista finalizada! (MVP)")

    except requests.HTTPError as e:
        # mostra o corpo retornado pelo backend (útil para 422/500)
        body = getattr(e.response, "text", "")
        st.error(f"Erro ao chamar backend: {e}\n{body}")
    except Exception as e:
        st.error(f"Erro ao chamar backend: {e}")


# ---------- UI ----------
st.title("🧭 Assistente de Requisitos — MVP")
st.write("Chat simples para conduzir uma entrevista inicial com o PO/stakeholders.")

# duas colunas; usaremos a primeira para o botão
# duas colunas; usaremos a primeira para o botão
col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 Reiniciar entrevista", use_container_width=True):
        try:
            requests.post(
                f"{backend_url}/reset",
                json={"session_id": st.session_state.session_id},
                timeout=5,
            )
        except Exception as e:
            st.sidebar.warning(f"Não consegui resetar no backend: {e}")

        st.session_state.messages = []
        st.session_state.current_id = None
        st.session_state.started = False
        st.rerun()



# Auto-start: se ainda não começou e não temos current_id, pede a 1ª pergunta
if not st.session_state.started and st.session_state.current_id is None:
    call_next()          # sem resposta -> backend retorna a 1ª pergunta
    st.session_state.started = True

# Histórico
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "assistant" else "user"
    with st.chat_message(role):
        st.markdown(msg["content"])

# Entrada do usuário
user_input = st.chat_input("Digite sua resposta...")
if user_input:
    # 1) mostra a fala do usuário no chat
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 2) chama o backend para pegar a próxima mensagem / próximo nó
    call_next(user_input)

    # 3) força re-render para já exibir a resposta do "assistente"
    st.rerun()
