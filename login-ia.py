import time
import os
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
import urllib3
import google.generativeai as genai
import re
from pathlib import Path
import datetime

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
    # Adiciona o argumento para usar esse perfil específico
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
    
    # Para ativar o modo headless (sem interface), descomente a linha abaixo:
    firefox_options.add_argument("--headless")

    # --- 4. Inicialização do Driver ---
    service = Service(GeckoDriverManager().install())
    
    return webdriver.Firefox(service=service, options=firefox_options)

def resolver_captcha(driver, wait):
    """Localiza, baixa e resolve o CAPTCHA usando Gemini."""
    print("--- Iniciando resolução de CAPTCHA ---")
    try:
        if API_KEY == "SUA_KEY_AQUI":
            raise ValueError("API Key do Gemini não configurada!")

        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('models/gemini-flash-latest')

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
            print("Erro: Não foi possível obter bytes da imagem.")
            return None

        # Enviar para Gemini
        response = model.generate_content([
            {"mime_type": "image/png", "data": image_bytes},
            "Retorne APENAS os caracteres alfanuméricos desta imagem. Sem espaços, sem texto extra."
        ])
        
        texto_captcha = response.text.strip()
        print(f"Gemini identificou: {texto_captcha}")
        return texto_captcha

    except Exception as e:
        print(f"Erro no módulo de Captcha: {e}")
        return None

def tirar_print(driver, nome_arquivo):
    """Salva um screenshot para auditoria (Essencial em Headless)."""
    nome = f"log/debug_{nome_arquivo}.png"
    driver.save_screenshot(nome)
    print(f"[DEBUG] Screenshot salvo: {nome}")


def extrair_linhas_tabela(driver):
    """Extrai todas as linhas da tabela de registros de ponto no formato:
    DD/MM/YYYY DIA HH:MM [HH:MM ...]
    Recebe o `driver` (Selenium) já posicionado na página com a tabela.
    Retorna uma lista de strings formatadas.
    """
    resultados = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
        print(f"[DEBUG] Total de linhas encontradas na tabela: {len(rows)}")
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
                continue
    except Exception as e:
        print(f"Erro ao extrair linhas da tabela: {e}")
    return resultados


def extrair_linha_hoje(driver):
    """Extrai apenas a linha referente à data de hoje (DD/MM/YYYY) e retorna
    no formato: DD/MM/YYYY DIA HH:MM [HH:MM ...] ou None se não encontrada.
    """
    try:
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        rows = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
        print(f"[DEBUG] Procurando linha de hoje: {hoje} entre {len(rows)} linhas")
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
                print(f"[DEBUG] Linha de hoje encontrada (idx {i}): {linha}")
                return linha
            except Exception:
                continue
    except Exception as e:
        print(f"Erro ao buscar linha de hoje: {e}")
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
            print(f"Status atualizado no servidor com sucesso: {status}")
        except Exception:
            print(f"Servidor respondeu com erro: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Falha ao avisar o servidor: {e}")

