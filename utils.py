import re
from pathlib import Path
import datetime


def tirar_print(driver, nome_arquivo):
    """Salva um screenshot para auditoria (essencial em headless)."""
    log_dir = Path("log")
    log_dir.mkdir(parents=True, exist_ok=True)
    nome = log_dir / f"{nome_arquivo}.png"
    try:
        driver.save_screenshot(str(nome))
    except Exception:
        # não levanta porque falhas de screenshot não devem abortar o fluxo
        pass


def extrair_linhas_tabela(driver):
    """Extrai todas as linhas da tabela de registros de ponto.

    Retorna uma lista de strings formatadas. Não levanta exceções.
    """
    resultados = []
    try:
        rows = driver.find_elements("css selector", "table.table tbody tr")
        for row in rows:
            try:
                tds = row.find_elements("tag name", "td")
                if len(tds) < 3:
                    continue
                data = tds[0].text.strip()
                dia = tds[1].text.strip()
                marcas_text = tds[2].get_attribute('innerText') or tds[2].text
                horarios = re.findall(r"\b\d{2}:\d{2}\b", marcas_text)
                if horarios:
                    linha = f"{data} {dia} " + " ".join(horarios)
                else:
                    linha = f"{data} {dia}"
                resultados.append(linha)
            except Exception:
                continue
    except Exception:
        pass
    return resultados


def extrair_linha_hoje(driver):
    """Extrai apenas a linha referente à data de hoje ou retorna None."""
    try:
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        rows = driver.find_elements("css selector", "table.table tbody tr")
        for row in rows:
            try:
                tds = row.find_elements("tag name", "td")
                if len(tds) < 3:
                    continue
                data = tds[0].text.strip()
                if data != hoje:
                    continue
                dia = tds[1].text.strip()
                marcas_text = tds[2].get_attribute('innerText') or tds[2].text
                horarios = re.findall(r"\b\d{2}:\d{2}\b", marcas_text)
                if horarios:
                    linha = f"{data} {dia} " + " ".join(horarios)
                else:
                    linha = f"{data} {dia}"
                return linha
            except Exception:
                continue
    except Exception:
        pass
    return None


def validar_linha_hoje(linha_hoje):
    """Valida se a linha de hoje tem data + dia + pelo menos 1 horário.

    Se houver 1 horário, valida esse horário. Se houver >=2, valida o último horário.
    O horário válido deve estar a no máximo 10 minutos de agora.
    """
    import datetime, re

    if not linha_hoje or not isinstance(linha_hoje, str):
        return False

    match = re.match(r"^(\d{2}/\d{2}/\d{4})\s+([A-Za-zÀ-ÿ]+)\s+((?:\d{2}:\d{2}\s*)+)$", linha_hoje.strip())
    if not match:
        return False

    data_str, dia_str, horarios_str = match.groups()
    horarios = re.findall(r"\d{2}:\d{2}", horarios_str)
    if len(horarios) < 1:
        return False

    try:
        hoje = datetime.datetime.now()

        if len(horarios) == 1:
            horario_valido = horarios[0]
        else:
            horario_valido = horarios[-1]

        horario_dt = datetime.datetime.strptime(horario_valido, "%H:%M").time()
        dt_valido = datetime.datetime.combine(hoje.date(), horario_dt)

        now = hoje
        diff = abs((now - dt_valido).total_seconds())

        # até 10 minutos = 600 segundos
        return diff <= 600
    except Exception:
        return False


def ja_batido_recente(linha_hoje) -> bool:
    """Verifica se há marcações de ponto hoje nas últimas 1 hora (ou futuro próximo devido a fuso/relógio)."""
    if not linha_hoje or not isinstance(linha_hoje, str):
        return False

    import re
    import datetime

    match = re.match(r"^(\d{2}/\d{2}/\d{4})\s+([A-Za-zÀ-ÿ]+)\s+((?:\d{2}:\d{2}\s*)+)$", linha_hoje.strip())
    if not match:
        return False

    data_str, dia_str, horarios_str = match.groups()
    horarios = re.findall(r"\d{2}:\d{2}", horarios_str)
    if not horarios:
        return False

    agora = datetime.datetime.now()
    for h_str in horarios:
        try:
            h_dt = datetime.datetime.strptime(h_str, "%H:%M").time()
            dt_punch = datetime.datetime.combine(agora.date(), h_dt)
            diff = (agora - dt_punch).total_seconds()
            # Se foi batido até 1h atrás (3600s) ou no futuro do mesmo dia (diff < 0)
            if diff <= 3600:
                return True
        except Exception:
            continue
    return False

