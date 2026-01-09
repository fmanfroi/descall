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

# Faz a requisição e captura a resposta JSON
RESPOSTA_JSON=$(curl -s $URL_API/health-check)
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $URL_API/health-check)

# Extrai os campos do JSON usando grep/sed ou jq se disponível
if command -v jq &> /dev/null; then
    STATUS=$(echo "$RESPOSTA_JSON" | jq -r '.status // "N/A"')
    MESSAGE=$(echo "$RESPOSTA_JSON" | jq -r '.message // "N/A"')
    EXECUTOU_SUCESSO=$(echo "$RESPOSTA_JSON" | jq -r 'if has("executou_sucesso") then (.executou_sucesso|tostring) else "N/A" end')
else
    # Fallback sem jq: usa grep e sed com tratamento melhorado
    STATUS=$(echo "$RESPOSTA_JSON" | grep -o '"status":"[^"]*' | head -1 | cut -d'"' -f4)
    MESSAGE=$(echo "$RESPOSTA_JSON" | grep -o '"message":"[^"]*' | head -1 | cut -d'"' -f4)
    # executou_sucesso pode ser true/false/null (não está entre aspas). Captura true/false ou null
    EXECUTOU_SUCESSO=$(echo "$RESPOSTA_JSON" | grep -o '"executou_sucesso"\s*:\s*\(true\|false\|null\)' | head -1 | sed -E 's/.*: *//')
    
    # Se algum campo não foi encontrado, trata com N/A
    STATUS=${STATUS:-N/A}
    MESSAGE=${MESSAGE:-N/A}
    EXECUTOU_SUCESSO=${EXECUTOU_SUCESSO:-N/A}
fi

DATA=$(date "+%Y-%m-%d %H:%M:%S")
echo "[$DATA] HTTP:$HTTP_STATUS | Status:$STATUS | executou_sucesso:$EXECUTOU_SUCESSO | MSG:$MESSAGE" >> "$ARQUIVO_LOG"
