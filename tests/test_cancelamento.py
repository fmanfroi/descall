import datetime
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

# Não carregar o .env nem acessar o banco real durante os testes.
_pasta_banco = tempfile.TemporaryDirectory(prefix='descall-test-')
with patch('dotenv.load_dotenv'), patch.dict(os.environ, {'DATABASE_URL': 'sqlite:///' + _pasta_banco.name + '/test.db'}):
    import main as api
    import cliente
import executar_tarefa
from fastapi.testclient import TestClient
from sqlmodel import SQLModel


class CancelamentoAPI(unittest.TestCase):
    def setUp(self):
        SQLModel.metadata.drop_all(api.engine)
        api.criar_banco()
        self.client = TestClient(api.app)
        self.key = {'data_execucao': '2026-10-07', 'hora': '12', 'minuto': '30'}
        self.client.post('/api/agendar', json=self.key).raise_for_status()

    def confirmar(self, status, **extra):
        return self.client.post('/api/confirmar-execucao', json={**self.key, 'status': status, **extra})

    def test_cancelar_criado_e_idempotencia(self):
        for _ in range(2):
            r = self.client.post('/api/cancelar', json=self.key)
            self.assertEqual(r.json()['status'], 'cancelado')
        self.assertEqual(self.client.get('/api/consultar').json(), {})
        self.assertEqual(self.client.post('/api/iniciar-execucao', json=self.key).status_code, 409)

    def test_cancelamento_durante_agendamento_e_confirmacao_atrasada(self):
        self.confirmar('consultado')
        self.assertEqual(self.client.post('/api/cancelar', json=self.key).json()['status'], 'cancelamento_pendente')
        r = self.confirmar('agendado', job_id='123')
        self.assertEqual(r.json()['tarefa']['status'], 'cancelamento_pendente')
        pendentes = self.client.get('/api/cancelamentos').json()
        self.assertEqual(pendentes[0]['job_id'], '123')
        self.assertEqual(self.client.post('/api/iniciar-execucao', json=self.key).status_code, 409)
        self.assertEqual(self.confirmar('cancelado').json()['tarefa']['status'], 'cancelado')
        self.assertEqual(self.client.get('/api/cancelamentos').json(), [])
        self.assertEqual(self.confirmar('sucesso').json()['tarefa']['status'], 'cancelado')

    def test_cancelamento_antes_de_receber_consulta(self):
        self.client.post('/api/cancelar', json=self.key)
        self.assertEqual(self.confirmar('consultado').json()['tarefa']['status'], 'cancelado')

    def test_nao_cancelar_execucao_iniciada_ou_finalizada(self):
        self.confirmar('agendado', job_id='9')
        self.assertEqual(self.client.post('/api/iniciar-execucao', json=self.key).status_code, 200)
        self.assertEqual(self.client.post('/api/iniciar-execucao', json=self.key).status_code, 409)
        self.assertEqual(self.client.post('/api/cancelar', json=self.key).status_code, 409)
        self.assertEqual(self.confirmar('agendado').json()['tarefa']['status'], 'executando')
        self.confirmar('sucesso')
        self.assertEqual(self.client.post('/api/cancelar', json=self.key).status_code, 409)

    def test_nao_reagendar_enquanto_cancelamento_pendente(self):
        self.confirmar('agendado', job_id='123')
        self.client.post('/api/cancelar', json=self.key)
        self.assertEqual(self.client.post('/api/agendar', json=self.key).status_code, 409)
        self.confirmar('cancelado')
        self.assertEqual(self.client.post('/api/agendar', json=self.key).status_code, 200)
        self.confirmar('consultado')
        self.client.post('/api/cancelar', json=self.key)
        self.assertIsNone(self.client.get('/api/cancelamentos').json()[0]['job_id'])

    def test_tarefa_inexistente_e_identificador_parcial(self):
        key = {**self.key, 'minuto': '31'}
        self.assertEqual(self.client.post('/api/cancelar', json=key).status_code, 404)
        self.assertEqual(self.client.post('/api/confirmar-execucao', json={**key, 'status': 'cancelado'}).status_code, 404)
        self.assertEqual(self.client.post('/api/confirmar-execucao', json={'hora': '12', 'status': 'cancelado'}).status_code, 422)
        self.assertEqual(self.confirmar('cancelado').status_code, 409)

    def test_home_inclui_cancelamento(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('/api/cancelar', r.text)
        self.assertIn('Cancelar', r.text)


class CancelamentoCliente(unittest.TestCase):
    def setUp(self):
        self.dados = {'data_para_execucao': '2026-10-07', 'hora': '12', 'minuto': '30', 'job_id': '123'}
        self.session = Mock()
        self.session.get.return_value.json.return_value = [self.dados]
        self.horario = datetime.datetime(2026, 10, 7, 12, 30)

    def test_remove_somente_job_da_tarefa(self):
        with patch.object(cliente, 'trabalhos_at', return_value={'123': self.horario, '456': self.horario}), patch.object(cliente.subprocess, 'run') as run, patch.object(cliente, 'reportar_servidor') as report:
            cliente.processar_cancelamentos(self.session)
            self.assertEqual(run.call_args.args[0], ['atrm', '123'])
            report.assert_called_once_with(self.session, 'cancelado', 'Cancelamento confirmado no executor', data_execucao='2026-10-07', hora='12', minuto='30')

    def test_falha_atrm_nao_confirma_cancelamento(self):
        with patch.object(cliente, 'trabalhos_at', return_value={'123': self.horario}), patch.object(cliente.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'atrm')), patch.object(cliente, 'reportar_servidor') as report:
            cliente.processar_cancelamentos(self.session)
            report.assert_not_called()

    def test_job_protegido_fora_da_fila(self):
        with patch.object(cliente, 'trabalhos_at', return_value={}), patch.object(cliente.subprocess, 'run') as run, patch.object(cliente, 'reportar_servidor') as report:
            cliente.processar_cancelamentos(self.session)
            run.assert_not_called()
            report.assert_called_once()

    def test_legado_remove_apenas_comando_e_horario_exatos(self):
        self.dados['job_id'] = None
        def executar(args, **kwargs):
            texto = '# script de outro projeto\n' if args == ['at', '-c', '456'] else '# ambiente\n/opt/descall/registrar.sh\n'
            return subprocess.CompletedProcess(args, 0, stdout=texto, stderr='')
        with patch.object(cliente, 'SCRIPT_ALVO', '/opt/descall/registrar.sh'), patch.object(cliente, 'trabalhos_at', return_value={'123': self.horario, '456': self.horario}), patch.object(cliente.subprocess, 'run', side_effect=executar) as run, patch.object(cliente, 'reportar_servidor') as report:
            cliente.processar_cancelamentos(self.session)
            removidos = [c.args[0] for c in run.call_args_list if c.args[0][0] == 'atrm']
            self.assertEqual(removidos, [['atrm', '123']])
            report.assert_called_once()

    def test_legado_nao_localizado_mantem_pendente(self):
        self.dados['job_id'] = None
        with patch.object(cliente, 'trabalhos_at', return_value={}), patch.object(cliente, 'reportar_servidor') as report:
            cliente.processar_cancelamentos(self.session)
            report.assert_not_called()

    def test_at_recebe_data_completa_e_wrapper(self):
        resultado = subprocess.CompletedProcess([], 0, stdout='', stderr='warning: commands will be executed using /bin/sh\njob 123 at Wed Oct 7 12:30:00 2026\n')
        with patch.object(cliente, 'SCRIPT_ALVO', '/opt/descall/registrar.sh'), patch.object(cliente.subprocess, 'run', return_value=resultado) as run:
            self.assertEqual(cliente.agendar_via_at(self.horario, self.dados), '123')
            self.assertEqual(run.call_args.args[0], ['at', '-t', '202610071230'])
            self.assertIn('executar_tarefa.py', run.call_args.kwargs['input'])
            self.assertIn('2026-10-07 12 30', run.call_args.kwargs['input'])

    def test_atq_formato(self):
        resultado = subprocess.CompletedProcess([], 0, stdout='123\tWed Oct  7 12:30:00 2026 a usuario\n', stderr='')
        with patch.object(cliente.subprocess, 'run', return_value=resultado):
            self.assertEqual(cliente.trabalhos_at(), {'123': self.horario})

    def test_futuro_nao_consumido(self):
        dados = {**self.dados, 'data_para_execucao': '2099-10-07'}
        with patch.object(cliente, 'URL', 'http://api.test'), patch.object(cliente, 'fetch_agendamento', return_value=dados), patch.object(cliente, 'processar_cancelamentos'), patch.object(cliente, 'post_json') as post:
            cliente.executar_cliente()
            post.assert_not_called()


