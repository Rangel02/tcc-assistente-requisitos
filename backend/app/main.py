from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, List
import json
from fastapi import Query, HTTPException
from .db import create_db_and_tables
from .repository import upsert_session, list_sessions, get_session_by_id
from fastapi.responses import StreamingResponse
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas



app = FastAPI(title="Assistente de Requisitos API", version="0.2.0")
@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# CORS liberado para desenvolvimento
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Carregar árvore de perguntas ----
DATA_PATH = Path(__file__).parent / "questions.json"
with DATA_PATH.open("r", encoding="utf-8") as f:
    QUESTIONS_LIST = json.load(f)
    QUESTIONS = {node["id"]: node for node in QUESTIONS_LIST}

# ---- Memória por sessão (MVP) ----
# SESSIONS[session_id] = [ {id, question, answer}, ... ]
SESSIONS: Dict[str, List[Dict]] = {}

# ---- Models ----
class NextRequest(BaseModel):
    session_id: str
    current_id: str | None = None
    answer: str | None = None

class NextResponse(BaseModel):
    message: str
    next_id: str | None
    done: bool

class BriefingRequest(BaseModel):
    session_id: str

class BriefingResponse(BaseModel):
    markdown: str

# ---- Helpers p/ ramificações ----
def _norm(txt: str | None) -> str:
    return (txt or "").strip().lower()

YES = {"sim", "s", "yes", "y", "true", "verdadeiro"}
NO  = {"nao", "não", "n", "no", "false", "falso"}

def choose_next(curr_node: dict, answer: str | None) -> str | None:
    """
    Decide o próximo id:
    - Se houver 'branches' e a resposta bater (sim/nao ou chave exata), segue o ramo.
    - Caso contrário, usa 'next' (fallback).
    """
    branches = curr_node.get("branches")
    if branches and answer is not None:
        a = _norm(answer)
        # chave exata?
        if a in branches:
            return branches[a]
        # sinônimos de sim/nao
        if a in YES and "sim" in branches:
            return branches["sim"]
        if a in NO and ("nao" in branches or "não" in branches):
            return branches.get("nao") or branches.get("não")
        # não reconheceu: fallback
        return curr_node.get("next")

    # sem branches: segue next normal
    return curr_node.get("next")

# ---- Rotas ----
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/interview/next", response_model=NextResponse)
def interview_next(req: NextRequest):
    # garante sessão em memória (histórico simples)
    SESSIONS.setdefault(req.session_id, [])

    # --- normalização: tratar "null"/"none"/"" como None ---
    cid = req.current_id
    ans = req.answer
    if isinstance(cid, str) and cid.strip().lower() in ("", "null", "none"):
        cid = None
    if isinstance(ans, str) and ans.strip().lower() in ("", "null", "none"):
        ans = None

    # se veio resposta do nó anterior, salva no histórico em memória
    if ans is not None and cid in QUESTIONS:
        qnode = QUESTIONS[cid]
        SESSIONS[req.session_id].append({
            "id": cid,
            "question": qnode["text"],
            "answer": ans,
        })

    # primeira pergunta: se não há current_id, comece por "start"
    if not cid:
        first = QUESTIONS.get("start")
        return NextResponse(message=first["text"], next_id="start", done=False)

    # nó atual
    curr = QUESTIONS.get(cid)
    if not curr:
        return NextResponse(message="Passo inválido. Reinicie a entrevista.", next_id=None, done=True)

    # -------- decidir o PRÓXIMO ID --------
    next_id = None
    ans_norm = (ans or "").strip().lower()

    # 1) Branch por resposta (se existir)
    branch = curr.get("branch") or curr.get("branches")
    if isinstance(branch, dict) and ans_norm:
        next_id = branch.get(ans_norm) or branch.get("*") or branch.get("default")

    # 2) Fallback 'next'
    if not next_id:
        next_id = curr.get("next")

    # 3) Se ainda não houver próximo, encerra
    if not next_id:
        next_id = "fim"

    # Carrega o nó seguinte (se não for o fim)
    nxt = QUESTIONS.get(next_id) if next_id != "fim" else None
    if next_id != "fim" and not nxt:
        return NextResponse(message="Fluxo mal configurado (próximo passo não encontrado).", next_id=None, done=True)

    # calcule o done e a mensagem final
    done = (next_id == "fim")
    message = nxt["text"] if not done else "Entrevista finalizada!"

    # ====== PERSISTÊNCIA ======
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




from .repository import upsert_session, list_sessions, get_session_by_id  # já está importado

