import requests
import datetime
import subprocess
import sys

URL = "https://descall.onrender.com"
#SCRIPT_ALVO = "/home/fernando-manfroi/bater-ponto.sh"
SCRIPT_ALVO = "/home/fernando-manfroi/ponto/cron.sh"


def main():
    # 1. Consultar Agendamento
    try:
        resp = requests.get(f"{URL}/api/consultar")
        if resp.status_code != 200:
            print("Erro ao conectar no servidor")
            return

        dados = resp.json()
        if not dados:
            print("Nenhuma configuração encontrada.")
            return

        # Verifica se é para hoje (Exemplo de lógica)
        hoje = datetime.datetime.now().strftime("%Y-%m-%d")
        data_agendada = dados.get("data_para_execucao")
        
        # Lógica: Só roda se a data bater e ainda não tiver executado com sucesso
        ja_executou = dados.get("executou_sucesso")

        print(f"Agendado: {data_agendada} | Hoje: {hoje} | Já feito? {ja_executou}")

        if data_agendada == hoje and not ja_executou:
            print(">>> INICIANDO TAREFA DO DIA... <<<")     
            hora = dados.get('hora')
            minuto = dados.get('minuto')

            agendar_via_at( hora, minuto )    

            sucesso = True  # Mude para False se der erro no seu script
            # ----------------------------------

            # 2. Reportar Sucesso
            reportar_servidor(sucesso)
        else:
            print("Não é hora de executar ou já foi feito.")

    except Exception as e:
        print(f"Erro fatal: {e}")

def reportar_servidor(sucesso):
    payload = {
        "sucesso": sucesso,
        "mensagem": "Script finalizado no Ubuntu com sucesso." if sucesso else "Falha no script."
    }
    try:
        requests.post(f"{URL}/api/confirmar-execucao", json=payload)
        print("Status atualizado no servidor com sucesso.")
    except:
        print("Falha ao avisar o servidor.")

def agendar_via_at(hora, minuto):
    try:
        
        # Validação simples
        if not hora or not minuto:
            print("Nenhum horário definido na resposta.")
            return

        print(f"Horário recebido do servidor: {hora}:{minuto}")

        # 2. Monta o comando 'at' conforme o seu pedido
        # Formato: echo "/caminho/script.sh" | at HH:MM
        comando_shell = f'echo "{SCRIPT_ALVO}" | at {hora}:{minuto}'
        
        print(f"A executar comando de sistema: {comando_shell}")

        # 3. Executa o comando no terminal do Linux
        processo = subprocess.run(
            comando_shell, 
            shell=True, 
            capture_output=True, 
            text=True
        )

        # 4. Verifica se o comando 'at' aceitou o pedido
        if processo.returncode == 0:
            print("Sucesso! Tarefa agendada no sistema 'at'.")
            print("Saída do sistema:", processo.stderr) # O 'at' costuma escrever no stderr
        else:
            print("Erro ao agendar no 'at'.")
            print("Erro:", processo.stderr)

    except Exception as e:
        print(f"Erro crítico: {e}")

if __name__ == "__main__":
    main()