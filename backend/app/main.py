from pathlib import Path
from typing import Dict, List
from datetime import datetime
from io import BytesIO
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .db import create_db_and_tables
from .repository import upsert_session, list_sessions, get_session_by_id


# -----------------------------------------------------------------------------
# Inicialização da API
# Aqui eu to subindo a aplicação FastAPI e garanto que o banco esteja criado.
# -----------------------------------------------------------------------------
app = FastAPI(title="Assistente de Requisitos API", version="0.2.0")


@app.on_event("startup")
def on_startup():
    """
    Quando a API sobe, eu garanto que o banco e as tabelas existem.
    Isso fica escondido dentro do create_db_and_tables().
    """
    create_db_and_tables()


# CORS liberado para desenvolvimento (vai facilitar a testar front/back em portas diferentes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Carregando a nossa árvore de perguntas a partir do questions.json
# -----------------------------------------------------------------------------
DATA_PATH = Path(__file__).parent / "questions.json"
with DATA_PATH.open("r", encoding="utf-8") as f:
    QUESTIONS_LIST = json.load(f)
    # aqui eu transformo a lista numa dict para acesso rápido por id
    QUESTIONS = {node["id"]: node for node in QUESTIONS_LIST}


# -----------------------------------------------------------------------------
# Memória por sessão (MVP)
# Aqui eu simplesmente to guardando o histórico da entrevista em memória, além do banco.
# SESSIONS[session_id] = [ {id, question, answer}, ... ]
# -----------------------------------------------------------------------------
SESSIONS: Dict[str, List[Dict]] = {}


# -----------------------------------------------------------------------------
# Models (entrada e saída das rotas principais)
# -----------------------------------------------------------------------------
class NextRequest(BaseModel):
    """
    Corpo esperado na chamada de /interview/next.
    - session_id: id lógico da sessão da entrevista;
    - current_id: id da pergunta atual (None para a primeira chamada);
    - answer: resposta do usuário para a pergunta anterior.
    """
    session_id: str
    current_id: str | None = None
    answer: str | None = None


class NextResponse(BaseModel):
    """
    Resposta da rota /interview/next.
    - message: texto que será exibido no front (normalmente a próxima pergunta);
    - next_id: id do próximo nó no fluxo;
    - done: indica se a entrevista chegou ao fim.
    """
    message: str
    next_id: str | None
    done: bool


class BriefingRequest(BaseModel):
    """
    Corpo usado em /briefing e /reset:
    aqui eu só preciso do session_id da entrevista.
    """
    session_id: str


class BriefingResponse(BaseModel):
    """
    Resposta da rota /briefing: devolve o markdown da ATA.
    """
    markdown: str


# -----------------------------------------------------------------------------
# Rotas básicas
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    """
    Endpoint simples para o nosso front testar se a API está de pé.
    """
    return {"status": "ok"}


