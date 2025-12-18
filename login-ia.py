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
    #firefox_options.add_argument("--headless")

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

def reportar_servidor(sucesso):
    payload = {
        "sucesso": sucesso,
        "mensagem": "Script finalizado no Ubuntu com sucesso." if sucesso else "Falha no script."
    }
    try:
        requests.post(f"{URL_API}/api/confirmar-execucao", json=payload)
        print("Status atualizado no servidor com sucesso.")
    except:
        print("Falha ao avisar o servidor.")

def main():
    driver = setup_driver()
    wait = WebDriverWait(driver, 20)
    wait_check = WebDriverWait(driver, 5)

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
        #btn_final.click()        

        print(">>> SUCESSO! Botão de Ponto clicado! <<<")
        
        time.sleep(5)
        tirar_print(driver, "04_final_resultado")

        # 2. Reportar Sucesso
        sucesso = True  
        reportar_servidor(sucesso)

    except Exception as e:
        print(f"ERRO FATAL NA EXECUÇÃO: {e}")
        tirar_print(driver, "erro_fatal")
    
    finally:
        print("Encerrando driver e limpando memória...")
        driver.quit()


if __name__ == "__main__":
    main()