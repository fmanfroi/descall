import logging
import requests
import datetime
import subprocess
import os
from dotenv import load_dotenv
from typing import Optional

# Carrega variáveis de ambiente
load_dotenv(override=True)

URL = os.getenv("URL_API")
SCRIPT_ALVO = os.getenv("SCRIPT_PONTO")

# Logging básico (mantém configuração simples)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def post_json(session: requests.Session, path: str, payload: dict, timeout: int = 6) -> tuple[bool, Optional[object]]:
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
    try:
        resp = session.get(f"{URL}/api/consultar", timeout=6)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Erro ao buscar agendamento: %s", e)
        return None


def validar_horario(data: str, hora: str, minuto: str) -> tuple[bool, str]:
    """Retorna (ok, mensagem). ok=False quando horário é inválido ou passado."""
    try:
        h = int(str(hora))
        m = int(str(minuto))
        agendamento_dt = datetime.datetime.strptime(f"{data} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M")
        agora = datetime.datetime.now()
        if agendamento_dt <= agora:
            return False, f"horario passado ({agendamento_dt.isoformat()})"
        return True, ""
    except Exception as e:
        return False, f"dados de horário inválidos: {e}"


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


def reportar_servidor(session: requests.Session, status: str, msgsucesso: Optional[str] = None) -> bool:
    """Envia status final para o endpoint /api/confirmar-execucao."""
    payload = {"status": status}
    if msgsucesso is not None:
        payload["msgsucesso"] = msgsucesso
    ok, _ = post_json(session, "/api/confirmar-execucao", payload)
    return ok


def main() -> None:
    if not URL:
        logger.error("URL_API não definida. Ex: export URL_API=http://127.0.0.1:8000")
        return

    session = requests.Session()

    dados = fetch_agendamento(session)
    if not dados:
        logger.info("Nenhuma configuração encontrada ou erro ao consultar")
        return

    hoje = datetime.datetime.now().strftime("%Y-%m-%d")
    data_agendada = dados.get("data_para_execucao")
    ja_executou = dados.get("executou_sucesso")
    logger.info("Agendado: %s | Hoje: %s | Já feito? %s", data_agendada, hoje, ja_executou)

    if data_agendada != hoje or ja_executou:
        logger.info("Não é hora de executar ou já foi feito.")
        return

    hora = dados.get("hora")
    minuto = dados.get("minuto")

    ok, msg = validar_horario(data_agendada, hora, minuto)
    if not ok:
        logger.warning("Validação falhou: %s", msg)
        post_json(session, "/api/agendar", {"status": "falha", "msgsucesso": msg})
        reportar_servidor(session, "falha", msg)
        return

    # cria/atualiza registro de agendamento usando o campo `data_execucao` esperado pela API
    post_json(session, "/api/agendar", {"hora": hora, "minuto": minuto, "data_execucao": data_agendada, "status": "criado"})

    agendado_ok = agendar_via_at(hora, minuto)
    if agendado_ok:
        # Atualiza status para `agendado` no endpoint de confirmação (servidor aplica update)
        post_json(session, "/api/confirmar-execucao", {"status": "agendado", "msgsucesso": "agendado no at"})
        reportar_servidor(session, "agendado", "agendado no at")
    else:
        post_json(session, "/api/confirmar-execucao", {"status": "falha", "msgsucesso": "erro ao agendar"})
        reportar_servidor(session, "falha", "erro ao agendar")


if __name__ == "__main__":
    main()