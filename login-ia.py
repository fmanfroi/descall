import time
import os
import logging
import requests
import base64
import urllib3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
import google.generativeai as genai
import re
from pathlib import Path
import datetime

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Suprimir avisos de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. CONFIGURAÇÕES E CREDENCIAIS ---
# Tente pegar das variáveis de ambiente do Linux, ou use o valor padrão (fallback)
URL_SITE = os.getenv("URL_SITE")
URL_API = os.getenv("URL_API")
USUARIO = os.getenv("PONTO_USER")
SENHA = os.getenv("PONTO_PASS")
API_KEY = os.getenv("GOOGLE_API_KEY")
FIREFOX_PROFILE_PATH = os.getenv("FIREFOX_PROFILE_PATH")
HEADLESS = os.getenv("HEADLESS", "1")

# --- 2. SELETORES (XPATH) ---
XPATHS = {
    "captcha_img": "//img[contains(@src, 'data:image')]",
    "input_user": "//input[contains(@formcontrolname, 'username') or contains(@placeholder, 'Usuário')]",
    "input_pass": "//input[@type='password']",
    "input_captcha": "//input[contains(@formcontrolname, 'captcha') or contains(@placeholder, '(Captcha)')]",
    "btn_login": "//button[normalize-space()='ACESSAR']",
    "menu_frequencia": "//a[@href='#/frequencia-ponto']",
    "submenu_registrar": "//a[@href='#/frequencia-ponto/registrar-ponto']",
    # Botão final verde de registrar
    "btn_final_registrar": "//button[contains(@class, 'btn-success') and contains(., 'Registrar Frequência')]" 
}

def setup_driver():
    """Configura o Firefox (GeckoDriver)."""
    firefox_options = Options()        
    # Adiciona o argumento para usar esse perfil específico, se informado
    if FIREFOX_PROFILE_PATH:
        firefox_options.add_argument("-profile")
        firefox_options.add_argument(FIREFOX_PROFILE_PATH)

    # --- 1. Configuração de Certificados (Equivalente a ignore-certificate-errors) ---
    firefox_options.accept_insecure_certs = True

    # --- 2. Preferências (Substitui o 'prefs' do Chrome) ---
    # Desabilita notificações nativas (push notifications)
    firefox_options.set_preference("dom.webnotifications.enabled", False)
    firefox_options.set_preference("dom.push.enabled", False)
    
    # Tenta evitar popups de confirmação
    firefox_options.set_preference("dom.disable_open_during_load", True)
    
    # O Firefox lida com acesso a rede local de forma diferente do Chrome.
    # Geralmente ele é menos intrusivo, mas essas prefs ajudam a silenciar alertas:
    firefox_options.set_preference("network.negotiate-auth.allow-insecure-ntlm-v1", True)
    
    # --- 3. Tamanho da Janela e Headless ---
    # No Firefox, usa-se --width e --height ou arguments
    firefox_options.add_argument("--width=1920")
    firefox_options.add_argument("--height=1080")
    
    # Headless controlado por variável de ambiente HEADLESS ("1" ou "0")
    try:
        if HEADLESS and HEADLESS != "0":
            firefox_options.add_argument("--headless")
    except Exception:
        firefox_options.add_argument("--headless")

    # --- 4. Inicialização do Driver ---
    service = Service(GeckoDriverManager().install())

    return webdriver.Firefox(service=service, options=firefox_options)

def resolver_captcha(driver, wait):
    """Localiza, baixa e resolve o CAPTCHA usando Gemini."""
    logger.info("Iniciando resolução de CAPTCHA")
    try:
        if not API_KEY:
            logger.warning("GOOGLE_API_KEY não configurada; pulando resolução por Gemini")
            return None

        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("models/gemini-flash-latest")

        # Localizar imagem
        img_element = wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["captcha_img"])))
        src_data = img_element.get_attribute('src')
        
        image_bytes = None
        if "data:image" in src_data:
            base64_str = src_data.split(',')[1]
            image_bytes = base64.b64decode(base64_str)
        else:
            resp = requests.get(src_data, verify=False)
            if resp.status_code == 200:
                image_bytes = resp.content

        if not image_bytes:
            logger.error("Não foi possível obter bytes da imagem do CAPTCHA")
            return None

        # Enviar para Gemini
        response = model.generate_content([
            {"mime_type": "image/png", "data": image_bytes},
            "Retorne APENAS os caracteres alfanuméricos desta imagem. Sem espaços, sem texto extra."
        ])

        texto_captcha = getattr(response, "text", "").strip()
        logger.info("Gemini identificou captcha: %s", texto_captcha)
        return texto_captcha

    except Exception as e:
        logger.exception("Erro no módulo de Captcha: %s", e)
        return None

