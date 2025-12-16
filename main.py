from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Field, Session, select, create_engine
import os

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---

# Tenta pegar a URL do banco das variáveis de ambiente (no Render), 
# se não achar, usa um arquivo local sqlite (no seu PC)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./banco_local.db")

# Corrige prefixo antigo do Postgres se necessário (coisa do Render/Heroku)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

# --- MODELO DA TABELA (A estrutura dos dados) ---
class Configuracao(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    hora: str
    minuto: str
    origem: str

# Função que cria o banco na inicialização
def criar_banco_e_dados_iniciais():
    SQLModel.metadata.create_all(engine)
    # Garante que existe a linha de ID 1 para a gente editar depois
    with Session(engine) as session:
        config = session.get(Configuracao, 1)
        if not config:
            # Cria o padrão se não existir
            novo_padrao = Configuracao(id=1, hora="09", minuto="00", origem="padrao")
            session.add(novo_padrao)
            session.commit()

# Inicializa o app e o banco
app = FastAPI(on_startup=[criar_banco_e_dados_iniciais])
templates = Jinja2Templates(directory="templates")

# --- ROTAS ---

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Busca a configuração atual para mostrar no HTML (opcional, mas legal)
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/agendar")
def salvar_agendamento(dados: Configuracao):
    with Session(engine) as session:
        # Busca a configuração de ID 1
        config_db = session.get(Configuracao, 1)
        
        # Atualiza os dados
        config_db.hora = dados.hora
        config_db.minuto = dados.minuto
        config_db.origem = "usuario_site"
        
        session.add(config_db)
        session.commit()
        session.refresh(config_db)
        
        print(f"Banco atualizado: {config_db.hora}:{config_db.minuto}")
        
    return {"status": "sucesso", "mensagem": f"Salvo no Banco: {dados.hora}:{dados.minuto}"}

@app.get("/api/consultar-agendamento")
def consultar_agendamento():
    with Session(engine) as session:
        # Busca a linha 1
        config = session.get(Configuracao, 1)
        return config