def build_briefing_md(session_id: str) -> str:
    # tenta pegar histórico do banco
    db_sess = get_session_by_id(session_id)
    qa = None

    if db_sess and isinstance(db_sess.answers_json, dict):
        qa = db_sess.answers_json.get("history")

    # fallback para memória
    if not qa:
        qa = SESSIONS.get(session_id, [])

    lines = [
        "# 📝 ATA da Entrevista Inicial",
        "",
        f"Sessão: `{session_id}`",
        "",
        "## 📋 Resumo da Entrevista",
    ]

    if not qa:
        lines.append("_Nenhuma resposta registrada nesta sessão._")
    else:
        for i, item in enumerate(qa, 1):
            question = item.get("question", "")
            answer = item.get("answer", "")
            lines += [
                f"### {i}. {question}",
                f"- Resposta: {answer}",
                ""
            ]

    lines += [
        "---",
        "_Gerado automaticamente pelo Assistente de Requisitos (MVP)_",
    ]
    return "\n".join(lines)


def _clean_for_pdf(text: str) -> str:
    """
    Remove marcações de markdown e caracteres fora da faixa básica (como emojis),
    mantendo acentos e cedilha.
    """
    text = text.replace("**", "").replace("_", "").replace("`", "")
    # mantém caracteres até 255 (acentos ok), remove emojis e cia
    return "".join(ch for ch in text if 32 <= ord(ch) <= 255)


def build_briefing_pdf_bytes(session_id: str) -> bytes:
    """
    Gera um PDF formatado a partir da ATA em Markdown.
    - Cabeçalho com infos do TCC (curso, período, ano)
    - Título centralizado e grande
    - Seções em negrito
    - Subseções para cada pergunta
    - Bullets para respostas
    - Rodapé com número da página
    """
    md = build_briefing_md(session_id)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    left_margin = 50
    top_margin = 80
    bottom_margin = 60

    year = datetime.now().year

    # textos fixos do seu TCC
    header_title = _clean_for_pdf("Assistente Virtual para Engenharia de Requisitos – MVP")
    header_sub = _clean_for_pdf(f"PUC Minas • Ciência da Computação • 8º período • {year}")

    def draw_header_footer():
        """
        Desenha cabeçalho e rodapé na página atual.
        """
        # Cabeçalho
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left_margin, height - 40, header_title)

        c.setFont("Helvetica", 9)
        c.drawString(left_margin, height - 55, header_sub)

        # Linha abaixo do cabeçalho
        c.setLineWidth(0.5)
        c.line(left_margin, height - 60, width - left_margin, height - 60)

        # Rodapé
        page_num = c.getPageNumber()
        footer_text = _clean_for_pdf(f"Relatório de Entrevista – Página {page_num}")
        c.setFont("Helvetica", 8)
        c.drawRightString(width - left_margin, bottom_margin - 25, footer_text)

        # Linha acima do rodapé
        c.setLineWidth(0.5)
        c.line(left_margin, bottom_margin - 20, width - left_margin, bottom_margin - 20)

    # posição inicial de texto (abaixo do cabeçalho)
    y = height - top_margin

    def new_page():
        nonlocal y
        c.showPage()
        draw_header_footer()
        y = height - top_margin

    def ensure_space(line_height: float):
        nonlocal y
        if y - line_height < bottom_margin:
            new_page()

    def draw_wrapped(text: str, font_name: str, font_size: int, extra_space: float = 0):
        """
        Desenha texto com quebra automática de linha.
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

    # desenha cabeçalho/rodapé da primeira página
    draw_header_footer()

    # ===== varrendo o markdown =====
    for raw_line in md.splitlines():
        line = raw_line.rstrip()

        # linha em branco -> só um pequeno espaço
        if not line.strip():
            y -= 6
            continue

        # TÍTULO "# ..."
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

        # SUBTÍTULO "## ..."
        if line.startswith("## "):
            subtitle = line[3:].strip()
            draw_wrapped(subtitle, "Helvetica-Bold", 14, extra_space=8)
            continue

        # SUB-SUBTÍTULO "### ..."
        if line.startswith("### "):
            subtitle = line[4:].strip()
            draw_wrapped(subtitle, "Helvetica-Bold", 12, extra_space=4)
            continue

        # LISTA "- ..."
        if line.lstrip().startswith("- "):
            item = line.lstrip()[2:].strip()
            item = "• " + item
            draw_wrapped(item, "Helvetica", 11, extra_space=4)
            continue

        # TEXTO NORMAL
        plain = _clean_for_pdf(line)
        draw_wrapped(plain, "Helvetica", 11)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


@app.post("/briefing", response_model=BriefingResponse)
def make_briefing(req: BriefingRequest):
    md = build_briefing_md(req.session_id)

    # salva a ATA no banco, sem sobrescrever answers_json
    try:
        upsert_session(session_id=req.session_id, answers_json=None, briefing_md=md)
    except Exception:
        # se der erro de banco, ainda assim devolvemos o MD pro front
        pass

    return BriefingResponse(markdown=md)


@app.get("/briefing/pdf/{session_id}")
def make_briefing_pdf(session_id: str):
    """
    Retorna a ATA da sessão em formato PDF (application/pdf).
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


@app.post("/reset")
def reset_session(req: BriefingRequest):
    SESSIONS.pop(req.session_id, None)
    return {"ok": True}
