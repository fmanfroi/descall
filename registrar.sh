#!/bin/bash

# --- CONFIGURAÇÃO ---
PROJETO_DIR="/home/fernando-manfroi/workspace/github/descall"
ARQUIVO_LOG="$PROJETO_DIR/execucao.log"

# --- CARREGA O .ENV ---
# Se o arquivo existir, carrega as variáveis
if [ -f "$PROJETO_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJETO_DIR/.env" | xargs)
else
    echo "ERRO: Arquivo .env não encontrado!" >> $LOG_FILE
    exit 1
fi

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
# Ativa o ambiente virtual (venv) Isso é crucial no Ubuntu 24 para não dar erro de módulo
source venv/bin/activate

# Entra na pasta do projeto
cd "$PROJETO_DIR"
# Registra a data e hora de início no log
echo "---------------------------------" >> "$ARQUIVO_LOG"
echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Iniciando script" >> "$ARQUIVO_LOG"
export DISPLAY=:0
# Roda o script Python e salva o resultado (erros e prints) no arquivo de log

#python3 "$LOGIN_PYTHON" >> "$ARQUIVO_LOG" 2>&1

# Registra o fim
echo "[$(date +'%Y-%m-%d %H:%M:%S.%3N')] Fim da execução" >> "$ARQUIVO_LOG"

# Desativa o ambiente virtual
deactivate