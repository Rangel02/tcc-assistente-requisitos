from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, List
import json
from fastapi import Query, HTTPException
from .db import create_db_and_tables
from .repository import upsert_session, list_sessions, get_session_by_id


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
            # "history": SESSIONS.get(req.session_id),  # opcional: salve também
        }
        upsert_session(session_id=req.session_id, answers_json=snapshot)
    except Exception:
        pass
    # ====== FIM PERSISTÊNCIA ======

    return NextResponse(message=message, next_id=next_id, done=done)




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
