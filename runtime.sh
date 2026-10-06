#!/bin/bash
# Carregado pelos scripts de execução; não imprime valores do .env.
PROJETO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ARQUIVO_LOG="$PROJETO_DIR/log/execucao.log"
mkdir -p "$PROJETO_DIR/log" || exit 1

if [ ! -f "$PROJETO_DIR/.env" ]; then
    echo "ERRO: Arquivo .env não encontrado!" >> "$ARQUIVO_LOG"
    exit 1
fi

export $(grep -v '^#' "$PROJETO_DIR/.env" | xargs)

# Prefere o ambiente do projeto; mantém compatibilidade com DIR_VENV.
PYTHON_EXEC="$PROJETO_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="$(dirname -- "${DIR_VENV:-$PROJETO_DIR/venv/bin/activate}")/python"
fi
if [ ! -x "$PYTHON_EXEC" ] || ! "$PYTHON_EXEC" -c 'import requests, dotenv' >> "$ARQUIVO_LOG" 2>&1; then
    echo "ERRO: Ambiente Python ausente ou incompatível. Instale requirements-automation.txt no ambiente virtual do projeto." >> "$ARQUIVO_LOG"
    exit 1
fi
cd "$PROJETO_DIR" || exit 1