def main():

    # Reporta que a execução está iniciando
    try:
        reportar_servidor("executando", None)
    except Exception as e:
        print(f"Falha ao reportar status executando: {e}")

    driver = setup_driver()
    wait = WebDriverWait(driver, 60)
    wait_check = WebDriverWait(driver, 10)

    try:
        print(f"Acessando: {URL_SITE}")
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
                
                print("Preenchendo credenciais...")
                wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_user"]))).send_keys(USUARIO)
                wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_pass"]))).send_keys(SENHA)
                
                if codigo_captcha:
                    wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_captcha"]))).send_keys(codigo_captcha)
                else:
                    print("AVISO: Tentando login sem captcha (ou falha no OCR)...")

                # 3. Clicar em Acessar
                tirar_print(driver, "01_pre_login")
                btn_login = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["btn_login"])))
                driver.execute_script("arguments[0].click();", btn_login)
                print("Botão Acessar clicado.")
                
                # 4. Validar se entrou (Esperar o menu aparecer)
                print("Aguardando carregamento do sistema...")
                time.sleep(5) # Pausa técnica para carregamento do Angular
                tirar_print(driver, "02_pos_login")

                # Tenta achar o menu para garantir que logou                
                wait.until(EC.presence_of_element_located((By.XPATH, XPATHS["menu_frequencia"])))
                print("Login confirmado! Menu encontrado.")                

            except TimeoutException:
                print("❌ ERRO CRÍTICO: O login falhou ou o site demorou demais.")
                print("Verifique se a senha está correta ou se houve captcha.")
                tirar_print(driver, "xx_erro_login")
                try:
                    reportar_servidor("falha", "login falhou ou captcha", sucesso=False)
                except Exception as e_rep:
                    print(f"Falha ao reportar falha de login: {e_rep}")
                driver.quit()
                exit() # Encerra o script  

        # 5. Navegação: Controle de Frequência
        menu = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["menu_frequencia"])))
        driver.execute_script("arguments[0].click();", menu)
        print("Menu 'Controle de Frequência' acessado.")
        time.sleep(2)

        # 6. Navegação: Registrar Ponto
        submenu = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["submenu_registrar"])))
        driver.execute_script("arguments[0].click();", submenu)
        print("Submenu 'Registrar' acessado.")
        time.sleep(3)
        tirar_print(driver, "03_tela_registro")


        # 7. AÇÃO FINAL: Registrar
        # Descomente as linhas abaixo para efetivar o ponto
        print("Procurando botão final de registro...")
        btn_final = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["btn_final_registrar"])))
        
        # --- ATENÇÃO: LINHA DE CLIQUE REAL ---
        # btn_final.click()
        print(">>> btn_final.click() <<<")
        
        print(">>> Botão de Ponto clicado (execução iniciada) <<<")
        
        time.sleep(5)
        tirar_print(driver, "04_final_resultado")

        # 2. Reportar status final — extrair apenas a linha do dia de hoje
        status = "sucesso"
        linha_hoje = None
        try:
            # Garantir que a tela de frequência esteja visível
            menu = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["menu_frequencia"])))
            driver.execute_script("arguments[0].click();", menu)
            print("Menu 'Controle de Frequência' acessado.")
            time.sleep(10)

            linha_hoje = extrair_linha_hoje(driver)
            if linha_hoje:
                print(f"Linha de hoje: {linha_hoje}")
            else:
                print("[DEBUG] Nenhuma marcação encontrada para hoje.")

            # Grava também em arquivo para revisão posterior (opcional)
            log_dir = Path("log")
            log_dir.mkdir(parents=True, exist_ok=True)
            out_file = log_dir / "linha_hoje_ponto.txt"
            try:
                with out_file.open("w", encoding="utf-8") as f:
                    f.write((linha_hoje or "") + "\n")
                print(f"[DEBUG] Linha de hoje gravada em: {out_file}")
            except Exception as e_file:
                print(f"Erro ao gravar arquivo da linha de hoje: {e_file}")

        except Exception as e:
            status = "falha"
            linha_hoje = str(e)
            print(f"Erro ao extrair/imprimir linha de hoje: {e}")

        # Reporta ao servidor incluindo a linha do dia (ou mensagem de erro)
        try:
            reportar_servidor(status, linha_hoje, sucesso=(status == "sucesso"))
        except Exception as e:
            print(f"Falha ao reportar status final: {e}")

    except Exception as e:
        print(f"ERRO FATAL NA EXECUÇÃO: {e}")
        tirar_print(driver, "erro_fatal")
        try:
            reportar_servidor("falha", str(e), sucesso=False)
        except Exception as e_rep:
            print(f"Falha ao reportar erro fatal: {e_rep}")
    
    finally:
        print("Encerrando driver e limpando memória...")
        driver.quit()


if __name__ == "__main__":
    main()