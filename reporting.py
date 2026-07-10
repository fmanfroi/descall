import requests
from common import logger
from config import URL_API

_session = requests.Session()


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
    payload = {"status": status}
    if msgsucesso is not None:
        payload["msgsucesso"] = msgsucesso
    if sucesso is not None:
        payload["sucesso"] = bool(sucesso)
    ok, resp = post_json(_session, "/api/confirmar-execucao", payload)
    if ok:
        logger.info("Status atualizado no servidor: %s", status)
    else:
        logger.warning("Falha ao atualizar status no servidor: %s", resp)
