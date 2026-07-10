import base64
import re
import time
import concurrent.futures
from PIL import Image
import io
import pytesseract
import google.generativeai as genai

from config import API_KEY, ZHIPU_API_KEY
from common import logger
from zhipuai import ZhipuAI

def _tesseract_valid(text: str) -> bool:
    """Verifica se o texto segue o padrão: dígito-letra-dígito-letra (ex: 1a2b)."""
    if not text:
        return False
    return bool(re.match(r'^\d[a-zA-Z]\d[a-zA-Z]$', text))

def _try_tesseract(image_bytes: bytes) -> str | None:
    """Tenta resolver CAPTCHA usando Tesseract OCR."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        texto = pytesseract.image_to_string(img).strip()
        texto = re.sub(r'[^a-zA-Z0-9]', '', texto)
        if texto and _tesseract_valid(texto):
            logger.info("Tesseract identificou captcha válido: %s", texto)
            return texto
        else:
            logger.info("Tesseract retornou '%s' mas não atende critério", texto)
            return None
    except Exception as e:
        logger.error("Erro no Tesseract: %s", e)
        return None


def _try_gemini(image_bytes: bytes) -> str | None:
    """Tenta resolver CAPTCHA usando Gemini AI."""
    if not API_KEY:
        logger.warning("GOOGLE_API_KEY não configurada; pulando Gemini")
        return None

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("models/gemini-flash-latest")

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        logger.info("Enviando imagem para Gemini (tentativa %d/%d)", attempt, max_attempts)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(model.generate_content, [
            {"mime_type": "image/png", "data": image_bytes},
            "Retorne APENAS os caracteres alfanuméricos desta imagem. Sem espaços, sem texto extra."
        ])
        try:
            response = future.result(timeout=60)
            texto = getattr(response, "text", "").strip()
            if texto:
                logger.info("Gemini identificou captcha válido: %s", texto)
                texto = re.sub(r'[^a-zA-Z0-9]', '', texto)               
                try:
                    executor.shutdown(wait=False)
                except Exception:
                    pass
                return texto                
            else:
                logger.warning("Resposta vazia do Gemini (tentativa %d/%d)", attempt, max_attempts)
        except concurrent.futures.TimeoutError:
            logger.warning("Timeout de 60s atingido para Gemini (tentativa %d/%d)", attempt, max_attempts)
            try:
                future.cancel()
            except Exception:
                pass
        except Exception as e:
            logger.warning("Erro ao chamar Gemini (tentativa %d/%d): %s", attempt, max_attempts, e)
        finally:
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass
        time.sleep(1)
    return None


def _try_zhipu(image_bytes: bytes) -> str | None:
    """Tenta resolver CAPTCHA usando ZhipuAI."""
    try:
        client = ZhipuAI(api_key=ZHIPU_API_KEY)
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        response = client.chat.completions.create(
            model="glm-4v-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                        {"type": "text", "text": "Retorne APENAS os caracteres alfanuméricos desta imagem. Sem espaços, sem texto extra."}
                    ],
                }
            ],
            top_p=0.1,
            temperature=0.1,
            max_tokens=1024,
            stream=False,
        )
        texto = response.choices[0].message.content
        if texto:
            texto = re.sub(r'[^a-zA-Z0-9]', '', texto)
            if _tesseract_valid(texto):
                logger.info("ZhipuAI identificou captcha válido: %s", texto)
                return texto
            else:
                logger.warning("ZhipuAI retornou '%s' mas não atende critério", texto)
        return None
    except Exception as e:
        logger.error("Erro na chamada ZhipuAI: %s", e)
        return None


def resolver_captcha(image_bytes: bytes, use_ai=False) -> str | None:
    """Resolve o CAPTCHA a partir dos bytes da imagem.
    Se use_ai=True, tenta Gemini e ZhipuAI após Tesseract.
    """
    logger.info("Iniciando resolução de CAPTCHA (prioridade: %s)", "IA" if use_ai else "Local")
    try:
        if not image_bytes:
            logger.error("Bytes da imagem não fornecidos")
            return None

        texto_captcha = None

        # Sempre tentar Tesseract primeiro
        texto_captcha = _try_tesseract(image_bytes)
        if texto_captcha:
            return texto_captcha

        # Se use_ai ou Tesseract falhou, tentar Gemini
        if use_ai:
            texto_captcha = _try_gemini(image_bytes)
            if texto_captcha:
                return texto_captcha

            # Se Gemini falhou, tentar ZhipuAI como último recurso
            texto_captcha = _try_zhipu(image_bytes)
            if texto_captcha:
                return texto_captcha

        logger.error("Falha ao resolver captcha com as técnicas solicitadas.")
        return None

    except Exception as e:
        logger.exception("Erro no módulo de Captcha: %s", e)
        return None