def tirar_print(driver, nome_arquivo):
    """Salva um screenshot para auditoria (Essencial em Headless)."""
    log_dir = Path("log")
    log_dir.mkdir(parents=True, exist_ok=True)
    nome = log_dir / f"debug_{nome_arquivo}.png"
    try:
        driver.save_screenshot(str(nome))
        logger.debug("Screenshot salvo: %s", nome)
    except Exception:
        logger.exception("Falha ao salvar screenshot %s", nome)


def extrair_linhas_tabela(driver):
    """Extrai todas as linhas da tabela de registros de ponto no formato:
    DD/MM/YYYY DIA HH:MM [HH:MM ...]
    Recebe o `driver` (Selenium) já posicionado na página com a tabela.
    Retorna uma lista de strings formatadas.
    """
    resultados = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
        logger.debug("Total de linhas encontradas na tabela: %d", len(rows))
        for i, row in enumerate(rows):
            try:
                tds = row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 3:
                    continue
                data = tds[0].text.strip()
                dia = tds[1].text.strip()
                # Extrai todos os horários no formato HH:MM do conteúdo da célula
                marcas_text = tds[2].get_attribute('innerText') or tds[2].text                
                horarios = re.findall(r"\b\d{2}:\d{2}\b", marcas_text)
                if horarios:
                    linha = f"{data} {dia} " + " ".join(horarios)
                else:
                    linha = f"{data} {dia}"
                resultados.append(linha)
            except Exception:
                logger.debug("Erro ao processar linha %d", i)
                continue
    except Exception as e:
        logger.exception("Erro ao extrair linhas da tabela: %s", e)
    return resultados


def extrair_linha_hoje(driver):
    """Extrai apenas a linha referente à data de hoje (DD/MM/YYYY) e retorna
    no formato: DD/MM/YYYY DIA HH:MM [HH:MM ...] ou None se não encontrada.
    """
    try:
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        rows = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
        logger.debug("Procurando linha de hoje: %s entre %d linhas", hoje, len(rows))
        for i, row in enumerate(rows):
            try:
                tds = row.find_elements(By.TAG_NAME, "td")
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
                logger.debug("Linha de hoje encontrada (idx %d): %s", i, linha)
                return linha
            except Exception:
                continue
    except Exception as e:
        logger.exception("Erro ao buscar linha de hoje: %s", e)
    return None

