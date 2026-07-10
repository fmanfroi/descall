import time
from pathlib import Path
import requests
import base64

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC

from common import logger
from config import URL_SITE, USUARIO, SENHA, REGISTER_ATTEMPTS, XPATHS
from drivers import setup_driver, setup_chrome_driver
from captcha import resolver_captcha
from utils import tirar_print, extrair_linha_hoje, validar_linha_hoje, ja_batido_recente
from reporting import reportar_servidor


def run_once(use_ai=False) -> bool:
    """Executa todo o fluxo de registrar ponto uma vez.
    use_ai: se True, utiliza Gemini como prioridade no captcha.
    """
    driver = None
    try:
        # Primeira tentativa: Firefox (padrão)
        driver = setup_driver()
    except Exception as e:
        logger.exception("Erro ao iniciar o WebDriver (Firefox): %s", e)
        # Se o Firefox falhar, tentar duas tentativas com Chrome como fallback
        driver = setup_chrome_driver()
        if not driver:
            logger.exception("Erro iniciando o WebDriver: nenhum driver disponível após tentativas")
            reportar_servidor("falha", "erro iniciando webdriver", sucesso=False)
            return False

    wait = WebDriverWait(driver, 45)
    wait_check = WebDriverWait(driver, 20)

    try:
        logger.info("Acessando: %s", URL_SITE)
        driver.get(URL_SITE)

        try:
            # TENTATIVA 1: Verifica se o menu JÁ está na tela (sessão salva no perfil)
            wait_check.until(EC.presence_of_element_located((By.XPATH, XPATHS["menu_frequencia"])))
            print("✅ Já está logado! Pulando etapa de autenticação.")

        except TimeoutException:
            try:
                tirar_print(driver, "01_pre_login")
                # 1. Localizar e extrair imagem do CAPTCHA
                img_element = wait.until(lambda d: d.find_element(By.XPATH, XPATHS["captcha_img"]) if d else None)
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
                    return False

                # 2. Resolver Captcha
                codigo_captcha = resolver_captcha(image_bytes, use_ai=use_ai)
                if codigo_captcha:
                    wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_captcha"]))).send_keys(codigo_captcha)
                else:
                    logger.warning("Falha ao resolver captcha (ou falha no OCR)")
                    return False

                logger.info("Preenchendo credenciais...")
                wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_user"]))).send_keys(USUARIO)
                wait.until(EC.visibility_of_element_located((By.XPATH, XPATHS["input_pass"]))).send_keys(SENHA)
               
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
        menu = wait.until(EC.presence_of_element_located((By.XPATH, XPATHS["menu_frequencia"])))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", menu)
        logger.info("Menu 'Controle de Frequência' acessado.")
        time.sleep(5)

        # Verifica se já bateu ponto no intervalo de 1 hora antes de tentar registrar novamente
        linha_hoje_previa = extrair_linha_hoje(driver)
        if ja_batido_recente(linha_hoje_previa):
            logger.info("Ponto já foi batido recentemente (até 1h atrás): %s. Abortando nova marcação.", linha_hoje_previa)
            try:
                reportar_servidor("sucesso", f"ponto ja batido recentemente: {linha_hoje_previa}", sucesso=True)
            except Exception as e_rep:
                logger.warning("Falha ao reportar status de ponto já batido: %s", e_rep)
            return True


        # 6. Navegação: Registrar Ponto
        try:
            submenu = wait.until(EC.presence_of_element_located((By.XPATH, XPATHS["submenu_registrar"])))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submenu)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", submenu)
            logger.info("Submenu 'Registrar' acessado.")
            time.sleep(3)
            tirar_print(driver, "03_tela_registro")
        except TimeoutException:
            # Diagnóstico: salvar screenshot, page_source e listar candidatos
            tirar_print(driver, "xx_submenu_timeout")
            log_dir = Path("log")
            log_dir.mkdir(parents=True, exist_ok=True)
            try:
                with open(log_dir / "page_after_menu.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
            except Exception:
                logger.exception("Falha ao gravar page_after_menu.html")

            try:
                candidates = driver.find_elements(By.XPATH, "//a|//button|//li")
                with open(log_dir / "candidates.txt", "w", encoding="utf-8") as f:
                    for e in candidates:
                        try:
                            href = e.get_attribute('href') or ''
                            cls = e.get_attribute('class') or ''
                            txt = (e.text or '').strip().replace('\n', ' ')
                            f.write(f"TAG={e.tag_name} TEXT={txt} HREF={href} CLASS={cls}\n")
                        except Exception:
                            continue
            except Exception:
                logger.exception("Falha ao listar elementos candidatos")

            logger.exception("Submenu 'Registrar' não encontrado — dumps salvos em log/")
            raise

        # 7. AÇÃO FINAL: Registrar
        logger.info("Procurando botão final de registro...")
        btn_final = wait.until(EC.element_to_be_clickable((By.XPATH, XPATHS["btn_final_registrar"])))
        
        btn_final.click()
        logger.info(">>> Botão de Ponto clicado <<<")

        # logger.info(">>> Botão de Ponto NÃO clicado <<<")

        time.sleep(15)  # Espera para o sistema processar o registro
        tirar_print(driver, "04_final_resultado")

        # 2. Reportar status final — extrair apenas a linha do dia de hoje
        status = "sucesso"
        linha_hoje = None
        try:
            menu = wait.until(EC.presence_of_element_located((By.XPATH, XPATHS["menu_frequencia"])))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", menu)
            logger.info("Menu 'Controle de Frequência' acessado.")
            time.sleep(10)

            linha_hoje = extrair_linha_hoje(driver)
            if linha_hoje:
                if validar_linha_hoje(linha_hoje):
                    logger.info("Linha de hoje válida: %s", linha_hoje)
                    status = "sucesso"
                else:
                    logger.warning("Linha de hoje encontrada, mas inválida/fora do intervalo de 10min: %s", linha_hoje)
                    status = "falha"
                    # força rerun (dentro de run_once), o main fará retries
                
            else:
                logger.debug("Nenhuma marcação encontrada para hoje.")
                status = "falha"

        except Exception as e:
            status = "falha"
            linha_hoje = str(e)
            logger.exception("Erro ao extrair/imprimir linha de hoje: %s", e)

        try:
            reportar_servidor(status, linha_hoje, sucesso=(status == "sucesso"))
        except Exception as e:
            logger.warning("Falha ao reportar status final: %s", e)

        return status == "sucesso"

    except Exception as e:
        logger.exception("ERRO FATAL NA EXECUÇÃO: %s", e)
        try:
            tirar_print(driver, "erro_fatal")
        except Exception:
            pass
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
            pass


def main():
    try:
        reportar_servidor("executando", None)
    except Exception as e:
        logger.warning("Falha ao reportar status executando: %s", e)

    attempts = int(REGISTER_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        logger.info("Iniciando tentativa %d/%d", attempt, attempts)
        use_ai = (attempt > (attempts/2))
        ok = run_once(use_ai=use_ai)
        if ok:
            logger.info("Fluxo completado com sucesso na tentativa %d", attempt)
            return
        if attempt < attempts:
            logger.warning("Tentativa %d falhou — aguardando e tentando novamente...", attempt)
            time.sleep(20)

    logger.error("Todas as tentativas (%d) falharam. Marcando como falha definitiva.", attempts)
    try:
        reportar_servidor("falha", "todas as tentativas falharam", sucesso=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
