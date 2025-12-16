from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()

# Configura a pasta onde estão os arquivos HTML
templates = Jinja2Templates(directory="templates")

# Submodelo para o campo "mensagem"
class Mensagem(BaseModel):
    evento: str
    timestamp: float

# Modelo principal recebido do iOS
class DadosCliente(BaseModel):
    origem: str
    mensagem: Mensagem

class Agendamento(BaseModel):
    hora: str
    minuto: str

@app.get("/", response_class=HTMLResponse)
def ler_pagina(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/registrar")
def receber_dados(dados: DadosCliente):
    print("Origem:", dados.origem)
    print("Evento:", dados.mensagem.evento)
    print("Timestamp:", dados.mensagem.timestamp)

    # Aqui você pode salvar no banco
    return {
        "recebido": True,
        "origem": dados.origem,
        "evento": dados.mensagem.evento
    }

# Rota que recebe os dados do agendamento via JSON
@app.post("/api/agendar")
def agendar_horario(dados: Agendamento):
    print(f"Recebido agendamento para: {dados.hora}:{dados.minuto}")
    
    # AQUI entra a lógica (ex: salvar no banco de dados ou agendar o job)
    
    return {
        "status": "sucesso", 
        "mensagem": f"Tarefa agendada para as {dados.hora}:{dados.minuto}"
    }