class ExecucaoProtegida(unittest.TestCase):
    def test_bloqueia_se_api_recusa_ou_falha(self):
        import requests
        for erro in (requests.HTTPError('409'), requests.ConnectionError('offline')):
            with patch.object(executar_tarefa, 'load_dotenv'), patch.dict(os.environ, {'URL_API': 'http://api.test', 'SCRIPT_PONTO': '/script.sh'}), patch.object(executar_tarefa.sys, 'argv', ['executar_tarefa.py', '2026-10-07', '12', '30']), patch.object(executar_tarefa.requests, 'post', side_effect=erro), patch.object(executar_tarefa.subprocess, 'run') as run:
                self.assertEqual(executar_tarefa.main(), 1)
                run.assert_not_called()

    def test_autorizado_preserva_identificador_para_relatorio(self):
        with patch.object(executar_tarefa, 'load_dotenv'), patch.dict(os.environ, {'URL_API': 'http://api.test', 'SCRIPT_PONTO': '/script.sh'}), patch.object(executar_tarefa.sys, 'argv', ['executar_tarefa.py', '2026-10-07', '12', '30']), patch.object(executar_tarefa.requests, 'post') as post, patch.object(executar_tarefa.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(executar_tarefa.main(), 0)
            self.assertEqual(post.call_args.kwargs['json'], {'data_execucao': '2026-10-07', 'hora': '12', 'minuto': '30'})
            self.assertEqual(run.call_args.kwargs['env']['TAREFA_DATA_EXECUCAO'], '2026-10-07')


if __name__ == '__main__':
    unittest.main()
