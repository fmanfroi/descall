#!/bin/bash
# cronjob para chamar a API do cliente para envio de relatórios
# 1,5 12 * * 1-5 /opt/descall/call-api.sh
# 30,45 18 * * 1-5 /opt/descall/call-api.sh


source "$(dirname -- "${BASH_SOURCE[0]}")/runtime.sh"

# Roda o script Python e salva o resultado (erros e prints) no arquivo de log
"$PYTHON_EXEC" "${SCRIPT_API_CLIENT:-$PROJETO_DIR/cliente.py}" >> "$ARQUIVO_LOG" 2>&1
