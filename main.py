from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Field, Session, select, create_engine
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# --- BANCO DE DADOS ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./banco_local.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


# --- MODELO DA TABELA (Atualizado para suportar status/msgsucesso) ---
class Configuracao(SQLModel, table=True):
    # Chave primária composta por data, hora e minuto
    data_para_execucao: str = Field(primary_key=True)
    hora: str = Field(primary_key=True)
    minuto: str = Field(primary_key=True)

    # Metadados de Controle
    origem: str
    data_solicitacao: datetime = Field(default_factory=datetime.now)
    executou_sucesso: bool = False

    # Novos campos para fluxo de status
    status: str = Field(default="criado")
    msgsucesso: Optional[str] = None


# --- MODELOS PARA A API (INPUT) ---
class DadosAgendamento(BaseModel):
    hora: str
    minuto: str
    data_execucao: str  # Vem do HTML
    status: Optional[str] = None
    msgsucesso: Optional[str] = None


class ConfirmacaoExecucao(BaseModel):
    status: Optional[str] = None
    msgsucesso: Optional[str] = None
    sucesso: Optional[bool] = None


class DadosRelatorio(BaseModel):
    sucesso: bool
    mensagem: str


# Inicialização
def criar_banco():
    SQLModel.metadata.create_all(engine)


app = FastAPI(on_startup=[criar_banco])
templates = Jinja2Templates(directory="templates")


# --- ROTAS ---


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# 1. API para AGENDAR (Cria/Atualiza a tarefa)
@app.post("/api/agendar")
def agendar(dados: DadosAgendamento):
    with Session(engine) as session:
        # Busca por registro com a mesma data/hora/minuto
        stmt = select(Configuracao).where(
            (Configuracao.data_para_execucao == dados.data_execucao)
            & (Configuracao.hora == dados.hora)
            & (Configuracao.minuto == dados.minuto)
        )
        tarefa = session.exec(stmt).first()

        if not tarefa:
            tarefa = Configuracao(
                data_para_execucao=dados.data_execucao,
                hora=dados.hora,
                minuto=dados.minuto,
                origem="web",
            )

        # Atualiza os campos
        tarefa.hora = dados.hora
        tarefa.minuto = dados.minuto
        tarefa.data_para_execucao = dados.data_execucao
        tarefa.origem = tarefa.origem or "web_user"
        tarefa.data_solicitacao = datetime.now()
        tarefa.executou_sucesso = False

        # Se quem chamou enviou status/msgsucesso, respeita; senão marca criado
        tarefa.status = dados.status or "criado"
        tarefa.msgsucesso = dados.msgsucesso

        session.add(tarefa)
        session.commit()
        # Recarrega o objeto da sessão para garantir valores padrão/atualizados
        try:
            session.refresh(tarefa)
        except Exception:
            # fallback: re-query the record
            tarefa = session.exec(
                select(Configuracao).where(
                    (Configuracao.data_para_execucao == dados.data_execucao)
                    & (Configuracao.hora == dados.hora)
                    & (Configuracao.minuto == dados.minuto)
                )
            ).first()

        # Retorna representação serializável do registro
        return tarefa.dict() if tarefa is not None else {}


# 2. API para CONSULTAR (O Ubuntu chama essa)
@app.get("/api/consultar")
def consultar():
    with Session(engine) as session:
        # Retorna todos os registros ordenados por `data_solicitacao DESC` (útil para depuração)
        stmt = select(Configuracao).order_by(Configuracao.data_solicitacao.desc())
        tarefas = session.exec(stmt).all()
        if not tarefas:
            return {}

        # Marca o registro mais recente como consultado para compatibilidade
        mais_recente = tarefas[0]
        # (removed debug logs)
        mais_recente.status = "consultado"
        session.add(mais_recente)
        session.commit()

        # Retorna apenas a tarefa mais recente (convertida para tipos primitivos)
        def to_primitive(t):
            return {
                "data_para_execucao": t.data_para_execucao,
                "hora": t.hora,
                "minuto": t.minuto,
                "origem": t.origem,
                "data_solicitacao": t.data_solicitacao.isoformat() if hasattr(t.data_solicitacao, "isoformat") else str(t.data_solicitacao),
                "executou_sucesso": bool(t.executou_sucesso),
                "status": t.status,
                "msgsucesso": t.msgsucesso,
            }

        return to_primitive(mais_recente)


@app.get("/api/listar-ultimas")
def listar_ultimas(limit: int = 20):
    """Retorna as últimas `limit` tarefas ordenadas por `data_solicitacao DESC`."""
    with Session(engine) as session:
        stmt = select(Configuracao).order_by(Configuracao.data_solicitacao.desc())
        tarefas = session.exec(stmt).all()
        if not tarefas:
            return []

        def to_primitive(t):
            return {
                "data_para_execucao": t.data_para_execucao,
                "hora": t.hora,
                "minuto": t.minuto,
                "origem": t.origem,
                "data_solicitacao": t.data_solicitacao.isoformat() if hasattr(t.data_solicitacao, "isoformat") else str(t.data_solicitacao),
                "executou_sucesso": bool(t.executou_sucesso),
                "status": t.status,
                "msgsucesso": t.msgsucesso,
            }

        return [to_primitive(t) for t in tarefas][:limit]


# 3. API para CONFIRMAR EXECUÇÃO (Atualiza status/msgsucesso)
@app.post("/api/confirmar-execucao")
def confirmar(confirm: ConfirmacaoExecucao):
    with Session(engine) as session:
        # Atualiza o registro mais recente (mesma abordagem de consultar)
        # Seleciona pelo registro mais recentemente solicitado (consistente com /api/consultar)
        stmt = select(Configuracao).order_by(Configuracao.data_solicitacao.desc())
        tarefa = session.exec(stmt).first()
        if tarefa:
            # Atualiza status/msg
            if confirm.status:
                tarefa.status = confirm.status
            if confirm.msgsucesso is not None:
                tarefa.msgsucesso = confirm.msgsucesso
            # Ajusta executou_sucesso quando aplicável
            if confirm.sucesso is not None:
                tarefa.executou_sucesso = bool(confirm.sucesso)
            else:
                if confirm.status == "sucesso":
                    tarefa.executou_sucesso = True
                elif confirm.status == "falha":
                    tarefa.executou_sucesso = False

            session.add(tarefa)
            session.commit()
            print(f"Relatório recebido: status={tarefa.status} msgsucesso={tarefa.msgsucesso}")
            return {"status": "recebido", "tarefa": tarefa.dict()}
    return {"status": "recebido"}


@app.get("/health-check")
async def health_check():
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "ok", "message": f"[{agora}] Resposta do health-check"}
