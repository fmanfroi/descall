#!/bin/bash

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
echo "Iniciando script em: $(date)" >> "$ARQUIVO_LOG"

# Roda o script Python e salva o resultado (erros e prints) no arquivo de log
python3 "$SCRIPT_API_CLIENT" >> "$ARQUIVO_LOG" 2>&1

echo "Fim da execução em: $(date)" >> "$ARQUIVO_LOG"
deactivate