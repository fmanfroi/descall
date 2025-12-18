#!/bin/bash
# cronjob para checagem de saúde da API
# Executa a cada 5 minutos durante o horário comercial (11h-12h e 18h-19h) de segunda a sexta-feira
# */5 11-12 * * 1-5 /opt/descall/renderon.sh
# */5 18-19 * * 1-5 /opt/descall/renderon.sh

PROJETO_DIR="/opt/descall"
ARQUIVO_LOG="$PROJETO_DIR/log/health-chek.log"

if [ -f "$PROJETO_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJETO_DIR/.env" | xargs)
else
    echo "ERRO: Arquivo .env não encontrado!" >> $ARQUIVO_LOG
    exit 1
fi
echo "---------------------------------" >> "$ARQUIVO_LOG"
echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Iniciando renderon.sh" >> "$ARQUIVO_LOG"
# -s : Silent (não mostra barra de progresso)
# -w : Write-out (adiciona o código de status HTTP ao final da resposta para debug)
RESPOSTA=$(curl -s -w " | Status HTTP: %{http_code}" $URL_API/health-check)

DATA=$(date "+%Y-%m-%d %H:%M:%S")
echo "[$DATA] Resposta: $RESPOSTA" >> $ARQUIVO_LOG

echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Fim renderon.sh" >> "$ARQUIVO_LOG"