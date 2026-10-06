# Descall

A API usa `requirements.txt`. O cliente de agendamento e a automação de
registro usam `requirements-automation.txt`.

## Ambiente da automação

Crie o ambiente com a versão de Python instalada e instale as dependências:

```bash
cd /opt/descall
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-automation.txt
```

Se o sistema não tiver `ensurepip`, mas tiver `pip`, use:

```bash
python3 -m venv --without-pip .venv
python3 -m pip --python .venv install -r requirements-automation.txt
```

Configure `.env` com as variáveis usadas pelo projeto. `call-api.sh` e
`registrar.sh` usam diretamente `.venv/bin/python`. Quando esse ambiente
não existe, usam o Python da pasta indicada por `DIR_VENV` (caminho do
arquivo `bin/activate`).

Após uma atualização da versão principal/secundária do Python do sistema,
recrie o ambiente virtual e reinstale as dependências. Ambientes antigos
podem apontar para o novo executável e deixar de encontrar os pacotes
instalados para a versão anterior.

Verificação local sem consultar a API nem registrar ponto:

```bash
bash -n runtime.sh call-api.sh registrar.sh
.venv/bin/python -c 'import cliente; import requests; import dotenv'
```

A automação de navegador também requer o navegador/driver configurados
e o executável Tesseract para o OCR local.