def reportar_servidor(status, msgsucesso=None, sucesso: bool = None):
    """Reporta o status para o servidor.
    status: criado, consultado, agendado, executando, falha, sucesso
    msgsucesso: mensagem livre (ex.: linha extraída)
    sucesso: booleano opcional indicando sucesso final
    """
    payload = {"status": status}
    if msgsucesso is not None:
        payload["msgsucesso"] = msgsucesso
    if sucesso is not None:
        payload["sucesso"] = bool(sucesso)
    try:
        resp = requests.post(f"{URL_API}/api/confirmar-execucao", json=payload, timeout=5)
        try:
            resp.raise_for_status()
            logger.info("Status atualizado no servidor: %s", status)
        except Exception:
            logger.warning("Servidor respondeu com erro: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.exception("Falha ao avisar o servidor: %s", e)

def run_once() -> bool:
    """Executa todo o fluxo de registrar ponto uma vez.
    Retorna True se o processo completou (mesmo que não tenha encontrado linha hoje),
    False em caso de erro fatal que deva disparar um retry.
    """
    driver = None
    try:
        driver = setup_driver()
    except Exception as e:
        logger.exception("Erro iniciando o WebDriver: %s", e)
        reportar_servidor("falha", "erro iniciando webdriver", sucesso=False)
        return False

    wait = WebDriverWait(driver, 60)
    wait_check = WebDriverWait(driver, 10)

    try:
        logger.info("Acessando: %s", URL_SITE)
        driver.get(URL_SITE)

        try:
            # TENTATIVA 1: Verifica se o menu JÁ está na tela (sessão salva no perfil)
            wait_check.until(EC.presence_of_element_located((By.XPATH, XPATHS["menu_frequencia"])))
            print("✅ Já está logado! Pulando etapa de autenticação.")

        except TimeoutException:
            # Se cair aqui, é porque o menu NÃO apareceu em 5 segundos.
            print("ℹ️ Não está logado. Iniciando processo de login...")
            try:
                # 1. Resolver Captcha
                codigo_captcha = resolver_captcha(driver, wait)

                logger.info("Preenchendo credenciais...")
                wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_user"]))).send_keys(USUARIO)
                wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_pass"]))).send_keys(SENHA)

                if codigo_captcha:
                    wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_captcha"]))).send_keys(codigo_captcha)
                else:
                    logger.warning("Tentando login sem captcha (ou falha no OCR)")

                # 3. Clicar em Acessar
                tirar_print(driver, "01_pre_login")
                btn_login = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["btn_login"])))
                driver.execute_script("arguments[0].click();", btn_login)
                logger.info("Botão Acessar clicado.")

                # 4. Validar se entrou (Esperar o menu aparecer)
                logger.info("Aguardando carregamento do sistema...")
                time.sleep(5)  # Pausa técnica para carregamento do Angular
                tirar_print(driver, "02_pos_login")

                # Tenta achar o menu para garantir que logou
                wait.until(EC.presence_of_element_located((By.XPATH, XPATHS["menu_frequencia"])))
                logger.info("Login confirmado! Menu encontrado.")

            except TimeoutException:
                logger.error("ERRO CRÍTICO: O login falhou ou o site demorou demais.")
                logger.error("Verifique se a senha está correta ou se houve captcha.")
                tirar_print(driver, "xx_erro_login")
                try:
                    reportar_servidor("falha", "login falhou ou captcha", sucesso=False)
                except Exception as e_rep:
                    logger.warning("Falha ao reportar falha de login: %s", e_rep)
                return False

        # 5. Navegação: Controle de Frequência
        menu = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["menu_frequencia"])))
        driver.execute_script("arguments[0].click();", menu)
        logger.info("Menu 'Controle de Frequência' acessado.")
        time.sleep(2)

        # 6. Navegação: Registrar Ponto
        submenu = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["submenu_registrar"])))
        driver.execute_script("arguments[0].click();", submenu)
        logger.info("Submenu 'Registrar' acessado.")
        time.sleep(3)
        tirar_print(driver, "03_tela_registro")

        # 7. AÇÃO FINAL: Registrar
        logger.info("Procurando botão final de registro...")
        btn_final = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["btn_final_registrar"])))

        # --- ATENÇÃO: LINHA DE CLIQUE REAL ---
        btn_final.click()
        # logger.info(">>> btn_final.click() <<<")
        logger.info(">>> Botão de Ponto clicado (execução iniciada) <<<")

        time.sleep(5)
        tirar_print(driver, "04_final_resultado")

        # 2. Reportar status final — extrair apenas a linha do dia de hoje
        status = "sucesso"
        linha_hoje = None
        try:
            # Garantir que a tela de frequência esteja visível
            menu = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["menu_frequencia"])))
            driver.execute_script("arguments[0].click();", menu)
            logger.info("Menu 'Controle de Frequência' acessado.")
            time.sleep(10)

            linha_hoje = extrair_linha_hoje(driver)
            if linha_hoje:
                logger.info("Linha de hoje: %s", linha_hoje)
            else:
                logger.debug("Nenhuma marcação encontrada para hoje.")

            # Grava também em arquivo para revisão posterior (opcional)
            log_dir = Path("log")
            log_dir.mkdir(parents=True, exist_ok=True)
            out_file = log_dir / "linha_hoje_ponto.txt"
            try:
                with out_file.open("w", encoding="utf-8") as f:
                    f.write((linha_hoje or "") + "\n")
                logger.debug("Linha de hoje gravada em: %s", out_file)
            except Exception as e_file:
                logger.exception("Erro ao gravar arquivo da linha de hoje: %s", e_file)

        except Exception as e:
            status = "falha"
            linha_hoje = str(e)
            logger.exception("Erro ao extrair/imprimir linha de hoje: %s", e)

        # Reporta ao servidor incluindo a linha do dia (ou mensagem de erro)
        try:
            reportar_servidor(status, linha_hoje, sucesso=(status == "sucesso"))
        except Exception as e:
            logger.warning("Falha ao reportar status final: %s", e)

        return True

    except Exception as e:
        logger.exception("ERRO FATAL NA EXECUÇÃO: %s", e)
        try:
            tirar_print(driver, "erro_fatal")
        except Exception:
            logger.debug("Falha ao salvar screenshot de erro fatal")
        try:
            reportar_servidor("falha", str(e), sucesso=False)
        except Exception as e_rep:
            logger.warning("Falha ao reportar erro fatal: %s", e_rep)
        return False

    finally:
        logger.info("Encerrando driver e limpando memória...")
        try:
            if driver:
                driver.quit()
        except Exception:
            logger.debug("Driver já encerrado ou erro ao fechar")


def main():
    # Reporta que a execução está iniciando
    try:
        reportar_servidor("executando", None)
    except Exception as e:
        logger.warning("Falha ao reportar status executando: %s", e)

    attempts = int(os.getenv("REGISTER_ATTEMPTS", "2"))
    for attempt in range(1, attempts + 1):
        logger.info("Iniciando tentativa %d/%d", attempt, attempts)
        ok = run_once()
        if ok:
            logger.info("Fluxo completado com sucesso na tentativa %d", attempt)
            return
        if attempt < attempts:
            logger.warning("Tentativa %d falhou — aguardando e tentando novamente...", attempt)
            time.sleep(60)

    logger.error("Todas as tentativas (%d) falharam. Marcando como falha definitiva.", attempts)
    try:
        reportar_servidor("falha", "todas as tentativas falharam", sucesso=False)
    except Exception:
        logger.debug("Falha ao reportar falha definitiva")


if __name__ == "__main__":
    main()