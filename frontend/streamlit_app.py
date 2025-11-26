# frontend/streamlit_app.py
import os
import requests
import streamlit as st
import uuid

# -----------------------------------------------------------------------------
# Estado inicial da aplicação
# Aqui eu garanto que todas as variáveis de sessão existem antes de usar.
# -----------------------------------------------------------------------------

# aqui eu controlo o id da sessão atual da entrevista
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# aqui eu guardo o histórico das mensagens que apareceram na tela de chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# id da pergunta atual no fluxo (vem do backend)
if "current_id" not in st.session_state:
    st.session_state.current_id = None

# flag simples pra saber se a entrevista já começou ou não
if "started" not in st.session_state:
    st.session_state.started = False

# aqui eu guardo o markdown da ATA quando o backend gera o relatório
if "briefing_md" not in st.session_state:
    st.session_state.briefing_md = ""

# aqui eu guardo os bytes do PDF, quando eu busco o relatório em PDF no backend
if "briefing_pdf" not in st.session_state:
    st.session_state.briefing_pdf = None


# -----------------------------------------------------------------------------
# Configuração básica da página
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Assistente de Levantamento de Requisitos",
    layout="wide",
)

st.title("Assistente de Levantamento de Requisitos – Protótipo de TCC")
st.write(
    "Aqui eu estou simulando a entrevista inicial com o cliente, "
    "fazendo perguntas em sequência e depois gerando um relatório com o que foi respondido."
)

# um subtítulo rápido explicando que é um chat simples de entrevista
st.subheader("Fluxo de perguntas com foco em levantamento de requisitos")
st.write("Abaixo eu mostro um chat simples para conduzir a entrevista com o stakeholder.")


# -----------------------------------------------------------------------------
# Config do backend (ENV > autodetect)
# Aqui eu tento descobrir automaticamente qual URL do backend eu vou acabar usando.
# -----------------------------------------------------------------------------
DEFAULT_BACKEND = os.getenv("BACKEND_URL")  # se vier do script/ENV, usamos
CANDIDATES = [DEFAULT_BACKEND, "http://127.0.0.1:8010", "http://127.0.0.1:8000"]


def detect_backend() -> str:
    """
    Aqui eu tento chamar /health em algumas URLs que são candidatas e uso a primeira
    que responder sem erro. Se nenhuma responder, eu caio em um fallback padrão.
    """
    for url in [c for c in CANDIDATES if c]:
        try:
            r = requests.get(f"{url}/health", timeout=1.5)
            if r.ok:
                return url
        except Exception:
            # se der erro nessa URL, eu só ignoro e tento a próxima
            continue
    # fallback final se nada respondeu
    return "http://127.0.0.1:8000"


# guardo a URL do backend na sessão
if "backend_url" not in st.session_state:
    st.session_state.backend_url = detect_backend()

backend_url = st.session_state.backend_url


# -----------------------------------------------------------------------------
# Sidebar
# Aqui eu deixo tudo que é configuração, diagnóstico e geração de relatório, só para deixar organizadin.
# -----------------------------------------------------------------------------
st.sidebar.title("Configurações")

st.sidebar.markdown("**Backend URL (detectado)**")
st.sidebar.code(backend_url)

if st.sidebar.button("Redetectar /health"):
    # aqui eu to tentando detectar de novo o backend chamando /health
    st.session_state.backend_url = detect_backend()
    backend_url = st.session_state.backend_url
    st.success(f"Detectado: {backend_url}")

st.sidebar.markdown("**Session ID atual**")
st.sidebar.code(st.session_state.session_id)

if st.sidebar.button("Testar /health"):
    """
    Aqui eu só faço uma chamada simples para o /health do backend
    só para eu ver se a API está respondendo OK.
    """
    try:
        r = requests.get(f"{backend_url}/health", timeout=5)
        r.raise_for_status()
        st.sidebar.success(f"OK: {r.json()}")
    except Exception as e:
        st.sidebar.error(f"Erro: {e}")

# --- Gerar ATA / Briefing ---
st.sidebar.markdown("---")
st.sidebar.markdown("### Relatório da entrevista (ATA)")

