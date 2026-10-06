import requests
import os
from common import logger
from config import URL_API

_session = requests.Session()
_ultima_falha = None


def limpar_ultima_falha():
    global _ultima_falha
    _ultima_falha = None


def ultima_mensagem_falha():
    return _ultima_falha


def post_json(session: requests.Session, path: str, payload: dict, timeout: int = 6) -> tuple[bool, object]:
    """Faz POST e retorna (sucesso, json_ou_text)."""
    if not URL_API:
        logger.error("URL_API não configurada")
        return False, "URL_API not set"

    url = f"{URL_API}{path}"
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


def reportar_servidor(status, msgsucesso=None, sucesso: bool = None):
    """Reporta o status para o servidor usando o helper `post_json`."""
    global _ultima_falha
    if status == "falha" and msgsucesso:
        _ultima_falha = str(msgsucesso)
    payload = {"status": status}
    for campo, variavel in (("data_execucao", "TAREFA_DATA_EXECUCAO"),
                            ("hora", "TAREFA_HORA"), ("minuto", "TAREFA_MINUTO")):
        if os.getenv(variavel):
            payload[campo] = os.environ[variavel]
    if msgsucesso is not None:
        payload["msgsucesso"] = msgsucesso
    if sucesso is not None:
        payload["sucesso"] = bool(sucesso)
    ok, resp = post_json(_session, "/api/confirmar-execucao", payload)
    if ok:
        logger.info("Status atualizado no servidor: %s", status)
    else:
        logger.warning("Falha ao atualizar status no servidor: %s", resp)
