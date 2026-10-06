"""Verifica o estado da tarefa antes de iniciar o script de registro."""
import os
import subprocess
import sys

import requests
from dotenv import load_dotenv
from pathlib import Path


def main() -> int:
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=True)
    if len(sys.argv) != 4:
        return 1
    data, hora, minuto = sys.argv[1:]
    url = os.getenv("URL_API")
    script = os.getenv("SCRIPT_PONTO")
    if not url or not script:
        return 1
    try:
        resp = requests.post(f"{url}/api/iniciar-execucao", json={
            "data_execucao": data, "hora": hora, "minuto": minuto,
        }, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Execução bloqueada: não foi possível autorizar a tarefa ({exc})", file=sys.stderr)
        return 1
    ambiente = {**os.environ, "TAREFA_DATA_EXECUCAO": data,
                "TAREFA_HORA": hora, "TAREFA_MINUTO": minuto}
    return subprocess.run([script], env=ambiente).returncode


if __name__ == "__main__":
    sys.exit(main())
