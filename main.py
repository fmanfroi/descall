from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Field, Session, select, create_engine
from pydantic import BaseModel
from datetime import datetime
import os
from dotenv import load_dotenv

# --- BANCO DE DADOS ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./banco_local.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

# --- MODELO DA TABELA (Atualizado) ---
class Configuracao(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    
    # Dados do Agendamento
    hora: str
    minuto: str
    data_para_execucao: str  # Data que o usuário quer que rode (YYYY-MM-DD)
    
    # Metadados de Controle
    origem: str
    data_solicitacao: datetime = Field(default_factory=datetime.now) # Preenchido auto
    executou_sucesso: bool = False # Começa falso, vira True quando o Ubuntu avisar

# --- MODELOS PARA A API (INPUT) ---
class DadosAgendamento(BaseModel):
    hora: str
    minuto: str
    data_execucao: str # Vem do HTML

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
        # Tenta pegar a config existente ou cria nova
        tarefa = session.get(Configuracao, 1)
        if not tarefa:
            tarefa = Configuracao(id=1, hora="", minuto="", data_para_execucao="", origem="")

        # Atualiza os campos
        tarefa.hora = dados.hora
        tarefa.minuto = dados.minuto
        tarefa.data_para_execucao = dados.data_execucao
        tarefa.origem = "web_user"
        tarefa.data_solicitacao = datetime.now() # Hora exata do clique
        tarefa.executou_sucesso = False # Reseta o status para pendente
        
        session.add(tarefa)
        session.commit()
        return {"status": "Agendado", "data": dados.data_execucao, "hora": f"{dados.hora}:{dados.minuto}"}

# 2. API para CONSULTAR (O Ubuntu chama essa)
@app.get("/api/consultar")
def consultar():
    with Session(engine) as session:
        tarefa = session.get(Configuracao, 1)
        return tarefa

# 3. API para CONFIRMAR EXECUÇÃO (O Ubuntu chama essa ao terminar)
@app.post("/api/confirmar-execucao")
def confirmar(relatorio: DadosRelatorio):
    with Session(engine) as session:
        tarefa = session.get(Configuracao, 1)
        if tarefa:
            tarefa.executou_sucesso = relatorio.sucesso
            session.add(tarefa)
            session.commit()
            print(f"Relatório recebido do Ubuntu: {relatorio.mensagem}")
    return {"status": "recebido"}

@app.get("/health-check")
async def health_check():
    return {"status": "ok", "message": "Estou acordado!"}