import datetime
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import captcha
import reporting
import utils

spec = importlib.util.spec_from_file_location('login_ocr_test', Path(__file__).resolve().parents[1] / 'login-ocr-ai.py')
login = importlib.util.module_from_spec(spec)
spec.loader.exec_module(login)


class RelatorioExecucao(unittest.TestCase):
    def setUp(self):
        reporting.limpar_ultima_falha()

    def executar_validacao(self, linha, valida=False):
        driver = Mock()
        espera = Mock()
        with patch.object(login, 'setup_driver', return_value=driver), patch.object(login, 'WebDriverWait', return_value=espera), patch.object(login, 'tirar_print'), patch.object(login.time, 'sleep'), patch.object(login, 'extrair_linha_hoje', side_effect=['linha anterior', linha]), patch.object(login, 'ja_batido_recente', return_value=False), patch.object(login, 'validar_linha_hoje', return_value=valida), patch.object(reporting, 'post_json', return_value=(True, {})) as post:
            resultado = login.run_once()
            payload = post.call_args.args[2]
        driver.quit.assert_called_once()
        # Modo de teste mantido: o botão final não é clicado.
        espera.until.return_value.click.assert_not_called()
        return resultado, payload

    def test_linha_invalida_envia_mesma_mensagem_do_log(self):
        resultado, payload = self.executar_validacao('06/10/2026 TER 13:10')
        self.assertFalse(resultado)
        self.assertEqual(payload['status'], 'falha')
        self.assertFalse(payload['sucesso'])
        self.assertEqual(payload['msgsucesso'], 'Linha de hoje encontrada, mas inválida/fora do intervalo de 10min: 06/10/2026 TER 13:10')

    def test_linha_ausente_tem_motivo(self):
        resultado, payload = self.executar_validacao(None)
        self.assertFalse(resultado)
        self.assertEqual(payload['msgsucesso'], 'Nenhuma marcação encontrada para hoje.')

    def test_linha_valida_continua_sucesso(self):
        resultado, payload = self.executar_validacao('06/10/2026 TER 14:50', valida=True)
        self.assertTrue(resultado)
        self.assertEqual(payload['msgsucesso'], '06/10/2026 TER 14:50')
        self.assertTrue(payload['sucesso'])

    def test_final_nao_substitui_motivo_por_mensagem_generica(self):
        mensagem = 'Linha de hoje encontrada, mas inválida/fora do intervalo de 10min: 06/10/2026 TER 13:10'
        def falhar(**kwargs):
            reporting.reportar_servidor('falha', mensagem, sucesso=False)
            return False
        with patch.object(login, 'REGISTER_ATTEMPTS', 2), patch.object(login, 'run_once', side_effect=falhar), patch.object(login.time, 'sleep'), patch.object(reporting, 'post_json', return_value=(True, {})) as post:
            login.main()
            self.assertEqual(post.call_args.args[2]['msgsucesso'], mensagem)

    def test_relatorio_identifica_tarefa(self):
        with patch.dict('os.environ', {'TAREFA_DATA_EXECUCAO':'2026-10-06', 'TAREFA_HORA':'14', 'TAREFA_MINUTO':'50'}), patch.object(reporting, 'post_json', return_value=(True, {})) as post:
            reporting.reportar_servidor('falha', 'motivo', sucesso=False)
            self.assertEqual(post.call_args.args[2], {'status':'falha', 'msgsucesso':'motivo', 'sucesso':False, 'data_execucao':'2026-10-06', 'hora':'14', 'minuto':'50'})

    def test_link_oculto_nao_selecionado(self):
        oculto, visivel = Mock(), Mock()
        oculto.is_displayed.return_value = False
        visivel.is_displayed.return_value = True
        visivel.is_enabled.return_value = True
        driver = Mock()
        driver.find_elements.return_value = [oculto, visivel]
        self.assertIs(login.elemento_clicavel(driver, '//a'), visivel)

    def test_sem_link_clicavel_continua_esperando(self):
        driver = Mock()
        driver.find_elements.return_value = []
        self.assertFalse(login.elemento_clicavel(driver, '//a'))


class ValidacaoHorario(unittest.TestCase):
    def setUp(self):
        class Relogio(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 6, 14, 51, 55)
        self.patch = patch.object(utils.datetime, 'datetime', Relogio)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_linha_do_log_fora_dez_minutos(self):
        self.assertFalse(utils.validar_linha_hoje('06/10/2026 TER 13:10'))

    def test_ultima_marcacao_recente_valida(self):
        self.assertTrue(utils.validar_linha_hoje('06/10/2026 TER 13:10 14:50'))

    def test_outro_dia_nao_e_sucesso(self):
        self.assertFalse(utils.validar_linha_hoje('05/10/2026 SEG 14:50'))
        self.assertFalse(utils.ja_batido_recente('05/10/2026 SEG 14:50'))

    def test_futuro_distante_nao_impede_registro(self):
        self.assertFalse(utils.ja_batido_recente('06/10/2026 TER 18:30'))
        self.assertTrue(utils.ja_batido_recente('06/10/2026 TER 14:55'))


class GeminiSDK(unittest.TestCase):
    def test_sdk_novo_sem_chamada_real(self):
        client = Mock()
        client.models.generate_content.return_value.text = '5J9Q'
        contexto = Mock()
        contexto.__enter__ = Mock(return_value=client)
        contexto.__exit__ = Mock(return_value=False)
        with patch.object(captcha, 'API_KEY', 'chave-ficticia'), patch.object(captcha.genai, 'Client', return_value=contexto) as constructor:
            self.assertEqual(captcha._try_gemini(b'imagem-ficticia'), '5J9Q')
            self.assertEqual(constructor.call_args.kwargs['http_options'].timeout, 60000)
            self.assertEqual(client.models.generate_content.call_args.kwargs['model'], 'gemini-flash-latest')

    def test_resposta_fora_do_formato_nao_e_aceita(self):
        client = Mock()
        client.models.generate_content.return_value.text = '3X8LF'
        contexto = Mock()
        contexto.__enter__ = Mock(return_value=client)
        contexto.__exit__ = Mock(return_value=False)
        with patch.object(captcha, 'API_KEY', 'chave-ficticia'), patch.object(captcha.genai, 'Client', return_value=contexto), patch.object(captcha.time, 'sleep'):
            self.assertIsNone(captcha._try_gemini(b'imagem-ficticia'))
            self.assertEqual(client.models.generate_content.call_count, 2)


if __name__ == '__main__':
    unittest.main()