# -----------------------------------------------------------------------------
# Fluxo principal da entrevista
# -----------------------------------------------------------------------------
@app.post("/interview/next", response_model=NextResponse)
def interview_next(req: NextRequest):
    """
    Aqui eu controlo o fluxo da entrevista.

    A minha ideia é:
    - Garantir que a sessão existe em memória (SESSIONS);
    - Se tiver vindo uma resposta (answer), eu só salvo essa resposta atrelada ao nó anterior;
    - Se for a primeira chamada (current_id = None), eu só começo no nó 'start';
    - Caso contrário, eu uso o current_id no caso para decidir o próximo id no questions.json;
    - No fim, eu salvo um snapshot da sessão no banco (SQLite via SQLModel).
    """

    # garante que a sessão está em memória (histórico simples)
    SESSIONS.setdefault(req.session_id, [])

    # --- normalização: tratar "null"/"none"/"" como None ---
    cid = req.current_id
    ans = req.answer
    if isinstance(cid, str) and cid.strip().lower() in ("", "null", "none"):
        cid = None
    if isinstance(ans, str) and ans.strip().lower() in ("", "null", "none"):
        ans = None

    # se veio a resposta do nó anterior, salva no histórico em memória
    if ans is not None and cid in QUESTIONS:
        qnode = QUESTIONS[cid]
        SESSIONS[req.session_id].append(
            {
                "id": cid,
                "question": qnode["text"],
                "answer": ans,
            }
        )

    # primeira pergunta: se não tem current_id, eu começo pelo "start"
    if not cid:
        first = QUESTIONS.get("start")
        return NextResponse(message=first["text"], next_id="start", done=False)

    # nó atual
    curr = QUESTIONS.get(cid)
    if not curr:
        # se cair aqui é porque o fluxo ficou inconsistente
        return NextResponse(
            message="Passo inválido no fluxo de perguntas. Reinicie a entrevista.",
            next_id=None,
            done=True,
        )

    # -------- decidir o PRÓXIMO ID --------
    next_id = None
    ans_norm = (ans or "").strip().lower()

    # 1) Branch por resposta (se existir):
    #    aqui eu aceito 'branch' ou 'branches' no questions.json
    branch = curr.get("branch") or curr.get("branches")
    if isinstance(branch, dict) and ans_norm:
        # tenta bater exato
        next_id = branch.get(ans_norm) or branch.get("*") or branch.get("default")

    # 2) Fallback 'next'
    if not next_id:
        next_id = curr.get("next")

    # 3) Se ainda não houver próximo, eu forço para "fim"
    if not next_id:
        next_id = "fim"

    # Carrega o nó seguinte (se não for o fim)
    nxt = QUESTIONS.get(next_id) if next_id != "fim" else None
    if next_id != "fim" and not nxt:
        return NextResponse(
            message="Fluxo mal configurado (próximo passo não encontrado).",
            next_id=None,
            done=True,
        )

    # calcule o done e a mensagem final
    done = next_id == "fim"
    message = nxt["text"] if not done else "Entrevista finalizada!"

    # ====== PERSISTÊNCIA ======
    # Aqui eu monto um snapshot da sessão e salvo no banco.
    # Se der erro de banco, eu não quebro o fluxo da entrevista.
    try:
        snapshot = {
            "current_id": next_id,
            "done": bool(done),
            # agora realmente salvando o histórico completo no banco
            "history": SESSIONS.get(req.session_id),
        }
        upsert_session(session_id=req.session_id, answers_json=snapshot)
    except Exception:
        # não vamos matar o fluxo se der erro de persistência
        pass
    # ====== FIM PERSISTÊNCIA ======

    return NextResponse(message=message, next_id=next_id, done=done)


# -----------------------------------------------------------------------------
# Geração de ATA em Markdown
# -----------------------------------------------------------------------------
def build_briefing_md(session_id: str) -> str:
    """
    Aqui a gente gera a ATA da entrevista em formato Markdown, usando as respostas
    que foram guardadas durante a conversa.

    Primeiro eu vou tentar pegar o histórico salvo no banco (answers_json['history'])
    e, se não achar nada lá, eu caio para o histórico em memória (SESSIONS).
    """

    # tenta buscar as respostas da sessão direto no nosso banco
    db_sess = get_session_by_id(session_id)
    qa = None

    if db_sess and isinstance(db_sess.answers_json, dict):
        qa = db_sess.answers_json.get("history")

    # se não tiver nada no banco, agora usa o que ficou em memória
    if not qa:
        qa = SESSIONS.get(session_id, [])

    lines: list[str] = [
        "# ATA da Entrevista de Levantamento de Requisitos",
        "",
        f"Sessão registrada: `{session_id}`",
        "",
        "## 1. Informações gerais",
        "Aqui eu junto, de forma organizada, as respostas que foram dadas na entrevista inicial.",
        "",
        "## 2. Perguntas e respostas",
    ]

    if not qa:
        lines.append("_Nenhuma resposta foi registrada para esta sessão._")
    else:
        for i, item in enumerate(qa, 1):
            question = item.get("question", "").strip()
            answer = item.get("answer", "").strip()

            lines += [
                f"### {i}. {question}",
                f"- Resposta registrada: {answer}",
                "",
            ]

    lines += [
        "## 3. Observações finais",
        "Esta ATA foi gerada automaticamente a partir dos dados coletados pelo protótipo de "
        "assistente virtual para apoio à Engenharia de Requisitos, desenvolvido como Trabalho "
        "de Conclusão de Curso.",
        "",
        "---",
        "Relatório montado a partir da entrevista realizada no sistema de apoio ao levantamento de requisitos.",
    ]

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Helpers para PDF (limpeza de texto e montagem do PDF com ReportLab)
# -----------------------------------------------------------------------------
def _clean_for_pdf(text: str) -> str:
    """
    Remove marcações de markdown e caracteres que estão fora da faixa básica (como emojis),
    mantendo acentos e cedilha.
    """
    text = text.replace("**", "").replace("_", "").replace("`", "")
    # mantém caracteres até 255 (acentos ok), remove emojis e cia
    return "".join(ch for ch in text if 32 <= ord(ch) <= 255)


