#!/bin/bash

# --- CONFIGURAÇÕES ---
DIRETORIO_DO_PROJETO="/home/fernando-manfroi/workspace/github/descall"
ARQUIVO_PYTHON="cliente.py"
ARQUIVO_LOG="$DIRETORIO_DO_PROJETO/log/execucao.log"

source /home/fernando-manfroi/venv/bin/activate

cd "$DIRETORIO_DO_PROJETO"

echo "---------------------------------" >> "$ARQUIVO_LOG"
echo "Iniciando script em: $(date)" >> "$ARQUIVO_LOG"

# Roda o script Python e salva o resultado (erros e prints) no arquivo de log
python3 "$ARQUIVO_PYTHON" >> "$ARQUIVO_LOG" 2>&1


echo "Fim da execução em: $(date)" >> "$ARQUIVO_LOG"
deactivate