#!/bin/bash
# cronjob para chamar a API do cliente para envio de relatórios
# 1,5 12 * * 1-5 /opt/descall/call-api.sh
# 30,45 18 * * 1-5 /opt/descall/call-api.sh


PROJETO_DIR="/opt/descall"
ARQUIVO_LOG="$PROJETO_DIR/log/execucao.log"

if [ -f "$PROJETO_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJETO_DIR/.env" | xargs)
else
    echo "ERRO: Arquivo .env não encontrado!" >> $LOG_FILE
    exit 1
fi

source "$DIR_VENV"

cd "$PROJETO_DIR"

echo "---------------------------------" >> "$ARQUIVO_LOG"
echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Iniciando call-api.sh" >> "$ARQUIVO_LOG"


# Roda o script Python e salva o resultado (erros e prints) no arquivo de log
python3 "$SCRIPT_API_CLIENT" >> "$ARQUIVO_LOG" 2>&1

echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Fim call-api.sh" >> "$ARQUIVO_LOG"
deactivate