if st.sidebar.button("Gerar relatório desta sessão"):
    """
    Quando eu clico aqui, eu peço para o backend montar pra mim a ATA em Markdown
    e também já busco o PDF correspondente.
    """
    try:
        # 1) gera/atualiza ATA em Markdown
        r = requests.post(
            f"{backend_url}/briefing",
            json={"session_id": st.session_state.session_id},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        st.session_state.briefing_md = data.get("markdown", "")

        # 2) já nos busca o PDF correspondente
        r_pdf = requests.get(
            f"{backend_url}/briefing/pdf/{st.session_state.session_id}",
            timeout=20,
        )
        r_pdf.raise_for_status()
        st.session_state.briefing_pdf = r_pdf.content

        st.sidebar.success("Relatório (Markdown + PDF) gerado com sucesso.")
    except Exception as e:
        st.sidebar.error(f"Erro ao gerar o relatório: {e}")


# -----------------------------------------------------------------------------
# Chamada à API principal da entrevista
# -----------------------------------------------------------------------------
def call_next(answer: str | None = None) -> None:
    """
    Aqui eu mando a resposta do usuário para o backend e pego a próxima pergunta.

    Regras:
    - Na primeira chamada eu mando current_id = None para o backend começar do 'start';
    - Depois disso, eu sempre envio o current_id atual e a resposta que o usuário digitou;
    - O backend devolve:
      - message: texto da próxima pergunta;
      - next_id: id do próximo nó no fluxo;
      - done: True/False para indicar se acabou a entrevista.
    """
    try:
        payload = {
            "session_id": st.session_state.session_id,
            # None na primeira vez para o backend saber que é o começo do fluxo
            "current_id": st.session_state.current_id,
            # se vier string vazia, eu mando None para o backend interpretar melhor
            "answer": None if answer in (None, "") else answer,
        }

        r = requests.post(f"{backend_url}/interview/next", json=payload, timeout=10)
        r.raise_for_status()  # se der 4xx/5xx, levanta exceção com detalhes
        data = r.json()

        # mostra a resposta do assistente (próxima pergunta) na tela
        st.session_state.messages.append(
            {"role": "assistant", "content": data["message"]}
        )

        # atualiza ponteiro do fluxo
        st.session_state.current_id = data.get("next_id")

        # terminou?
        if data.get("done"):
            st.success(
                "A entrevista inicial acabou de ser concluída. "
                "Se você quiser, você já pode gerar o relatório dessa sessão na barra lateral."
            )

    except requests.HTTPError as e:
        # mostra o corpo que é retornado pelo backend (útil para 422/500)
        body = getattr(e.response, "text", "")
        st.error(f"Erro ao chamar backend: {e}\n{body}")
    except Exception as e:
        st.error(f"Erro ao chamar backend: {e}")


# -----------------------------------------------------------------------------
# UI principal
# Aqui eu estou organizando o chat, o botão de reset e a nossa exibição da ATA.
# -----------------------------------------------------------------------------

# Botão de reset da entrevista
col1, col2 = st.columns(2)
with col1:
    if st.button("Reiniciar entrevista", use_container_width=True):
        """
        Aqui eu aviso o backend para resetar a sessão atual
        e também limpo o estado local do Streamlit.
        """
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
    # sem resposta -> backend retorna a 1ª pergunta do fluxo
    call_next()
    st.session_state.started = True

# Histórico do chat (assistente e usuário)
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


# -----------------------------------------------------------------------------
# ATA / Briefing
# Aqui eu estou mostrando o relatório só se ele já tiver sido gerado.
# -----------------------------------------------------------------------------
if st.session_state.briefing_md:
    st.markdown("---")
    st.markdown("## Relatório da entrevista de levantamento de requisitos")
    st.markdown(st.session_state.briefing_md)

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="Baixar o relatório em formato Markdown (.md)",
            data=st.session_state.briefing_md,
            file_name=f"ata_{st.session_state.session_id}.md",
            mime="text/markdown",
        )

    with col2:
        if st.session_state.briefing_pdf:
            st.download_button(
                label="Baixar o relatório em PDF (.pdf)",
                data=st.session_state.briefing_pdf,
                file_name=f"ata_{st.session_state.session_id}.pdf",
                mime="application/pdf",
            )
        else:
            st.info(
                "O PDF ainda não foi carregado. Porfavor gere o relatório pela barra lateral "
                "para criar o PDF correspondente."
            )