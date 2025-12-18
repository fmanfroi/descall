#!/bin/bash

PROJETO_DIR="/opt/descall"
ARQUIVO_LOG="$PROJETO_DIR/log/execucao.log"

if [ -f "$PROJETO_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJETO_DIR/.env" | xargs)
else
    echo "ERRO: Arquivo .env não encontrado!" >> $LOG_FILE
    exit 1
fi

# URL do servidor
URL="$URL_API/health-check"

# Envia uma requisição GET silenciosa (-s) e mostra apenas o código de status (-o /dev/null -w "%{http_code}")
# Ou simplesmente um curl simples se preferir ver o output
curl -s -o /dev/null -w "Ping em $URL: HTTP %{http_code} em $(date)\n" $URL >> "$ARQUIVO_LOG"