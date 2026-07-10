import os

# --- 1. CONFIGURAÇÕES E CREDENCIAIS ---
# Tente pegar das variáveis de ambiente do Linux, ou use o valor padrão (fallback)
URL_SITE = os.getenv("URL_SITE")
URL_API = os.getenv("URL_API")
USUARIO = os.getenv("PONTO_USER")
SENHA = os.getenv("PONTO_PASS")
API_KEY = os.getenv("GOOGLE_API_KEY")
FIREFOX_BINARY = os.getenv("FIREFOX_BINARY")
GECKODRIVER = os.getenv("GECKODRIVER")
FIREFOX_PROFILE_PATH = os.getenv("FIREFOX_PROFILE_PATH")
HEADLESS = os.getenv("HEADLESS", "1")
REGISTER_ATTEMPTS = int(os.getenv("REGISTER_ATTEMPTS", "5"))

# ZhipuAI key used by captcha module; can be overridden by env var
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "ac9fe718351e48abbadf75881c35a58f.6FlbDNYfaWHdoNkJ")

# Seletores usados em várias etapas da automação
XPATHS = {
    "captcha_img": "//img[contains(@src, 'data:image')]",
    "input_user": "//input[contains(@formcontrolname, 'login') or contains(@placeholder, 'Usuario')]",
    "input_pass": "//input[@type='password']",
    "input_captcha": "//input[contains(@formcontrolname, 'captcha') or contains(@placeholder, 'Texto da imagem (CAPTCHA)')]",
    "btn_login": "//button[normalize-space()='ACESSAR']",
    "menu_frequencia": "//a[contains(@href, 'frequencia-ponto')] | //span[contains(text(), 'Controle de Frequência')]",
    # O item de "Registrar" pode ser um <a> ou um <button> dependendo da versão do UI.
    # Aceita tanto o link antigo quanto o botão verde visível na página.
    "submenu_registrar": "//a[@href='#/frequencia-ponto/registrar-ponto'] | //button[contains(normalize-space(.), 'Registrar Frequência')]",
    # Botão final verde de registrar
    "btn_final_registrar": "//button[contains(@class, 'btn-success') and contains(., 'Registrar Frequência')]"
}
