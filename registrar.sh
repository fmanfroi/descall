#!/bin/bash

source "$(dirname -- "${BASH_SOURCE[0]}")/runtime.sh"

# --- TRECHO PARA FECHAR FIREFOX ---
# Define o nome do processo (pode ser firefox ou firefox-bin)
PROCESSO="firefox"
if pgrep -f "$PROCESSO" > /dev/null; then    
    echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Firefox detectado aberto. Fechando..." >> $ARQUIVO_LOG        
    sudo pkill -f "$PROCESSO"        
    sleep 5   
    if pgrep -f "$PROCESSO" > /dev/null; then
        echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Firefox não fechou. Forçando encerramento (SIGKILL)..." >> $ARQUIVO_LOG        
        sudo pkill -9 -f "$PROCESSO"
    else
        echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Firefox fechado com sucesso." >> $ARQUIVO_LOG
    fi
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Verificação: Firefox já estava fechado." >> $ARQUIVO_LOG
fi
# --- FIM DO TRECHO ---

# --- EXECUÇÃO ---
# Registra a data e hora de início no log
echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Iniciando registrar.sh" >> "$ARQUIVO_LOG"
export DISPLAY=:0
# Roda o script Python e salva o resultado (erros e prints) no arquivo de log

"$PYTHON_EXEC" "${LOGIN_PYTHON:-$PROJETO_DIR/login-ocr-ai.py}" >> "$ARQUIVO_LOG" 2>&1
RESULTADO=$?

# Registra o fim
echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Fim registrar.sh" >> "$ARQUIVO_LOG"

exit "$RESULTADO"
