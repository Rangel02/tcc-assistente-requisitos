from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, List
import json

app = FastAPI(title="Assistente de Requisitos API", version="0.2.0")

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
    # garante sessão
    SESSIONS.setdefault(req.session_id, [])

    # se veio resposta do nó anterior, salva
    if req.answer is not None and req.current_id in QUESTIONS:
        qnode = QUESTIONS[req.current_id]
        SESSIONS[req.session_id].append({
            "id": req.current_id,
            "question": qnode["text"],
            "answer": req.answer,
        })

    # primeira pergunta
    if not req.current_id:
        first = QUESTIONS.get("start")
        return NextResponse(message=first["text"], next_id="start", done=False)

    # nó atual
    curr = QUESTIONS.get(req.current_id)
    if not curr:
        return NextResponse(message="Passo inválido. Reinicie a entrevista.", next_id=None, done=True)

    # decide próximo: branch (se existir) ou fallback 'next'
    nxt_id = choose_next(curr, req.answer)
    if not nxt_id:
        return NextResponse(message="Entrevista concluída. Obrigado!", next_id=None, done=True)

    nxt = QUESTIONS.get(nxt_id)
    if not nxt:
        return NextResponse(message="Fluxo mal configurado (próximo passo não encontrado).", next_id=None, done=True)

    return NextResponse(message=nxt["text"], next_id=nxt_id, done=(nxt_id == "fim"))

def build_briefing_md(session_id: str) -> str:
    qa = SESSIONS.get(session_id, [])
    lines = [
        "# Briefing Inicial",
        "",
        f"**Sessão:** `{session_id}`",
        "",
        "## Resumo da Entrevista",
    ]
    if not qa:
        lines += ["_Nenhuma resposta registrada nesta sessão._"]
    else:
        for i, item in enumerate(qa, 1):
            lines += [
                f"### {i}. {item['question']}",
                f"- **Resposta:** {item['answer']}",
                ""
            ]
    lines += [
        "---",
        "_Gerado automaticamente pelo Assistente de Requisitos (MVP)_"
    ]
    return "\n".join(lines)

@app.post("/briefing", response_model=BriefingResponse)
def make_briefing(req: BriefingRequest):
    md = build_briefing_md(req.session_id)
    return BriefingResponse(markdown=md)

@app.post("/reset")
def reset_session(req: BriefingRequest):
    SESSIONS.pop(req.session_id, None)
    return {"ok": True}
