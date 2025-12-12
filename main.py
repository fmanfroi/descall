from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Modelo de dados que o cliente vai enviar
class DadosCliente(BaseModel):
    origem: str
    mensagem: str
    status: str

@app.get("/")
def home():
    return {"status": "Backend online"}

@app.post("/api/registro")
def receber_dados(dados: DadosCliente):
    print(f"Recebido de {dados.origem}: {dados.mensagem}")
    # Aqui você salvaria no banco de dados
    return {"recebido": True, "mensagem": "Dados processados com sucesso"}