def build_briefing_pdf_bytes(session_id: str) -> bytes:
    """
    Aqui eu gero o PDF da ATA a partir do texto em Markdown.

    A ideia é simples:
    - primeiro eu chamo a função build_briefing_md(session_id) para montar o texto base;
    - depois eu vou jogando esse conteúdo linha a linha no PDF, ajustando fonte e quebras;
    - também desenho um cabeçalho e um rodapé em cada página, com o contexto do TCC.
    """

    md = build_briefing_md(session_id)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # aqui estão as margens que eu vou usar na página
    left_margin = 50
    top_margin = 80
    bottom_margin = 60

    year = datetime.now().year

    # aqui eu defino o texto do cabeçalho (titulo e contexto do curso)
    header_title = _clean_for_pdf("Protótipo de Assistente Virtual para Engenharia de Requisitos")
    header_sub = _clean_for_pdf(f"PUC Minas – Ciência da Computação – 8º período – {year}")

    def draw_header_footer():
        """
        Cabeçalho e rodapé que vão aparecer em todas as páginas.
        Aqui eu desenho:
        - o título do protótipo;
        - a linha com curso/período/ano;
        - e por fim o número da página lá embaixo.
        """
        # cabeçalho
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left_margin, height - 40, header_title)

        c.setFont("Helvetica", 9)
        c.drawString(left_margin, height - 55, header_sub)

        # linha abaixo do cabeçalho
        c.setLineWidth(0.5)
        c.line(left_margin, height - 60, width - left_margin, height - 60)

        # rodapé
        page_num = c.getPageNumber()
        footer_text = _clean_for_pdf(f"Relatório de entrevista de requisitos – página {page_num}")
        c.setFont("Helvetica", 8)
        c.drawRightString(width - left_margin, bottom_margin - 25, footer_text)

        # linha acima do rodapé
        c.setLineWidth(0.5)
        c.line(left_margin, bottom_margin - 20, width - left_margin, bottom_margin - 20)

    # posição inicial do texto (já descontando o cabeçalho)
    y = height - top_margin

    def new_page():
        """
        Quando o conteúdo chega perto do fim da página, eu chamo essa função, no caso
        para abrir uma nova página, redesenhar cabeçalho/rodapé e resetar o y.
        """
        nonlocal y
        c.showPage()
        draw_header_footer()
        y = height - top_margin

    def ensure_space(line_height: float):
        """
        Antes de escrever uma linha, eu confiro se ainda tem espaço.
        Se não tiver, eu abro uma nova página.
        """
        nonlocal y
        if y - line_height < bottom_margin:
            new_page()

    def draw_wrapped(text: str, font_name: str, font_size: int, extra_space: float = 0):
        """
        Aqui eu escrevo um parágrafo com quebra automática de linha.

        - text: texto que eu quero escrever;
        - font_name / font_size: controle básico de estilo;
        - extra_space: espaço extra que eu deixo depois do parágrafo.
        """
        nonlocal y
        text = _clean_for_pdf(text)
        if not text:
            return

        c.setFont(font_name, font_size)
        max_width = width - 2 * left_margin
        words = text.split(" ")
        line = ""
        line_height = font_size * 1.3

        for word in words:
            test_line = (line + " " + word).strip()
            if c.stringWidth(test_line, font_name, font_size) <= max_width:
                line = test_line
            else:
                ensure_space(line_height)
                c.drawString(left_margin, y, line)
                y -= line_height
                line = word

        if line:
            ensure_space(line_height)
            c.drawString(left_margin, y, line)
            y -= line_height + extra_space

    # primeira página já começa com o cabeçalho/rodapé
    draw_header_footer()

    # agora eu vou varrer o markdown linha a linha, interpretando alguns padrões
    for raw_line in md.splitlines():
        line = raw_line.rstrip()

        # linha em branco -> só desce um pouco
        if not line.strip():
            y -= 6
            continue

        # título principal "# ..."
        if line.startswith("# "):
            title = _clean_for_pdf(line[2:].strip())
            font_name = "Helvetica-Bold"
            font_size = 18
            c.setFont(font_name, font_size)
            text_width = c.stringWidth(title, font_name, font_size)
            ensure_space(font_size * 1.6)
            c.drawString((width - text_width) / 2, y, title)
            y -= font_size * 1.6
            continue

        # subtítulo "## ..."
        if line.startswith("## "):
            subtitle = line[3:].strip()
            draw_wrapped(subtitle, "Helvetica-Bold", 14, extra_space=8)
            continue

        # sub-subtítulo "### ..."
        if line.startswith("### "):
            subtitle = line[4:].strip()
            draw_wrapped(subtitle, "Helvetica-Bold", 12, extra_space=4)
            continue

        # lista "- ..."
        if line.lstrip().startswith("- "):
            item = line.lstrip()[2:].strip()
            item = "• " + item
            draw_wrapped(item, "Helvetica", 11, extra_space=4)
            continue

        # texto normal (linha que não bate com nenhum padrão acima)
        plain = _clean_for_pdf(line)
        draw_wrapped(plain, "Helvetica", 11)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# Rotas de Briefing / ATA
