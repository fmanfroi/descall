import logging
import requests
import datetime
import subprocess
import os
import time
import re
import shlex
from pathlib import Path
import fcntl
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


def identificador(dados: dict) -> dict:
    return {"data_execucao": dados["data_para_execucao"],
            "hora": dados["hora"], "minuto": dados["minuto"]}


def comando_tarefa(dados: dict) -> str:
    wrapper = Path(__file__).resolve().with_name("executar_tarefa.py")
    return shlex.join([str(Path(os.sys.executable).absolute()), str(wrapper),
                       dados["data_para_execucao"], dados["hora"], dados["minuto"]])


def agendar_via_at(agendamento_dt: datetime.datetime, dados: dict) -> Optional[str]:
    """Agenda a execução protegida e retorna o identificador do trabalho."""
    if not SCRIPT_ALVO:
        logger.error("Variável SCRIPT_PONTO não definida")
        return None
    comando = comando_tarefa(dados)
    try:
        proc = subprocess.run(
            ["at", "-t", agendamento_dt.strftime("%Y%m%d%H%M")],
            input=comando + "\n", capture_output=True, text=True,
            env={**os.environ, "LC_ALL": "C"}, timeout=30,
        )
        match = re.search(r"\bjob (\d+) at\b", proc.stderr + proc.stdout)
        if proc.returncode == 0 and match:
            return match.group(1)
        logger.error("Erro ao identificar agendamento no at: %s", proc.stderr)
    except (OSError, subprocess.SubprocessError):
        logger.exception("Falha ao executar at")
    return None


def trabalhos_at() -> dict[str, datetime.datetime]:
    proc = subprocess.run(["atq"], capture_output=True, text=True, check=True,
                          env={**os.environ, "LC_ALL": "C"}, timeout=30)
    jobs = {}
    for linha in proc.stdout.splitlines():
        partes = linha.split()
        if len(partes) >= 8 and partes[0].isdigit():
            jobs[partes[0]] = datetime.datetime.strptime(
                " ".join(partes[1:6]), "%a %b %d %H:%M:%S %Y")
    return jobs


def processar_cancelamentos(session: requests.Session) -> None:
    """Remove somente os trabalhos associados às tarefas canceladas."""
    try:
        resp = session.get(f"{URL}/api/cancelamentos", timeout=30)
        resp.raise_for_status()
        pendentes = resp.json()
        if not pendentes:
            return
        jobs = trabalhos_at()
        for dados in pendentes:
            job_id = dados.get("job_id")
            ids = []
            if job_id:
                if not str(job_id).isdigit():
                    logger.error("Identificador do at inválido")
                    continue
                if str(job_id) in jobs:
                    ids = [str(job_id)]
            else:
                # Compatibilidade com tarefas criadas antes deste recurso.
                alvo = datetime.datetime.strptime(
                    f'{dados["data_para_execucao"]} {dados["hora"]}:{dados["minuto"]}',
                    "%Y-%m-%d %H:%M")
                for candidato, horario in jobs.items():
                    proc = subprocess.run(["at", "-c", candidato], capture_output=True,
                                          text=True, check=True, timeout=30)
                    linhas = [l.strip() for l in proc.stdout.splitlines()]
                    if comando_tarefa(dados) in linhas or (horario == alvo and SCRIPT_ALVO and SCRIPT_ALVO in linhas):
                        ids.append(candidato)
                if not ids:
                    logger.warning("Cancelamento legado pendente: não foi possível localizar o trabalho com segurança")
                    continue
            for id_at in ids:
                subprocess.run(["atrm", id_at], capture_output=True, text=True,
                               check=True, timeout=30)
            # Sem job na fila, a execução protegida também bloqueia o cancelamento.
            reportar_servidor(session, "cancelado", "Cancelamento confirmado no executor",
                              **identificador(dados))
    except (requests.RequestException, OSError, subprocess.SubprocessError, ValueError, KeyError):
        logger.exception("Falha ao processar cancelamentos; será tentado na próxima consulta")


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


def executar_cliente() -> None:
    if not URL:
        logger.error("URL_API não definida. Ex: export URL_API=http://127.0.0.1:8000")
        return

    session = requests.Session()

    processar_cancelamentos(session)
    dados = fetch_agendamento(session)
    if not dados:
        logger.info("Nenhuma tarefa encontrada ou erro ao consultar")
        return

    data_agendada = dados.get("data_para_execucao")
    hora = dados.get("hora")
    minuto = dados.get("minuto")
    ja_executou = dados.get("executou_sucesso")

    hoje = datetime.datetime.now().strftime("%Y-%m-%d")
    if data_agendada != hoje or ja_executou:
        logger.info("Tarefa futura ou já executada; mantendo estado para a próxima consulta")
        return

    ok, resposta = post_json(session, "/api/confirmar-execucao",
                             {"status": "consultado", **identificador(dados)})
    if not ok or not isinstance(resposta, dict) or resposta.get("tarefa", {}).get("status") != "consultado":
        logger.info("Tarefa não disponível para agendamento")
        return

    ok, msg, agendamento_dt = validar_horario(data_agendada, hora, minuto)
    if not ok or agendamento_dt is None:
        reportar_servidor(session, "falha", msg or "erro na validação de data",
                          **identificador(dados))
        return

    job_id = agendar_via_at(agendamento_dt, dados)
    if job_id:
        post_json(session, "/api/confirmar-execucao", {
            "status": "agendado", "msgsucesso": "agendado no at", "job_id": job_id,
            **identificador(dados),
        })
        # Cobre cancelamento solicitado durante a criação do trabalho.
        processar_cancelamentos(session)
    else:
        reportar_servidor(session, "falha", "erro ao agendar", **identificador(dados))


def main() -> None:
    pasta_log = Path(__file__).resolve().parent / "log"
    pasta_log.mkdir(exist_ok=True)
    with (pasta_log / "cliente.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Outra consulta já está em andamento")
            return
        executar_cliente()


if __name__ == "__main__":
    main()
