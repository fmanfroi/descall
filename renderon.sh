#!/bin/bash

PROJETO_DIR="/opt/descall"
ARQUIVO_LOG="$PROJETO_DIR/log/health-chek.log"

if [ -f "$PROJETO_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJETO_DIR/.env" | xargs)
else
    echo "ERRO: Arquivo .env não encontrado!" >> $ARQUIVO_LOG
    exit 1
fi
# -s : Silent (não mostra barra de progresso)
# -w : Write-out (adiciona o código de status HTTP ao final da resposta para debug)
RESPOSTA=$(curl -s -w " | Status HTTP: %{http_code}" $URL)

echo "[$DATA] Resposta: $RESPOSTA" >> $ARQUIVO_LOG