# -----------------------------------------------------------------------------
@app.post("/briefing", response_model=BriefingResponse)
def make_briefing(req: BriefingRequest):
    """
    Aqui eu peço para montar a ATA em Markdown para uma sessão específica
    e também aproveito para salvar esse texto no banco.
    """
    md = build_briefing_md(req.session_id)

    # salva a ATA no banco, sem sobrescrever answers_json
    try:
        upsert_session(session_id=req.session_id, answers_json=None, briefing_md=md)
    except Exception:
        # se der erro de banco, ainda assim devolvo o MD pro front
        pass

    return BriefingResponse(markdown=md)


@app.get("/briefing/pdf/{session_id}")
def make_briefing_pdf(session_id: str):
    """
    Retorna a ATA da sessão em formato PDF (application/pdf).
    Aqui eu só garanto que a sessão existe e depois gero o PDF em memória.
    """
    # só para garantir que a sessão existe:
    sess = get_session_by_id(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    pdf_bytes = build_briefing_pdf_bytes(session_id)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ata_{session_id}.pdf"'
        },
    )


# -----------------------------------------------------------------------------
# Reset da sessão (lado do backend)
# Aqui eu só limpo o histórico em memória. O que foi para o banco continua salvo.
# -----------------------------------------------------------------------------
@app.post("/reset")
def reset_session(req: BriefingRequest):
    """
    Limpa o histórico de uma sessão em memória (SESSIONS).
    O front também gera um novo session_id quando reseta.
    """
    SESSIONS.pop(req.session_id, None)
    return {"ok": True}
