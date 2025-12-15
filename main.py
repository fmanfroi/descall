from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Submodelo para o campo "mensagem"
class Mensagem(BaseModel):
    evento: str
    timestamp: float

# Modelo principal recebido do iOS
class DadosCliente(BaseModel):
    origem: str
    mensagem: Mensagem

@app.get("/")
def healthz():
    return {"status": "Backend online"}

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
