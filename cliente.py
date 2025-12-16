import requests
import datetime

# URL do seu backend no Render
URL_BACKEND = "https://descall.onrender.com/api/registro"

def rodar_tarefa():
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    payload = {
        "origem": "Ubuntu_PC_Casa",
        "mensagem": f"Rodando tarefa agendada em {agora}",
        "status": "OK"
    }

    try:
        response = requests.post(URL_BACKEND, json=payload)
        if response.status_code == 200:
            print(f"Sucesso: {response.json()}")
        else:
            print(f"Erro no servidor: {response.status_code}")
    except Exception as e:
        print(f"Erro de conexão: {e}")

if __name__ == "__main__":
    rodar_tarefa()