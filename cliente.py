import logging
import requests
import datetime
import subprocess
import os
import time
from dotenv import load_dotenv
from typing import Optional

# Carrega variáveis de ambiente
load_dotenv(override=True)

URL = os.getenv("URL_API")
SCRIPT_ALVO = os.getenv("SCRIPT_PONTO")

# Logging básico (mantém configuração simples)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def post_json(session: requests.Session, path: str, payload: dict, timeout: int = 16) -> tuple[bool, Optional[object]]:
    """Faz POST e retorna (sucesso, json_ou_text).
    Retorna (False, error_text) em falha.
    """
    if not URL:
        logger.error("URL_API não configurada")
        return False, "URL_API not set"

    url = f"{URL}{path}"
    try:
        resp = session.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        try:
            return True, resp.json()
        except Exception:
            return True, resp.text
    except Exception as e:
        logger.warning("Falha POST %s: %s", url, e)
        return False, str(e)


def fetch_agendamento(session: requests.Session) -> Optional[dict]:
    if not URL:
        logger.error("URL_API não configurada")
        return None
    attempts = 2
    for attempt in range(1, attempts + 1):
        try:
            resp = session.get(f"{URL}/api/consultar", timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Erro ao buscar agendamento: %s", e)
            if attempt < attempts:
                logger.info("Aguardando 60s antes de tentar novamente...")
                time.sleep(60)
            else:
                return None


def validar_horario(data: str, hora: str, minuto: str) -> tuple[bool, str, Optional[datetime.datetime]]:
    """Retorna (ok, mensagem, agendamento_dt). ok=False quando horário é inválido ou passou além da tolerância."""
    try:
        h = int(str(hora))
        m = int(str(minuto))
        agendamento_dt = datetime.datetime.strptime(f"{data} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M")
        agora = datetime.datetime.now()
        tolerancia = datetime.timedelta(minutes=10)
        if agendamento_dt + tolerancia < agora:
            logger.warning("Agendamento fora da tolerância (>=10m atrasado): %s", agendamento_dt.isoformat())
            return False, f"horario passado ({agendamento_dt.isoformat()})", None
        if agendamento_dt < agora:
            logger.info("Agendamento dentro da tolerância (<10m atrás). Ajustando de %s para agora+1min", agendamento_dt.isoformat())
            agendamento_dt = agora + datetime.timedelta(minutes=1)
        return True, "", agendamento_dt
    except Exception as e:
        logger.error("Erro ao validar horário: %s", e)
        return False, f"dados de horário inválidos: {e}", None


def agendar_via_at(hora: str, minuto: str) -> bool:
    """Agenda o `SCRIPT_ALVO` via `at`. Retorna True se agendado com sucesso."""
    if not SCRIPT_ALVO:
        logger.error("Variável SCRIPT_PONTO não definida")
        return False
    if hora is None or minuto is None:
        logger.error("Hora ou minuto não informados")
        return False

    comando = f'echo "{SCRIPT_ALVO}" | at {int(hora):02d}:{int(minuto):02d}'
    logger.info("Executando: %s", comando)
    try:
        proc = subprocess.run(comando, shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            logger.info("Agendamento aceito pelo at: %s", (proc.stderr or proc.stdout).strip())
            return True
        else:
            logger.error("Erro ao agendar via at: %s", (proc.stderr or proc.stdout).strip())
            return False
    except Exception as e:
        logger.exception("Erro crítico ao executar at: %s", e)
        return False


def reportar_servidor(session: requests.Session, status: str, msgsucesso: Optional[str] = None, data_execucao: Optional[str] = None, hora: Optional[str] = None, minuto: Optional[str] = None) -> bool:
    """Envia status final para o endpoint /api/confirmar-execucao."""
    payload = {"status": status}
    if msgsucesso is not None:
        payload["msgsucesso"] = msgsucesso
    if data_execucao is not None:
        payload["data_execucao"] = data_execucao
    if hora is not None:
        payload["hora"] = hora
    if minuto is not None:
        payload["minuto"] = minuto
    ok, _ = post_json(session, "/api/confirmar-execucao", payload)
    return ok


def main() -> None:
    if not URL:
        logger.error("URL_API não definida. Ex: export URL_API=http://127.0.0.1:8000")
        return

    session = requests.Session()

    dados = fetch_agendamento(session)
    if not dados:
        logger.info("Nenhuma tarefa encontrada ou erro ao consultar")
        return

    data_agendada = dados.get("data_para_execucao")
    hora = dados.get("hora")
    minuto = dados.get("minuto")
    ja_executou = dados.get("executou_sucesso")

    # Marca como consultado para indicar que o cliente recebeu a tarefa
    try:
        reportar_servidor(session, "consultado", data_execucao=data_agendada, hora=hora, minuto=minuto)
    except Exception as e:
        logger.warning("Falha ao marcar como consultado: %s", e)

    hoje = datetime.datetime.now().strftime("%Y-%m-%d")
    logger.info("Agendado: %s | Hoje: %s | Já feito? %s", data_agendada, hoje, ja_executou)

    if data_agendada != hoje or ja_executou:
        logger.info("Não é hora de executar ou já foi feito.")
        return

    ok, msg, agendamento_dt = validar_horario(data_agendada, hora, minuto)
    if not ok:
        logger.warning("Validação falhou: %s", msg)
        post_json(session, "/api/agendar", {
            "hora": hora,
            "minuto": minuto,
            "data_execucao": data_agendada,
            "status": "falha",
            "msgsucesso": msg
        })
        reportar_servidor(session, "falha", msg, data_execucao=data_agendada, hora=hora, minuto=minuto)
        return

    if agendamento_dt is None:
        logger.error("Agendamento inválido e não há data a usar")
        post_json(session, "/api/agendar", {
            "hora": hora,
            "minuto": minuto,
            "data_execucao": data_agendada,
            "status": "falha",
            "msgsucesso": "erro na validação de data"
        })
        reportar_servidor(session, "falha", "erro na validação de data", data_execucao=data_agendada, hora=hora, minuto=minuto)
        return

    logger.info("Agendamento definido para execução: %s", agendamento_dt.isoformat())

    hora_corrigida = f"{agendamento_dt.hour:02d}"
    minuto_corrigido = f"{agendamento_dt.minute:02d}"
    data_corrigida = agendamento_dt.strftime("%Y-%m-%d")

    # cria/atualiza registro de agendamento usando o campo `data_execucao` esperado pela API
    post_json(session, "/api/agendar", {"hora": hora_corrigida, "minuto": minuto_corrigido, "data_execucao": data_corrigida, "status": "criado"})

    agendado_ok = agendar_via_at(hora_corrigida, minuto_corrigido)
    if agendado_ok:
        # Atualiza status para `agendado` no endpoint de confirmação (servidor aplica update)
        post_json(session, "/api/confirmar-execucao", {
            "status": "agendado",
            "msgsucesso": "agendado no at",
            "data_execucao": data_corrigida,
            "hora": hora_corrigida,
            "minuto": minuto_corrigido
        })
        reportar_servidor(session, "agendado", "agendado no at", data_execucao=data_corrigida, hora=hora_corrigida, minuto=minuto_corrigido)
    else:
        post_json(session, "/api/confirmar-execucao", {
            "status": "falha",
            "msgsucesso": "erro ao agendar",
            "data_execucao": data_corrigida,
            "hora": hora_corrigida,
            "minuto": minuto_corrigido
        })
        reportar_servidor(session, "falha", "erro ao agendar", data_execucao=data_corrigida, hora=hora_corrigida, minuto=minuto_corrigido)


if __name__ == "__main__":
    main()