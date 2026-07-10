import time
import subprocess
import logging
import os
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.chrome import ChromeDriverManager

from config import FIREFOX_BINARY, GECKODRIVER, HEADLESS, REGISTER_ATTEMPTS
from common import logger

# workaround to prevent noisy tracebacks when terminating webdriver services
try:
    import selenium.webdriver.common.service as _selenium_service

    def _safe_terminate(self):
        try:
            stdin, stdout, stderr = (
                getattr(self, 'process').stdin,
                getattr(self, 'process').stdout,
                getattr(self, 'process').stderr,
            )
            for stream in (stdin, stdout, stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            proc = getattr(self, 'process', None)
            if not proc:
                return
            try:
                proc.terminate()
            except PermissionError:
                return
            except OSError:
                return

            try:
                proc.wait(60)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    logger.warning("Falha ao enviar SIGKILL (ignorado)")
        except Exception:
            logger.debug("Erro ignorado ao tentar terminar service process")

    _selenium_service.Service._terminate_process = _safe_terminate
except Exception:
    logger.debug("Não foi possível aplicar workaround de término do serviço")


def setup_driver() -> webdriver.Firefox:
    """Configura o Firefox (GeckoDriver)."""
    firefox_options = Options()
    firefox_options.accept_insecure_certs = True
    firefox_options.set_preference("dom.webnotifications.enabled", False)
    firefox_options.set_preference("dom.push.enabled", False)
    firefox_options.set_preference("dom.disable_open_during_load", True)
    firefox_options.set_preference("network.negotiate-auth.allow-insecure-ntlm-v1", True)
    firefox_options.add_argument("--window-size=1920,1080")
    try:
        if HEADLESS and HEADLESS != "0":
            firefox_options.add_argument("--headless")
    except Exception:
        firefox_options.add_argument("--headless")

    if FIREFOX_BINARY:
        firefox_options.binary_location = FIREFOX_BINARY
    else:
        logger.warning("Variável de ambiente FIREFOX_BINARY não definida. O Selenium tentará encontrar o Firefox automaticamente.")

    service = None
    if GECKODRIVER:
        try:
            service = Service(GECKODRIVER)
            logger.info("Usando Geckodriver do caminho especificado: %s", GECKODRIVER)
        except Exception as e:
            logger.warning("Falha ao iniciar Geckodriver do caminho especificado (%s): %s. Tentando instalar automaticamente...", GECKODRIVER, e)
            service = None

    if not service:
        logger.info("Tentando instalar Geckodriver automaticamente com GeckoDriverManager.")
        for attempt in range(1, REGISTER_ATTEMPTS + 1):
            try:
                installed_path = GeckoDriverManager().install()
                service = Service(installed_path)
                logger.info("Geckodriver instalado e Service criado a partir de %s (tentativa %d/%d).", installed_path, attempt, REGISTER_ATTEMPTS)
                break
            except Exception as e2:
                if attempt < REGISTER_ATTEMPTS:
                    logger.warning("Falha ao instalar geckodriver (tentativa %d/%d): %s. Re-tentando...", attempt, REGISTER_ATTEMPTS, e2)
                    time.sleep(10 * attempt)
                else:
                    logger.exception("Falha final ao instalar geckodriver após %d tentativas: %s", REGISTER_ATTEMPTS, e2)
                    raise

    if service:
        driver = webdriver.Firefox(service=service, options=firefox_options)
        driver.set_window_size(1920, 1080)
        return driver
    else:
        raise Exception("Não foi possível configurar o serviço do GeckoDriver.")


def setup_chrome_driver() -> webdriver.Chrome | None:
    """Configura o Chrome (ChromeDriver) como fallback."""
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    try:
        if HEADLESS and HEADLESS != "0":
            chrome_options.add_argument("--headless")
    except Exception:
        chrome_options.add_argument("--headless")

    install_attempts = 3
    for attempt in range(1, install_attempts + 1):
        try:
            installed = ChromeDriverManager().install()
            service = ChromeService(installed)
            logger.info("Chromedriver instalado e Service criado a partir de %s (tentativa %d/%d).", installed, attempt, install_attempts)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_window_size(1920, 1080)
            return driver
        except Exception as e2:
            if attempt < install_attempts:
                logger.warning("Falha ao instalar chromedriver (tentativa %d/%d): %s. Re-tentando...", attempt, install_attempts, e2)
                time.sleep(10 * attempt)
            else:
                logger.exception("Falha final ao instalar chromedriver após %d tentativas: %s", install_attempts, e2)
                raise

    return None
